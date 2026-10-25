"""Role discovery across vendors: the same rules must work for every heat pump."""

from analysis.discovery import EntityInfo, discover_roles, normalize, room_candidates


def T(entity_id, name, unit="°C", device_class="temperature", **kw):
    return EntityInfo(entity_id, name, device_class=device_class, unit=unit, state_class="measurement", **kw)


def P(entity_id, name, **kw):
    return EntityInfo(entity_id, name, device_class="power", unit="W", state_class="measurement", **kw)


def E(entity_id, name, **kw):
    return EntityInfo(
        entity_id, name, device_class="energy", unit="kWh", state_class="total_increasing", **kw
    )


# Things every house has that must never be taken for the heat pump.
DISTRACTORS = [
    P("sensor.pv_power", "PV Leistung", platform="fronius"),
    P("sensor.house_consumption", "Hausverbrauch", platform="shelly"),
    T("sensor.living_room_temperature", "Living room temperature", platform="zha"),
    T("sensor.dhw_tank_temperature", "Hot water tank temperature", platform="mqtt"),
    E("sensor.grid_import", "Grid import energy", platform="shelly"),
]


def _suggested(entities):
    return {role: entry["suggested"] for role, entry in discover_roles(entities + DISTRACTORS).items()}


def test_normalize_folds_umlauts_and_separators():
    assert normalize("Außen-Temperatur HK1") == " aussen temperatur hk 1 "


def test_stiebel_eltron_isg_english_keys():
    dev = {"platform": "stiebel_eltron_isg", "device_name": "Stiebel Eltron WPM"}
    s = _suggested(
        [
            P("sensor.meter_heat_pump_power", "Energiemeter Wärmepumpe Leistung", platform="shelly"),
            T("sensor.isg_outdoor_temperature", "Außentemperatur", **dev),
            T("sensor.isg_flow_temperature_wp", "Vorlauftemperatur WP", **dev),
            T("sensor.isg_return_temperature_wp1", "Rücklauftemperatur WP1", **dev),
            T("sensor.isg_actual_temperature_hk_1", "Isttemperatur HK 1", **dev),
            T("sensor.isg_target_temperature_hk_1", "Solltemperatur HK 1", **dev),
            E("sensor.isg_produced_heating_total", "Wärmemenge Heizen gesamt", **dev),
            E("sensor.isg_produced_water_heating_total", "Wärmemenge Warmwasser gesamt", **dev),
            E("sensor.isg_produced_heating_today", "Wärmemenge Heizen heute", **dev),
            EntityInfo("number.isg_heating_curve_rise_hk1", "Heizkurve Steigung HK1", **dev),
            T("sensor.isg_hot_gas_temperature_wp1", "Heißgastemperatur WP1", **dev),
            EntityInfo(
                "sensor.isg_high_pressure_wp1", "Hochdruck WP1", device_class="pressure", unit="bar", **dev
            ),
        ]
    )
    assert s == {
        "power_entity": "sensor.meter_heat_pump_power",
        "outdoor_temp_entity": "sensor.isg_outdoor_temperature",
        "flow_temp_entity": "sensor.isg_flow_temperature_wp",
        "return_temp_entity": "sensor.isg_return_temperature_wp1",
        "circuit_flow_temp_entity": "sensor.isg_actual_temperature_hk_1",
        "circuit_flow_target_entity": "sensor.isg_target_temperature_hk_1",
        "heat_energy_entity": "sensor.isg_produced_heating_total",
        "curve_slope_entity": "number.isg_heating_curve_rise_hk1",
        "high_pressure_entity": "sensor.isg_high_pressure_wp1",
        "hot_gas_temp_entity": "sensor.isg_hot_gas_temperature_wp1",
    }


def test_viessmann_vicare():
    dev = {"platform": "vicare", "device_name": "Vitocal 250-A"}
    s = _suggested(
        [
            T("sensor.vitocal_outside_temperature", "Outside temperature", **dev),
            T("sensor.vitocal_supply_temperature", "Supply temperature", **dev),
            T("sensor.vitocal_return_temperature", "Return temperature", **dev),
            T(
                "sensor.vitocal_heating_circuit_0_supply_temperature",
                "Heating circuit 0 supply temperature",
                **dev,
            ),
            T("sensor.vitocal_dhw_storage_temperature", "DHW storage temperature", **dev),
            EntityInfo("number.vitocal_heating_curve_slope", "Heating curve slope", **dev),
            EntityInfo("number.vitocal_heating_curve_shift", "Heating curve shift", **dev),
            P("sensor.vitocal_power_consumption", "Power consumption", **dev),
        ]
    )
    assert s["outdoor_temp_entity"] == "sensor.vitocal_outside_temperature"
    assert s["flow_temp_entity"] == "sensor.vitocal_supply_temperature"
    assert s["return_temp_entity"] == "sensor.vitocal_return_temperature"
    assert s["circuit_flow_temp_entity"] == "sensor.vitocal_heating_circuit_0_supply_temperature"
    assert s["curve_slope_entity"] == "number.vitocal_heating_curve_slope"
    assert s["power_entity"] == "sensor.vitocal_power_consumption"


