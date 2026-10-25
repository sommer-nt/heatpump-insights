"""Heat Pump Insights: expert heat pump analysis tools for AI assistants."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import llm
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .llm_api import HeatPumpInsightsAPI

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the LLM API once; every config entry is one heat pump inside it."""
    llm.async_register_api(hass, HeatPumpInsightsAPI(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to set up per entry: tools read the entry's roles on every call."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
