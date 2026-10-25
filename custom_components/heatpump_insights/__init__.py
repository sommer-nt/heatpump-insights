"""Heat Pump Insights: expert heating analysis for dashboards and AI assistants."""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import InsightsCoordinator
from .llm_api import HeatPumpInsightsAPI

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
STRATEGY_URL = f"/{DOMAIN}/heatpump-insights-strategy.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the LLM API and the dashboard strategy once for all heat pumps."""
    llm.async_register_api(hass, HeatPumpInsightsAPI(hass))
    await _async_register_strategy(hass)
    return True


async def _async_register_strategy(hass: HomeAssistant) -> None:
    """Serve the dashboard strategy and load it in the frontend (always present in a normal HA)."""
    if "frontend" not in hass.config.components or "http" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    strategy = Path(__file__).parent / "frontend" / "heatpump-insights-strategy.js"
    await hass.http.async_register_static_paths([StaticPathConfig(STRATEGY_URL, str(strategy), False)])
    version = (await hass.async_add_executor_job(strategy.stat)).st_mtime_ns
    add_extra_js_url(hass, f"{STRATEGY_URL}?v={version}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # v0.3.0 attached valve sensors to devices it created with Homematic IP identifiers.
    # Detach this entry from any device that is not its own.
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not any(domain == DOMAIN for domain, _ in device.identifiers):
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)

    coordinator = InsightsCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