def test_daikin_and_panasonic_wording():
    daikin = {"platform": "daikin_onecta", "device_name": "Altherma"}
    pana = {"platform": "mqtt", "device_name": "Panasonic Heat Pump (HeishaMon)"}
    s = _suggested(
        [
            T("sensor.altherma_leaving_water_temperature", "Leaving water temperature", **daikin),
            T("sensor.altherma_outdoor_temperature", "Outdoor temperature", **daikin),
        ]
    )
    assert s["flow_temp_entity"] == "sensor.altherma_leaving_water_temperature"
    assert s["outdoor_temp_entity"] == "sensor.altherma_outdoor_temperature"
    s = _suggested(
        [
            T("sensor.panasonic_main_outlet_temp", "Main outlet temp", **pana),
            T("sensor.panasonic_main_inlet_temp", "Main inlet temp", **pana),
            T("sensor.panasonic_outside_temp", "Outside temp", **pana),
            T("sensor.panasonic_z1_water_target_temp", "Z1 water target temp", **pana),
        ]
    )
    assert s["flow_temp_entity"] == "sensor.panasonic_main_outlet_temp"
    assert s["return_temp_entity"] == "sensor.panasonic_main_inlet_temp"
    assert s["circuit_flow_target_entity"] == "sensor.panasonic_z1_water_target_temp"


def test_german_and_french_names_without_device_class():
    lux = {"platform": "luxtronik", "device_name": "Alpha Innotec"}
    s = _suggested(
        [
            EntityInfo("sensor.lux_vorlauf", "Vorlauf", unit="°C", **lux),
            EntityInfo("sensor.lux_ruecklauf", "Rücklauf", unit="°C", **lux),
            EntityInfo("sensor.lux_aussentemperatur", "Außentemperatur", unit="°C", **lux),
            EntityInfo("sensor.lux_ruecklauf_soll", "Rücklauf Soll", unit="°C", **lux),
        ]
    )
    assert s["flow_temp_entity"] == "sensor.lux_vorlauf"
    assert s["return_temp_entity"] == "sensor.lux_ruecklauf"
    assert s["outdoor_temp_entity"] == "sensor.lux_aussentemperatur"
    s = _suggested(
        [
            T("sensor.pac_temperature_exterieure", "Température extérieure", platform="atlantic"),
            T("sensor.pac_temperature_depart", "Température départ", platform="atlantic"),
        ]
    )
    assert s["outdoor_temp_entity"] == "sensor.pac_temperature_exterieure"
    assert s["flow_temp_entity"] == "sensor.pac_temperature_depart"


def test_distractors_are_never_suggested_and_ambiguity_is_not_guessed():
    s = _suggested([])
    assert all(v is None for v in s.values())
    # Two equally good power meters: no suggestion, both offered.
    roles = discover_roles(
        [
            P("sensor.heat_pump_power_a", "Heat pump power"),
            P("sensor.heat_pump_power_b", "Heat pump power"),
        ]
    )
    assert roles["power_entity"]["suggested"] is None
    assert len(roles["power_entity"]["candidates"]) == 2


def test_room_candidates_skip_the_heat_pump_climate():
    entities = [
        EntityInfo("climate.wohnzimmer", "Wandthermostat Wohnzimmer", platform="homematicip_cloud"),
        EntityInfo("climate.vitocal_heating", "Heating", platform="vicare", device_name="Vitocal"),
        EntityInfo("climate.bath", "Bath", platform="tado"),
    ]
    assert room_candidates(entities) == ["climate.wohnzimmer", "climate.bath"]


