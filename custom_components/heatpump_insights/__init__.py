"""Heat Pump Insights: expert heat pump analysis tools for AI assistants."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .llm_api import HeatPumpInsightsAPI

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the LLM API once; every config entry is one heat pump inside it."""
    llm.async_register_api(hass, HeatPumpInsightsAPI(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tools read the entry's roles on every call; the optional valve bridge adds entities."""
    # This integration creates no devices. Detach devices created by v0.3.0's valve sensors.
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
