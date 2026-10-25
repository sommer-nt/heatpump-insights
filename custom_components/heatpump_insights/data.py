"""Load recorder history and convert it to analysis samples."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.recorder import get_instance, history, statistics
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State

from .analysis import Sample
from .analysis.timeseries import segments, time_weighted_mean

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


async def async_load_hourly_means(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> dict[float, float]:
    """Hourly means keyed by hour start (UTC seconds), converted to W / °C.

    Uses long-term statistics (kept for months); falls back to the state history
    for sensors without statistics.
    """
    rows = await get_instance(hass).async_add_executor_job(
        statistics.statistics_during_period,
        hass,
        start,
        end,
        {entity_id},
        "hour",
        {"temperature": "°C", "power": "W"},
        {"mean"},
    )
    means = {row["start"]: row["mean"] for row in rows.get(entity_id, []) if row.get("mean") is not None}
    if means:
        return means
    samples = await async_load_samples(hass, entity_id, start, end)
    segs = segments(samples, start.timestamp(), end.timestamp())
    first = int(start.timestamp() // 3600 + 1) * 3600
    result = {}
    for hour in range(first, int(end.timestamp()) - 3599, 3600):
        mean = time_weighted_mean(segs, hour, hour + 3600)
        if mean is not None:
            result[float(hour)] = mean
    return result


async def async_load_attribute_samples(
    hass: HomeAssistant, entity_id: str, attribute: str, start: datetime, end: datetime
) -> list[Sample]:
    """A numeric attribute of every state change (e.g. a thermostat's current temperature)."""
    # state_changes_during_period skips attribute-only updates, which is exactly how
    # thermostats report a new room temperature; this query returns every update.
    states = await get_instance(hass).async_add_executor_job(
        history.get_significant_states,
        hass,
        start,
        end,
        [entity_id],
        None,  # filters
        True,  # include_start_time_state
        False,  # significant_changes_only
        False,  # minimal_response
        False,  # no_attributes
    )
    unit = hass.config.units.temperature_unit
    scale, offset = (5 / 9, -32 * 5 / 9) if unit == "°F" else (1.0, 0.0)
    samples = []
    for state in states.get(entity_id.lower(), []):
        value = state.attributes.get(attribute)
        try:
            number = float(value) * scale + offset if value is not None else None
        except (TypeError, ValueError):
            number = None
        if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            number = None
        samples.append(Sample(state.last_updated.timestamp(), number))
    return samples
