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
CONF_CIRCUIT_FLOW = "circuit_flow_temp_entity"
CONF_CIRCUIT_TARGET = "circuit_flow_target_entity"
CONF_CURVE_SLOPE = "curve_slope_entity"
CONF_HIGH_PRESSURE = "high_pressure_entity"
CONF_HOT_GAS = "hot_gas_temp_entity"
CONF_ROOMS = "room_entities"
CONF_VALVES = "valve_entities"
CONF_HMIP_VALVES = "hmip_valve_sensors"

ROLES = {
    CONF_POWER: "Electrical power of the heat pump (required)",
    CONF_OUTDOOR_TEMP: "Outdoor temperature",
    CONF_FLOW_TEMP: "Flow (supply) water temperature",
    CONF_RETURN_TEMP: "Return water temperature",
    CONF_HEAT_ENERGY: "Heat energy meter (thermal kWh)",
    CONF_CIRCUIT_FLOW: "Heating circuit flow temperature (what the heating curve controls)",
    CONF_CIRCUIT_TARGET: "Target flow temperature calculated by the controller",
    CONF_CURVE_SLOPE: "Heating curve slope setting",
    CONF_HIGH_PRESSURE: "Refrigerant high pressure",
    CONF_HOT_GAS: "Hot gas (compressor discharge) temperature",
    CONF_ROOMS: "Room thermostats (climate entities)",
    CONF_VALVES: "Valve or actuator state per heating circuit (on = open)",
}

# Which analysis each optional role unlocks, so the assistant can tell the user
# what an extra sensor would be worth.
ROLE_UNLOCKS = {
    CONF_OUTDOOR_TEMP: "cycling vs. weather, heating curve (energy signature planned)",
    CONF_FLOW_TEMP: "heating curve analysis (fallback if no heating circuit flow is assigned)",
    CONF_RETURN_TEMP: "flow/return spread (analysis planned, not yet available)",
    CONF_HEAT_ENERGY: "real COP / seasonal performance factor (analysis planned, not yet available)",
    CONF_CIRCUIT_FLOW: "heating curve analysis (actual curve)",
    CONF_CIRCUIT_TARGET: "heating curve analysis (controller curve, delivery check)",
    CONF_ROOMS: "room comfort: overheated rooms, the room that limits the curve",
    CONF_VALVES: "undersupplied rooms (valve open but cold), number of open circuits",
    CONF_HIGH_PRESSURE: "compressor view on the dashboard (limit check planned, not yet available)",
    CONF_HOT_GAS: "compressor view on the dashboard (limit check planned, not yet available)",
}

CONF_ON_THRESHOLD_W = "on_threshold_w"
CONF_SHORT_CYCLE_MIN = "short_cycle_minutes"
DEFAULT_SHORT_CYCLE_MIN = 10

MAX_DAYS = 10
"""Home Assistant keeps full-resolution history for 10 days by default."""

MAX_CURVE_DAYS = 60
"""The curve uses hourly long-term statistics, which are kept much longer."""
