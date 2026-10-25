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

from .const import (
    CONF_ROOMS,
    DOMAIN,
    LLM_API_ID,
    LLM_API_NAME,
    MAX_CURVE_DAYS,
    MAX_DAYS,
    ROLE_UNLOCKS,
    ROLES,
)
from .runner import (
    async_run_curve,
    async_run_cycles,
    async_run_rooms,
    entity_name,
    has_curve_roles,
    settings_of,
)

KNOWLEDGE_URL = "https://github.com/sommer-nt/heatpump-insights/blob/main/docs/knowledge"

API_PROMPT = (
    "You have expert heat pump analysis tools. Call heatpump_describe first to see which "
    "heat pumps and sensors are configured. Every figure in a tool result is computed from "
    "the user's recorded data: quote it, do not estimate your own. "
    "Rules for advice: (1) Always state how much data a statement rests on (coverage, "
    "data_days, evidence) and say plainly when data is insufficient. (2) Start with the "
    "simplest explanation the data allows - a setpoint, the weather, too little data - "
    "before anything else. (3) Each finding has a severity: 'info' is context, 'check' means "
    "worth watching or verifying, 'act' means a reversible setting change is justified. Only "
    "suggest setting changes for 'act' findings, one at a time, and never recommend physical "
    "work (flushing, balancing, replacing parts) - at most suggest discussing a persistent "
    "pattern with the installer. (4) Never present an analysis as available unless "
    "heatpump_describe lists it. These tools never change settings. "
    "Before talking about the heating curve, combine heatpump_heating_curve with heating_rooms."
)

READ_ONLY = llm.ToolAnnotations(read_only=True, destructive=False, idempotent=True, open_world=False)


def _entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return hass.config_entries.async_loaded_entries(DOMAIN)


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


def _days(maximum: int, default: int) -> dict:
    return {
        probatio.Optional(
            "days", default=default, description=f"Days back from now to analyze (1-{maximum})"
        ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=maximum)),
        probatio.Optional("heat_pump", description="Heat pump name; omit if only one"): str,
    }


def _window(days: int):
    end = dt_util.utcnow()
    return end - timedelta(days=days), end


class DescribeTool(llm.Tool):
    name = "heatpump_describe"
    title = "Describe heat pumps"
    description = (
        "List the configured heat pumps, the sensor assigned to each role with its current "
        "value, the analyses available for each, and what missing sensors would unlock."
    )
    annotations = READ_ONLY
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        pumps = []
        for entry in _entries(hass):
            settings = settings_of(entry)
            roles = {}
            missing = {}
            for role, label in ROLES.items():
                entity_id = settings.get(role)
                if not entity_id:
                    if role in ROLE_UNLOCKS:
                        missing[role] = ROLE_UNLOCKS[role]
                    continue
                if isinstance(entity_id, list):
                    roles[role] = {"meaning": label, "entities": [entity_name(hass, e) for e in entity_id]}
                    continue
                state = hass.states.get(entity_id)
                roles[role] = {
                    "meaning": label,
                    "entity_id": entity_id,
                    "state": state.state if state else "not found",
                    "unit": state.attributes.get("unit_of_measurement") if state else None,
                }
            available = ["heatpump_analyze_cycles"]
            if has_curve_roles(settings):
                available.append("heatpump_heating_curve")
            if settings.get(CONF_ROOMS):
                available.append("heating_rooms")
            pumps.append(
                {
                    "heat_pump": entry.title,
                    "roles": roles,
                    "available_analyses": available,
                    "missing_roles": missing,
                }
            )
        return llm.ToolResult(
            data={
                "heat_pumps": pumps,
                "max_days": MAX_DAYS,
                "max_curve_days": MAX_CURVE_DAYS,
                "knowledge": KNOWLEDGE_URL,
            }
        )


class AnalyzeCyclesTool(llm.Tool):
    name = "heatpump_analyze_cycles"
    title = "Analyze compressor cycling"
    description = (
        "Detect compressor runs from the heat pump's power and assess cycling: starts per day, "
        "run and pause times, share of short cycles, worst hour, per-day figures and, with an "
        "outdoor sensor, cycling by outdoor temperature. Returns a rating with graded findings."
    )
    parameters = probatio.Schema(
        {
            **_days(MAX_DAYS, 7),
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
        start, end = _window(args["days"])
        report = await async_run_cycles(hass, entry, start, end, args.get("short_cycle_minutes"))
        data = report.as_dict()
        data["heat_pump"] = entry.title
        data["knowledge"] = f"{KNOWLEDGE_URL}/cycling.md"
        return llm.ToolResult(data=data)


class HeatingCurveTool(llm.Tool):
    name = "heatpump_heating_curve"
    title = "Analyze heating curve"
    description = (
        "Fit the effective heating curve from hourly flow and outdoor temperatures: slope in K/K, "
        "flow temperature at +10/0/-10 °C, fit quality, covered outdoor range and, if the "
        "controller's target flow is known, how well the actual flow follows it."
    )
    parameters = probatio.Schema(_days(MAX_CURVE_DAYS, 30))
    annotations = READ_ONLY
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        args = self.parameters(tool_input.tool_args)
        entry = _pick(hass, args.get("heat_pump"))
        if not has_curve_roles(settings_of(entry)):
            raise HomeAssistantError(
                "The heating curve needs an outdoor temperature and a heating circuit flow "
                "temperature (or the controller's target flow). Assign them in the integration options."
            )
        start, end = _window(args["days"])
        report = await async_run_curve(hass, entry, start, end)
        data = report.as_dict()
        data["heat_pump"] = entry.title
        data["knowledge"] = f"{KNOWLEDGE_URL}/heating-curve.md"
        return llm.ToolResult(data=data)


class RoomsTool(llm.Tool):
    name = "heating_rooms"
    title = "Analyze room comfort"
    description = (
        "Compare each room's temperature with its setpoint: mean deviation, share of time too "
        "cold or too warm, valve open share where valves are assigned, which rooms are "
        "overheated and which room limits the heating curve."
    )
    parameters = probatio.Schema(_days(MAX_DAYS, 7))
    annotations = READ_ONLY
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        args = self.parameters(tool_input.tool_args)
        entry = _pick(hass, args.get("heat_pump"))
        if not settings_of(entry).get(CONF_ROOMS):
            raise HomeAssistantError(
                "No room thermostats are assigned. Add climate entities in the integration options."
            )
        start, end = _window(args["days"])
        report, _, unmatched, _ = await async_run_rooms(hass, entry, start, end)
        data = report.as_dict()
        if unmatched:
            data["unmatched_valves"] = [entity_name(hass, v) for v in unmatched]
        data["heat_pump"] = entry.title
        data["knowledge"] = f"{KNOWLEDGE_URL}/rooms.md"
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
            tools=[DescribeTool(), AnalyzeCyclesTool(), HeatingCurveTool(), RoomsTool()],
        )
