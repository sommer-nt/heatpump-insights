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

from .analysis import CycleConfig, analyze_cycles, analyze_heating_curve, analyze_rooms
from .const import (
    CONF_CIRCUIT_FLOW,
    CONF_CIRCUIT_TARGET,
    CONF_CURVE_SLOPE,
    CONF_FLOW_TEMP,
    CONF_ON_THRESHOLD_W,
    CONF_OUTDOOR_TEMP,
    CONF_POWER,
    CONF_ROOMS,
    CONF_SHORT_CYCLE_MIN,
    DEFAULT_SHORT_CYCLE_MIN,
    DOMAIN,
    LLM_API_ID,
    LLM_API_NAME,
    MAX_CURVE_DAYS,
    MAX_DAYS,
    ROLE_UNLOCKS,
    ROLES,
)
from .data import async_load_attribute_samples, async_load_hourly_means, async_load_samples

KNOWLEDGE_URL = "https://github.com/sommer-nt/heatpump-insights/blob/main/docs/knowledge"

API_PROMPT = (
    "You have expert heat pump analysis tools. Call heatpump_describe first to see which "
    "heat pumps and sensors are configured. Every figure in a tool result is computed from "
    "the user's recorded data: quote it, do not estimate your own. Always mention the "
    "coverage, assumptions and missing sensors a result reports, and say when data is "
    "insufficient instead of guessing. Explain findings in plain language and suggest "
    "concrete, reversible setting changes one at a time; these tools never change settings. "
    "Before recommending a heating curve change, combine heatpump_heating_curve with "
    "heating_rooms: overheated rooms mean headroom to lower the curve, a limiting room must be "
    "fixed (balancing, emitter, setpoint) rather than compensated by a steeper curve."
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


def _room_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    return state.name if state else entity_id


def _days(maximum: int, default: int) -> dict:
    return {
        probatio.Optional(
            "days", default=default, description=f"Days back from now to analyze (1-{maximum})"
        ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=maximum)),
        probatio.Optional("heat_pump", description="Heat pump name; omit if only one"): str,
    }


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
                if isinstance(entity_id, list):
                    roles[role] = {
                        "meaning": label,
                        "entities": [_room_name(hass, e) for e in entity_id],
                    }
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
                "available_analyses": [
                    "heatpump_analyze_cycles",
                    "heatpump_heating_curve",
                    "heating_rooms",
                ],
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
        settings = _settings(entry)
        flow_id = settings.get(CONF_CIRCUIT_FLOW) or settings.get(CONF_FLOW_TEMP)
        outdoor_id = settings.get(CONF_OUTDOOR_TEMP)
        target_id = settings.get(CONF_CIRCUIT_TARGET)
        if not outdoor_id or not (flow_id or target_id):
            raise HomeAssistantError(
                "The heating curve needs an outdoor temperature and a heating circuit flow "
                "temperature (or the controller's target flow). Assign them in the integration options."
            )
        end = dt_util.utcnow()
        start = end - timedelta(days=args["days"])
        outdoor = await async_load_hourly_means(hass, outdoor_id, start, end)
        actual = await async_load_hourly_means(hass, flow_id, start, end) if flow_id else None
        target = await async_load_hourly_means(hass, target_id, start, end) if target_id else None
        slope = None
        if (slope_id := settings.get(CONF_CURVE_SLOPE)) and (state := hass.states.get(slope_id)):
            try:
                slope = float(state.state)
            except ValueError:
                slope = None
        report = await hass.async_add_executor_job(
            lambda: analyze_heating_curve(
                outdoor,
                actual,
                target,
                start=start.timestamp(),
                end=end.timestamp(),
                tz=dt_util.get_default_time_zone(),
                curve_setting=slope,
            )
        )
        data = report.as_dict()
        data["heat_pump"] = entry.title
        data["knowledge"] = f"{KNOWLEDGE_URL}/heating-curve.md"
        return llm.ToolResult(data=data)


class RoomsTool(llm.Tool):
    name = "heating_rooms"
    title = "Analyze room comfort"
    description = (
        "Compare each room's temperature with its setpoint: mean deviation, share of time too "
        "cold or too warm, which rooms are overheated (headroom to lower the curve) and which "
        "room limits the heating curve."
    )
    parameters = probatio.Schema(_days(MAX_DAYS, 7))
    annotations = READ_ONLY
    integration = DOMAIN

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> llm.ToolResult:
        args = self.parameters(tool_input.tool_args)
        entry = _pick(hass, args.get("heat_pump"))
        room_ids = _settings(entry).get(CONF_ROOMS) or []
        if not room_ids:
            raise HomeAssistantError(
                "No room thermostats are assigned. Add climate entities in the integration options."
            )
        end = dt_util.utcnow()
        start = end - timedelta(days=args["days"])
        rooms = {}
        for entity_id in room_ids:
            actual = await async_load_attribute_samples(hass, entity_id, "current_temperature", start, end)
            setpoint = await async_load_attribute_samples(hass, entity_id, "temperature", start, end)
            rooms[_room_name(hass, entity_id)] = (actual, setpoint)
        report = await hass.async_add_executor_job(
            lambda: analyze_rooms(
                rooms, start.timestamp(), end.timestamp(), tz=dt_util.get_default_time_zone()
            )
        )
        data = report.as_dict()
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
