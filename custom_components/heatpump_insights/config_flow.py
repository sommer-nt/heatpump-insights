"""Config flow: map the user's sensors to vendor-independent roles."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CIRCUIT_FLOW,
    CONF_CIRCUIT_TARGET,
    CONF_CURVE_SLOPE,
    CONF_FLOW_TEMP,
    CONF_HEAT_ENERGY,
    CONF_HMIP_VALVES,
    CONF_ON_THRESHOLD_W,
    CONF_OUTDOOR_TEMP,
    CONF_POWER,
    CONF_RETURN_TEMP,
    CONF_ROOMS,
    CONF_SHORT_CYCLE_MIN,
    CONF_VALVES,
    DEFAULT_SHORT_CYCLE_MIN,
    DOMAIN,
)


def _sensor(device_class: str) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class=device_class))


def _roles_schema(values: dict[str, Any]) -> dict:
    def opt(key: str) -> probatio.Optional:
        return probatio.Optional(key, description={"suggested_value": values.get(key)})

    return {
        probatio.Required(CONF_POWER, description={"suggested_value": values.get(CONF_POWER)}): _sensor(
            "power"
        ),
        opt(CONF_OUTDOOR_TEMP): _sensor("temperature"),
        opt(CONF_FLOW_TEMP): _sensor("temperature"),
        opt(CONF_RETURN_TEMP): _sensor("temperature"),
        opt(CONF_HEAT_ENERGY): _sensor("energy"),
        opt(CONF_CIRCUIT_FLOW): _sensor("temperature"),
        opt(CONF_CIRCUIT_TARGET): _sensor("temperature"),
        opt(CONF_CURVE_SLOPE): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["number", "input_number", "sensor"])
        ),
        opt(CONF_ROOMS): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate", multiple=True)
        ),
        opt(CONF_VALVES): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "switch", "sensor"], multiple=True)
        ),
    }


def _tuning_schema(values: dict[str, Any]) -> dict:
    return {
        probatio.Optional(
            CONF_ON_THRESHOLD_W, description={"suggested_value": values.get(CONF_ON_THRESHOLD_W)}
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=5000, step=1, unit_of_measurement="W")
        ),
        probatio.Optional(
            CONF_HMIP_VALVES, default=values.get(CONF_HMIP_VALVES, False)
        ): selector.BooleanSelector(),
        probatio.Optional(
            CONF_SHORT_CYCLE_MIN,
            default=values.get(CONF_SHORT_CYCLE_MIN, DEFAULT_SHORT_CYCLE_MIN),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=3, max=30, step=1, unit_of_measurement="min")
        ),
    }


class HeatPumpInsightsConfigFlow(ConfigFlow, domain=DOMAIN):
    """One config entry per heat pump."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_POWER])
            self._abort_if_unique_id_configured()
            name = user_input.pop(CONF_NAME)
            return self.async_create_entry(title=name, data=user_input)
        schema = probatio.Schema(
            {probatio.Required(CONF_NAME, default="Heat pump"): str, **_roles_schema({})}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> HeatPumpInsightsOptionsFlow:
        return HeatPumpInsightsOptionsFlow()


class HeatPumpInsightsOptionsFlow(OptionsFlowWithReload):
    """Change role mapping and analysis tuning later."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        values = {**self.config_entry.data, **self.config_entry.options}
        schema = probatio.Schema({**_roles_schema(values), **_tuning_schema(values)})
        return self.async_show_form(step_id="init", data_schema=schema)
