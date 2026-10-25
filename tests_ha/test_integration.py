"""End-to-end: set the integration up in Home Assistant with a recorder and real history."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import llm
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

DOMAIN = "heatpump_insights"
OPTIONS = {
    "power_entity": "sensor.hp_power",
    "outdoor_temp_entity": "sensor.outdoor",
    "circuit_flow_temp_entity": "sensor.flow",
    "room_entities": ["climate.bath"],
    "valve_entities": ["switch.bath_valve"],
    "high_pressure_entity": "sensor.high_pressure",
    "short_cycle_minutes": 10,
}


async def _record_history(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Two days: compressor runs of 40 min every 3 h, a cold bath with its valve open."""
    start = dt_util.utcnow() - timedelta(days=2, minutes=10)
    freezer.move_to(start)
    for step in range(0, 2 * 24 * 6 + 1):  # every 10 minutes
        minute = step * 10
        running = (minute % 180) < 40
        hass.states.async_set(
            "sensor.hp_power",
            "900" if running else "40",
            {"unit_of_measurement": "W", "device_class": "power", "friendly_name": "Heat pump power"},
        )
        hass.states.async_set(
            "sensor.outdoor",
            "5",
            {
                "unit_of_measurement": "°C",
                "device_class": "temperature",
                "friendly_name": "Outdoor temperature",
            },
        )
        hass.states.async_set("sensor.flow", "30", {"unit_of_measurement": "°C"})
        hass.states.async_set(
            "climate.bath",
            "heat",
            {"current_temperature": 21.0 + (step % 2) * 0.1, "temperature": 23.0, "friendly_name": "Bath"},
        )
        hass.states.async_set("switch.bath_valve", "on", {"friendly_name": "Bath valve"})
        await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=10))
    await async_wait_recording_done(hass)


@pytest.fixture
async def setup_entry(hass: HomeAssistant, recorder_mock, freezer: FrozenDateTimeFactory):
    await _record_history(hass, freezer)
    entry = MockConfigEntry(domain=DOMAIN, title="Heat pump", data=OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensors_are_created_with_values(hass: HomeAssistant, setup_entry) -> None:
    registry = er.async_get(hass)
    own = {
        e.translation_key: e.entity_id
        for e in er.async_entries_for_config_entry(registry, setup_entry.entry_id)
    }
    for key in (
        "starts_today",
        "runtime_today",
        "starts_per_day",
        "cycling_rating",
        "curve_slope",
        "overheated_rooms",
        "limiting_room",
        "configuration",
    ):
        assert key in own, key
    starts = hass.states.get(own["starts_per_day"])
    assert float(starts.state) == pytest.approx(8, abs=1)  # one run every 3 hours
    rating = hass.states.get(own["cycling_rating"])
    # Two days of data in a 7-day window: the rating waits for more data instead of guessing.
    assert rating.state == "insufficient_data"
    assert rating.attributes["data_days"] == pytest.approx(2, abs=0.1)
    # Room statements also wait: unknown, not a guessed "none".
    assert hass.states.get(own["limiting_room"]).state == "unknown"
    assert hass.states.get(own["overheated_rooms"]).state == "unknown"
    config = hass.states.get(own["configuration"])
    assert config.attributes["roles"]["power_entity"] == "sensor.hp_power"
    assert config.attributes["roles"]["high_pressure_entity"] == "sensor.high_pressure"
    assert config.attributes["valves_by_room"] == {"Bath": "switch.bath_valve"}
    valve = next(
        e
        for e in er.async_entries_for_config_entry(registry, setup_entry.entry_id)
        if e.translation_key == "valve_open"
    )
    assert float(hass.states.get(valve.entity_id).state) == pytest.approx(100, abs=1)


async def test_llm_tools(hass: HomeAssistant, setup_entry) -> None:
    context = llm.LLMContext(
        platform="test", context=None, language="en", assistant="conversation", device_id=None
    )
    api = await llm.async_get_api(hass, DOMAIN, context)
    names = {tool.name for tool in api.tools}
    assert names == {
        "heatpump_describe",
        "heatpump_discover_sensors",
        "heatpump_analyze_cycles",
        "heatpump_heating_curve",
        "heating_rooms",
    }

    describe = await api.async_call_tool(llm.ToolInput("heatpump_describe", {}))
    pump = describe.data["heat_pumps"][0]
    assert pump["available_analyses"] == [
        "heatpump_analyze_cycles",
        "heatpump_heating_curve",
        "heating_rooms",
    ]

    rooms = await api.async_call_tool(llm.ToolInput("heating_rooms", {"days": 2}))
    codes = {f["code"]: f for f in rooms.data["findings"]}
    assert "limiting_room" in codes
    assert codes["limiting_room"]["severity"] == "info"
    # valve history is shorter than 3 days: valve statements are held back
    assert "insufficient_valve_history" in codes
    assert "undersupplied_room" not in codes

    found = await api.async_call_tool(llm.ToolInput("heatpump_discover_sensors", {}))
    assert found.data["roles"]["outdoor_temp_entity"]["suggested"] == "sensor.outdoor"
    assert found.data["room_thermostats"] == ["climate.bath"]

    cycles = await api.async_call_tool(llm.ToolInput("heatpump_analyze_cycles", {"days": 2}))
    assert cycles.data["cycles_complete"] >= 14


async def test_unload(hass: HomeAssistant, setup_entry) -> None:
    assert await hass.config_entries.async_unload(setup_entry.entry_id)


async def test_config_flow_creates_entry(hass: HomeAssistant, recorder_mock) -> None:
    hass.states.async_set(
        "sensor.hp_power",
        "40",
        {"unit_of_measurement": "W", "device_class": "power", "friendly_name": "Heat pump power"},
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == "form"
    # the form is pre-filled from role discovery
    suggested = {
        str(k): k.description["suggested_value"]
        for k in result["data_schema"].schema
        if isinstance(k.description, dict)
    }
    assert suggested["power_entity"] == "sensor.hp_power"
    with patch("custom_components.heatpump_insights.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Heat pump", "power_entity": "sensor.hp_power"}
        )
    assert result["type"] == "create_entry"
    assert result["data"] == {"power_entity": "sensor.hp_power"}