def test_vaillant_mypyllant():
    dev = {"platform": "mypyllant", "device_name": "aroTHERM plus"}
    s = _suggested(
        [
            T("sensor.home_outdoor_temperature", "Home Outdoor Temperature", **dev),
            T("sensor.home_circuit_0_flow_temperature", "Circuit 0 Flow Temperature", **dev),
            EntityInfo("sensor.home_circuit_0_heating_curve", "Circuit 0 Heating Curve", **dev),
            T(
                "sensor.home_domestic_hot_water_tank_temperature",
                "Domestic Hot Water Tank Temperature",
                **dev,
            ),
            E("sensor.arotherm_heating_energy_generated", "Heating Energy Generated", **dev),
            E("sensor.arotherm_heating_energy_consumed", "Heating Energy Consumed", **dev),
        ]
    )
    assert s["outdoor_temp_entity"] == "sensor.home_outdoor_temperature"
    assert s["circuit_flow_temp_entity"] == "sensor.home_circuit_0_flow_temperature"
    assert s["curve_slope_entity"] == "sensor.home_circuit_0_heating_curve"
    assert s["heat_energy_entity"] == "sensor.arotherm_heating_energy_generated"


def test_buderus_bosch_junkers_ems_esp():
    # EMS-ESP calls the heat generator "boiler" – that is not the hot water tank.
    dev = {"platform": "mqtt", "device_name": "EMS-ESP Boiler"}
    s = _suggested(
        [
            T("sensor.boiler_outside_temperature", "Boiler Outside temperature", **dev),
            T("sensor.boiler_current_flow_temperature", "Boiler Current flow temperature", **dev),
            T("sensor.boiler_selected_flow_temperature", "Boiler Selected flow temperature", **dev),
            T("sensor.boiler_return_temperature", "Boiler Return temperature", **dev),
            T("sensor.boiler_dhw_current_intern_temperature", "Boiler DHW current intern temperature", **dev),
        ]
    )
    assert s["outdoor_temp_entity"] == "sensor.boiler_outside_temperature"
    assert s["flow_temp_entity"] == "sensor.boiler_current_flow_temperature"
    assert s["return_temp_entity"] == "sensor.boiler_return_temperature"
    assert s["circuit_flow_target_entity"] == "sensor.boiler_selected_flow_temperature"


def test_wolf_weishaupt_german_and_ebusd_camel_case():
    wolf = {"platform": "wolflink", "device_name": "Wolf CHA"}
    s = _suggested(
        [
            T("sensor.wolf_aussentemperatur", "Außentemperatur", **wolf),
            T("sensor.wolf_vorlauftemperatur", "Vorlauftemperatur", **wolf),
            T("sensor.wolf_ruecklauftemperatur", "Rücklauftemperatur", **wolf),
            T("sensor.wolf_warmwassertemperatur", "Warmwassertemperatur", **wolf),
        ]
    )
    assert s["outdoor_temp_entity"] == "sensor.wolf_aussentemperatur"
    assert s["flow_temp_entity"] == "sensor.wolf_vorlauftemperatur"
    assert s["return_temp_entity"] == "sensor.wolf_ruecklauftemperatur"
    s = _suggested(
        [
            T("sensor.weishaupt_wwp_aussentemperatur", "WWP Außentemperatur", platform="weishaupt_modbus"),
            T("sensor.weishaupt_wwp_vorlauftemperatur", "WWP Vorlauftemperatur", platform="weishaupt_modbus"),
            T("sensor.weishaupt_hk1_vorlauf_soll", "HK1 Vorlauf Soll", platform="weishaupt_modbus"),
        ]
    )
    assert s["outdoor_temp_entity"] == "sensor.weishaupt_wwp_aussentemperatur"
    assert s["flow_temp_entity"] == "sensor.weishaupt_wwp_vorlauftemperatur"
    assert s["circuit_flow_target_entity"] == "sensor.weishaupt_hk1_vorlauf_soll"
    s = _suggested(
        [
            T("sensor.ebusd_hmu_flowtemp", "hmu FlowTemp", platform="mqtt"),
            T("sensor.ebusd_hmu_returntemp", "hmu ReturnTemp", platform="mqtt"),
            T("sensor.ebusd_broadcast_outsidetemp", "broadcast outsidetemp", platform="mqtt"),
        ]
    )
    assert s["flow_temp_entity"] == "sensor.ebusd_hmu_flowtemp"
    assert s["return_temp_entity"] == "sensor.ebusd_hmu_returntemp"
    assert s["outdoor_temp_entity"] == "sensor.ebusd_broadcast_outsidetemp"
