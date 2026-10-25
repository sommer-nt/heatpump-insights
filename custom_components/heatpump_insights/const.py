"""Constants for Heat Pump Insights."""

DOMAIN = "heatpump_insights"
LLM_API_ID = DOMAIN
LLM_API_NAME = "Heat Pump Insights"

# Roles: what a sensor *means* for the analysis, independent of the vendor.
CONF_POWER = "power_entity"
CONF_OUTDOOR_TEMP = "outdoor_temp_entity"
CONF_FLOW_TEMP = "flow_temp_entity"
CONF_RETURN_TEMP = "return_temp_entity"
CONF_HEAT_ENERGY = "heat_energy_entity"

ROLES = {
    CONF_POWER: "Electrical power of the heat pump (required)",
    CONF_OUTDOOR_TEMP: "Outdoor temperature",
    CONF_FLOW_TEMP: "Flow (supply) water temperature",
    CONF_RETURN_TEMP: "Return water temperature",
    CONF_HEAT_ENERGY: "Heat energy meter (thermal kWh)",
}

# Which analysis each optional role unlocks, so the assistant can tell the user
# what an extra sensor would be worth.
ROLE_UNLOCKS = {
    CONF_OUTDOOR_TEMP: "cycling vs. weather, energy signature, heating curve",
    CONF_FLOW_TEMP: "heating curve analysis",
    CONF_RETURN_TEMP: "flow/return spread",
    CONF_HEAT_ENERGY: "real COP / seasonal performance factor",
}

CONF_ON_THRESHOLD_W = "on_threshold_w"
CONF_SHORT_CYCLE_MIN = "short_cycle_minutes"
DEFAULT_SHORT_CYCLE_MIN = 10

MAX_DAYS = 10
"""Home Assistant keeps full-resolution history for 10 days by default."""
