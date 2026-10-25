"""Tests for the room comfort analysis."""

from datetime import UTC, datetime

import pytest

from analysis import Sample, analyze_rooms
from analysis.rooms import match_valves

T0 = datetime(2026, 1, 12, tzinfo=UTC).timestamp()
DAY = 86400.0


def flat(value, start=T0):
    return [Sample(start, value)]


def test_overheated_rooms_and_limiting_room():
    rooms = {
        "Living": (flat(22.5), flat(21.0)),
        "Kitchen": (flat(22.4), flat(21.0)),
        "Bedroom": (flat(19.0), flat(18.0)),
        "Bath": (flat(21.0), flat(23.0)),
    }
    r = analyze_rooms(rooms, T0, T0 + DAY)
    codes = {f.code for f in r.findings}
    assert set(r.overheated_rooms) == {"Living", "Kitchen"}
    assert "rooms_overheated" in codes
    assert r.limiting_room == "Bath"
    assert r.rooms[0]["room"] == "Bath"  # sorted by deviation, coldest first
    bath = r.rooms[0]
    assert bath["deviation_mean_k"] == pytest.approx(-2.0)
    assert bath["too_cold_share"] == pytest.approx(1.0)


def test_setpoint_changes_are_followed():
    actual = flat(20.0)
    setpoint = [Sample(T0, 20.0), Sample(T0 + DAY / 2, 22.0)]  # comfort period in 2nd half
    r = analyze_rooms({"Office": (actual, setpoint)}, T0, T0 + DAY)
    office = r.rooms[0]
    assert office["too_cold_share"] == pytest.approx(0.5)
    assert office["setpoint_mean_c"] == pytest.approx(21.0)


def test_rooms_with_little_data_are_not_rated():
    rooms = {
        "Good": (flat(21.0), flat(21.0)),
        "Gappy": ([Sample(T0, 18.0), Sample(T0 + DAY / 5, None)], flat(22.0)),
    }
    r = analyze_rooms(rooms, T0, T0 + DAY)
    assert "low_coverage" in {f.code for f in r.findings}
    assert r.limiting_room is None
    assert r.overheated_rooms == []


def test_all_comfortable():
    r = analyze_rooms({"A": (flat(21.2), flat(21.0)), "B": (flat(20.8), flat(21.0))}, T0, T0 + DAY)
    assert r.findings == []


def test_valve_open_but_cold_is_undersupplied():
    rooms = {"Bath": (flat(21.0), flat(23.0)), "Living": (flat(21.0), flat(21.0))}
    valves = {
        "Bath": [Sample(T0, 1.0)],
        "Living": [Sample(T0, 1.0), Sample(T0 + DAY, 0.0)],
    }
    r = analyze_rooms(rooms, T0, T0 + 4 * DAY, valves=valves)
    by_room = {x["room"]: x for x in r.rooms}
    assert by_room["Bath"]["valve_open_share"] == pytest.approx(1.0)
    assert by_room["Living"]["valve_open_share"] == pytest.approx(0.25)
    assert "undersupplied_room" in {f.code for f in r.findings}
    assert r.valves["mean_open"] == pytest.approx(1.25)


def test_power_readings_count_as_open_and_few_open_circuits():
    names = ["A", "B", "C", "D"]
    rooms = {n: (flat(21.0), flat(21.0)) for n in names}
    valves = {n: [Sample(T0, 0.0)] for n in names}
    valves["A"] = [Sample(T0, 1.8)]  # actuator draws 1.8 W = open
    r = analyze_rooms(rooms, T0, T0 + 4 * DAY, valves=valves)
    assert r.valves == {"circuits": 4, "mean_open": 1.0, "at_most_one_open_share": 1.0}
    assert "few_open_circuits" in {f.code for f in r.findings}


def test_match_valves_by_group_area_and_name():
    rooms = {
        "climate.wohnzimmer": ("Wandthermostat Wohnzimmer", "wohnzimmer", "Wohnzimmer"),
        "climate.kuche": ("Wandthermostat Küche", "kuche", "Küchenstudio"),
        "climate.flur": ("Wandthermostat Flur", "flur", "Flur"),
        "climate.flur_dg": ("Flur Dachgeschoss", "flur_dg", "Flur Dachgeschoss"),
    }
    valves = {
        "binary_sensor.wth_wohnen_valve": ("Wandthermostat Wohnen Ventil", None, "Wohnzimmer"),
        "switch.fsm_kuche": ("Schaltaktor Stellregler FBH Küche", None, None),
        "switch.in_area": ("Aktor 7", "flur", None),
        "switch.fsm_flur_dg": ("Schaltaktor FBH Flur DG", None, None),
    }
    matched, unmatched = match_valves(rooms, valves)
    assert matched["binary_sensor.wth_wohnen_valve"] == "climate.wohnzimmer"
    assert matched["switch.fsm_kuche"] == "climate.kuche"
    assert matched["switch.in_area"] == "climate.flur"
    assert unmatched == ["switch.fsm_flur_dg"]  # "Flur" fits two rooms: left to the user


def test_short_valve_history_holds_back_valve_findings():
    rooms = {"Bath": (flat(21.0), flat(23.0)), "Living": (flat(21.0), flat(21.0))}
    valves = {"Bath": [Sample(T0 + DAY - 3600, 1.0)], "Living": [Sample(T0 + DAY - 3600, 0.0)]}
    r = analyze_rooms(rooms, T0, T0 + DAY, valves=valves)
    codes = {f.code for f in r.findings}
    assert "insufficient_valve_history" in codes
    assert "undersupplied_room" not in codes


def test_limiting_room_names_high_setpoint_as_simple_explanation():
    rooms = {
        "Bath": (flat(21.5), flat(23.0)),
        "Living": (flat(21.0), flat(21.0)),
        "Office": (flat(21.0), flat(21.0)),
    }
    r = analyze_rooms(rooms, T0, T0 + DAY)
    finding = next(f for f in r.findings if f.code == "limiting_room")
    assert finding.severity == "info"
    assert "simplest explanation" in finding.message
    assert all(f.severity in {"info", "check"} for f in r.findings)  # rooms never reach "act"
