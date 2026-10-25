"""Tests for the room comfort analysis."""

from datetime import UTC, datetime

import pytest

from analysis import Sample, analyze_rooms

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
