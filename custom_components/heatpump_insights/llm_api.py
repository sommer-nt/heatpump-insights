"""LLM API: the expert tools an AI assistant can call.

Exposed through Home Assistant's LLM API registry, so the built-in MCP server
and every conversation agent (cloud or local) can use the same tools. All
numbers are computed here; the model only interprets them.
"""

from __future__ import annotations

from datetime import timedelta

import probatio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.util import dt as dt_util

from .analysis import CycleConfig, analyze_cycles
from .const import (
    CONF_ON_THRESHOLD_W,
    CONF_OUTDOOR_TEMP,
    CONF_POWER,
    CONF_SHORT_CYCLE_MIN,
    DEFAULT_SHORT_CYCLE_MIN,
    DOMAIN,
    LLM_API_ID,
    LLM_API_NAME,
    MAX_DAYS,
    ROLE_UNLOCKS,
    ROLES,
)
from .data import async_load_samples

KNOWLEDGE_URL = "https://github.com/sommer-nt/heatpump-insights/blob/main/docs/knowledge"

API_PROMPT = (
    "You have expert heat pump analysis tools. Call heatpump_describe first to see which "
    "heat pumps and sensors are configured. Every figure in a tool result is computed from "
    "the user's recorded data: quote it, do not estimate your own. Always mention the "
    "coverage, assumptions and missing sensors a result reports, and say when data is "
    "insufficient instead of guessing. Explain findings in plain language and suggest "
    "concrete, reversible setting changes one at a time; these tools never change settings."
)

READ_ONLY = llm.ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False)


def _entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return hass.config_entries.async_loaded_entries(DOMAIN)


def _settings(entry: ConfigEntry) -> dict:
    """Role mapping and tuning: options replace the initial data once saved."""
    return dict(entry.options or entry.data)


def _pick(hass: HomeAssistant, name: str | None) -> ConfigEntry:
    entries = _entries(hass)
    if not entries:
        raise HomeAssistantError("No heat pump is configured in Heat Pump Insights.")
    if name is None:
        if len(entries) > 1:
            raise HomeAssistantError(
                "Several heat pumps are configured; pass heat_pump with one of: "
                + ", ".join(e.title for e in entries)
            )
        return entries[0]
    for entry in entries:
        if entry.title.casefold() == name.casefold():
            return entry
    raise HomeAssistantError(f"Unknown heat pump {name!r}.")


class DescribeTool(llm.Tool):
    name = "heatpump_describe"
    title = "Describe heat pumps"
    description = (
        "List the configured heat pumps, the sensor assigned to each role with its current "
        "value, and which analyses missing sensors would unlock."
    )
    annotations = READ_ONLY
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        pumps = []
        for entry in _entries(hass):
            roles = {}
            missing = {}
            for role, label in ROLES.items():
                entity_id = _settings(entry).get(role)
                if not entity_id:
                    if role in ROLE_UNLOCKS:
                        missing[role] = ROLE_UNLOCKS[role]
                    continue
                state = hass.states.get(entity_id)
                roles[role] = {
                    "meaning": label,
                    "entity_id": entity_id,
                    "state": state.state if state else "not found",
                    "unit": state.attributes.get("unit_of_measurement") if state else None,
                }
            pumps.append({"heat_pump": entry.title, "roles": roles, "missing_roles": missing})
        return llm.ToolResult(
            data={
                "heat_pumps": pumps,
                "available_analyses": ["heatpump_analyze_cycles"],
                "max_days": MAX_DAYS,
                "knowledge": KNOWLEDGE_URL,
            }
        )


class AnalyzeCyclesTool(llm.Tool):
    name = "heatpump_analyze_cycles"
    title = "Analyze compressor cycling"
    description = (
        "Detect compressor runs from the heat pump's power and assess cycling: starts per day, "
        "run and pause times, share of short cycles, worst hour, per-day figures and, with an "
        "outdoor sensor, cycling by outdoor temperature. Returns a rating with findings."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional("heat_pump", description="Heat pump name; omit if only one"): str,
            probatio.Optional(
                "days", default=7, description=f"Days back from now to analyze (1-{MAX_DAYS})"
            ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=MAX_DAYS)),
            probatio.Optional(
                "short_cycle_minutes", description="Override the short-cycle limit (3-30 min)"
            ): probatio.All(probatio.Coerce(float), probatio.Range(min=3, max=30)),
        }
    )
    annotations = READ_ONLY
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        args = self.parameters(tool_input.tool_args)
        entry = _pick(hass, args.get("heat_pump"))
        settings = _settings(entry)
        end = dt_util.utcnow()
        start = end - timedelta(days=args["days"])

        power = await async_load_samples(hass, settings[CONF_POWER], start, end)
        outdoor = None
        if outdoor_id := settings.get(CONF_OUTDOOR_TEMP):
            outdoor = await async_load_samples(hass, outdoor_id, start, end)

        short_min = args.get("short_cycle_minutes") or settings.get(
            CONF_SHORT_CYCLE_MIN, DEFAULT_SHORT_CYCLE_MIN
        )
        cfg = CycleConfig(
            on_threshold_w=settings.get(CONF_ON_THRESHOLD_W) or None,
            short_cycle_s=float(short_min) * 60,
        )
        report = await hass.async_add_executor_job(
            lambda: analyze_cycles(
                power,
                start.timestamp(),
                end.timestamp(),
                tz=dt_util.get_default_time_zone(),
                outdoor_temp=outdoor,
                cfg=cfg,
            )
        )
        data = report.as_dict()
        data["heat_pump"] = entry.title
        data["knowledge"] = f"{KNOWLEDGE_URL}/cycling.md"
        return llm.ToolResult(data=data)


class HeatPumpInsightsAPI(llm.API):
    """One API for all configured heat pumps."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass=hass, id=LLM_API_ID, name=LLM_API_NAME)

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt=API_PROMPT,
            llm_context=llm_context,
            tools=[DescribeTool(), AnalyzeCyclesTool()],
        )
