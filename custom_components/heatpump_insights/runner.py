"""Load recorder data for a heat pump entry and run the analyses.

Shared by the LLM tools and the sensors, so both always show the same numbers.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .analysis import (
    CurveReport,
    CycleConfig,
    CycleReport,
    RoomsReport,
    analyze_cycles,
    analyze_heating_curve,
    analyze_rooms,
)
from .analysis.rooms import match_valves
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
    CONF_VALVES,
    DEFAULT_SHORT_CYCLE_MIN,
)
from .data import async_load_attribute_samples, async_load_hourly_means, async_load_samples


def settings_of(entry: ConfigEntry) -> dict:
    """Role mapping and tuning: options replace the initial data once saved."""
    return dict(entry.options or entry.data)


def entity_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    return state.name if state else entity_id


def _place(hass: HomeAssistant, entity_id: str) -> tuple[str, str | None, str | None]:
    """(name, area, device name or heating group) used to pair valves with rooms."""
    name = entity_name(hass, entity_id)
    entry = er.async_get(hass).async_get(entity_id)
    device = dr.async_get(hass).async_get(entry.device_id) if entry and entry.device_id else None
    area = (entry.area_id if entry else None) or (device.area_id if device else None)
    state = hass.states.get(entity_id)
    group = state.attributes.get("heating_group") if state else None
    if group is None and device is not None:
        group = device.name_by_user or device.name
    return name, area, group


def has_curve_roles(settings: dict) -> bool:
    return bool(
        settings.get(CONF_OUTDOOR_TEMP)
        and (
            settings.get(CONF_CIRCUIT_FLOW)
            or settings.get(CONF_FLOW_TEMP)
            or settings.get(CONF_CIRCUIT_TARGET)
        )
    )


async def async_run_cycles(
    hass: HomeAssistant,
    entry: ConfigEntry,
    start: datetime,
    end: datetime,
    short_cycle_minutes: float | None = None,
    threshold_w: float | None = None,
) -> CycleReport:
    """``threshold_w`` is used when no threshold is configured, e.g. today's figures reuse the
    threshold learned over the week (early in the day there may be no run to learn from)."""
    settings = settings_of(entry)
    power = await async_load_samples(hass, settings[CONF_POWER], start, end)
    outdoor = None
    if outdoor_id := settings.get(CONF_OUTDOOR_TEMP):
        outdoor = await async_load_samples(hass, outdoor_id, start, end)
    short_min = short_cycle_minutes or settings.get(CONF_SHORT_CYCLE_MIN, DEFAULT_SHORT_CYCLE_MIN)
    cfg = CycleConfig(
        on_threshold_w=settings.get(CONF_ON_THRESHOLD_W) or threshold_w,
        short_cycle_s=float(short_min) * 60,
    )
    return await hass.async_add_executor_job(
        lambda: analyze_cycles(
            power,
            start.timestamp(),
            end.timestamp(),
            tz=dt_util.get_default_time_zone(),
            outdoor_temp=outdoor,
            cfg=cfg,
        )
    )


async def async_run_curve(
    hass: HomeAssistant, entry: ConfigEntry, start: datetime, end: datetime
) -> CurveReport:
    """Caller checks ``has_curve_roles`` first."""
    settings = settings_of(entry)
    flow_id = settings.get(CONF_CIRCUIT_FLOW) or settings.get(CONF_FLOW_TEMP)
    target_id = settings.get(CONF_CIRCUIT_TARGET)
    outdoor = await async_load_hourly_means(hass, settings[CONF_OUTDOOR_TEMP], start, end)
    actual = await async_load_hourly_means(hass, flow_id, start, end) if flow_id else None
    target = await async_load_hourly_means(hass, target_id, start, end) if target_id else None
    slope = None
    if (slope_id := settings.get(CONF_CURVE_SLOPE)) and (state := hass.states.get(slope_id)):
        try:
            slope = float(state.state)
        except ValueError:
            slope = None
    return await hass.async_add_executor_job(
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


async def async_run_rooms(
    hass: HomeAssistant, entry: ConfigEntry, start: datetime, end: datetime, *, days: tuple[float, ...] = ()
) -> tuple[RoomsReport, dict[str, str], list[str], list[RoomsReport]]:
    """Room analysis over ``[start, end)``.

    Returns (report, room name → valve entity, unmatched valves, extra reports). Each value in
    ``days`` adds a report over the last N days, computed from the same loaded data, so every
    thermostat and valve is read from the recorder only once.
    """
    settings = settings_of(entry)
    room_ids = settings.get(CONF_ROOMS) or []
    rooms = {}
    for entity_id in room_ids:
        attrs = await async_load_attribute_samples(
            hass, entity_id, ("current_temperature", "temperature"), start, end
        )
        rooms[entity_name(hass, entity_id)] = (attrs["current_temperature"], attrs["temperature"])

    valve_ids = settings.get(CONF_VALVES) or []
    matched, unmatched = match_valves(
        {e: _place(hass, e) for e in room_ids}, {v: _place(hass, v) for v in valve_ids}
    )
    valves = {}
    valve_of: dict[str, str] = {}
    for valve_id, room_id in matched.items():
        room = entity_name(hass, room_id)
        if room not in valves:  # one valve per room is enough for the open share
            valves[room] = await async_load_samples(hass, valve_id, start, end)
            valve_of[room] = valve_id
    tz = dt_util.get_default_time_zone()
    stop = end.timestamp()

    def run() -> tuple[RoomsReport, list[RoomsReport]]:
        main = analyze_rooms(rooms, start.timestamp(), stop, valves=valves or None, tz=tz)
        extra = [analyze_rooms(rooms, stop - d * 86400.0, stop, valves=valves or None, tz=tz) for d in days]
        return main, extra

    report, extra = await hass.async_add_executor_job(run)
    return report, valve_of, unmatched, extra
