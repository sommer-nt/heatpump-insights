"""Load recorder history and convert it to analysis samples."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.recorder import get_instance, history
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State

from .analysis import Sample

_TO_WATT = {"W": 1.0, "kW": 1000.0, "MW": 1e6}


def _factor(hass: HomeAssistant, entity_id: str) -> tuple[float, float]:
    """Return (scale, offset) that converts the entity's unit to W or °C."""
    state = hass.states.get(entity_id)
    unit = state.attributes.get("unit_of_measurement") if state else None
    if unit in _TO_WATT:
        return _TO_WATT[unit], 0.0
    if unit == "°F":
        return 5 / 9, -32 * 5 / 9
    return 1.0, 0.0


def _to_sample(state: State, scale: float, offset: float) -> Sample:
    ts = state.last_changed.timestamp()
    if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
        return Sample(ts, None)
    try:
        return Sample(ts, float(state.state) * scale + offset)
    except ValueError:
        return Sample(ts, None)


async def async_load_samples(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> list[Sample]:
    """All state changes of ``entity_id`` in the window, including the state at ``start``."""
    states = await get_instance(hass).async_add_executor_job(
        history.state_changes_during_period,
        hass,
        start,
        end,
        entity_id,
        True,  # no_attributes
        False,  # descending
        None,  # limit
        True,  # include_start_time_state
    )
    scale, offset = _factor(hass, entity_id)
    return [_to_sample(s, scale, offset) for s in states.get(entity_id.lower(), [])]
