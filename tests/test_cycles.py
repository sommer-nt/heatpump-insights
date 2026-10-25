"""Tests for compressor cycle detection and rating."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from analysis import CycleConfig, Sample, analyze_cycles
from analysis.cycles import auto_threshold, detect_cycles
from analysis.timeseries import day_bounds, segments
from synth import constant, periodic_runs, power_series

T0 = datetime(2026, 1, 12, tzinfo=UTC).timestamp()
DAY = 86400.0


def test_long_cycles_are_rated_good():
    runs = periodic_runs(6 * 3600, 3 * 3600, 1200, 2 * DAY, first_offset_s=1800)
    power = power_series(T0, T0 + 2 * DAY, runs, noise_w=100)
    r = analyze_cycles(power, T0, T0 + 2 * DAY)
    assert r.cycles_complete == 8
    assert r.short_cycle_share == 0
    assert r.run_time_min["median"] == pytest.approx(180, abs=1)
    assert r.starts_per_day == 4
    assert r.rating == "good"


def test_short_cycling_is_rated_problem():
    runs = periodic_runs(1800, 360, 900, DAY, first_offset_s=600)
    power = power_series(T0, T0 + DAY, runs)
    r = analyze_cycles(power, T0, T0 + DAY)
    assert r.cycles_complete == 48
    assert r.short_cycle_share == 1.0
    assert r.max_starts_in_one_hour == 2
    assert r.rating == "problem"
    assert {f.code for f in r.findings} >= {"short_cycling"}


def test_many_starts_per_hour_flagged():
    runs = periodic_runs(900, 420, 900, DAY, first_offset_s=300)
    r = analyze_cycles(power_series(T0, T0 + DAY, runs), T0, T0 + DAY)
    assert r.max_starts_in_one_hour == 4
    assert "many_starts_per_hour" in {f.code for f in r.findings}


def test_short_dip_is_bridged_and_blip_is_ignored():
    runs = [(3600, 1800, 1000), (5460, 1800, 1000), (20000, 30, 1000)]  # 60 s dip, 30 s blip
    power = power_series(T0, T0 + DAY, runs)
    cycles = detect_cycles(power, T0, T0 + DAY, 300, CycleConfig())
    assert len(cycles) == 1
    assert cycles[0].duration_s == pytest.approx(3660, abs=10)
    assert not cycles[0].truncated


def test_runs_at_window_edges_are_truncated_and_excluded_from_stats():
    runs = [(0, 1200, 1000), (40000, 2400, 1000), (DAY - 600, 600, 1000)]
    power = power_series(T0 - 600, T0 + DAY, runs=[(r[0] + 600, r[1], r[2]) for r in runs])
    r = analyze_cycles(power, T0, T0 + DAY, cfg=CycleConfig(on_threshold_w=300))
    assert r.cycles_total == 3
    assert r.cycles_complete == 1


def test_unavailable_gap_truncates_run():
    power = [Sample(T0, 40), Sample(T0 + 3600, 1000), Sample(T0 + 5400, None), Sample(T0 + 9000, 40)]
    cycles = detect_cycles(power, T0, T0 + DAY, 300, CycleConfig())
    assert len(cycles) == 1 and cycles[0].truncated
    r = analyze_cycles(power, T0, T0 + DAY, cfg=CycleConfig(on_threshold_w=300))
    assert r.coverage_share == pytest.approx(1 - 3600 / DAY, abs=1e-3)


def test_constant_power_has_no_distinct_levels():
    r = analyze_cycles(constant(T0, T0 + DAY, 45), T0, T0 + DAY)
    assert r.threshold_w is None
    assert r.threshold_method == "no_distinct_levels"
    assert r.rating == "insufficient_data"


def test_auto_threshold_separates_pump_from_compressor():
    # Idle 30 W, circulation pump alone 90 W, compressor at minimum modulation 350 W.
    runs = [(0, 20000, 90), (20000, 20000, 350), (40000, 20000, 1800)]
    segs = segments(power_series(T0, T0 + DAY, runs, idle_w=30), T0, T0 + DAY)
    threshold, method = auto_threshold(segs, 150)
    assert method == "auto"
    assert 90 < threshold < 350


def test_low_coverage_is_insufficient():
    runs = periodic_runs(1800, 360, 900, DAY / 2)
    power = [*power_series(T0, T0 + DAY / 2, runs), Sample(T0 + DAY / 2, None)]
    r = analyze_cycles(power, T0, T0 + DAY)
    assert r.coverage_share == pytest.approx(0.5, abs=0.01)
    assert r.rating == "insufficient_data"


def test_per_day_follows_local_calendar_including_dst():
    berlin = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 10, 24, tzinfo=berlin).timestamp()
    end = datetime(2026, 10, 27, tzinfo=berlin).timestamp()
    days = day_bounds(start, end, berlin)
    assert [d for d, _, _ in days] == ["2026-10-24", "2026-10-25", "2026-10-26"]
    assert days[1][2] - days[1][1] == 25 * 3600  # clocks go back on 25 October 2026


def test_outdoor_bins_and_mild_weather_finding():
    total = 4 * DAY
    # Two cold days with long runs, two mild days with frequent short runs.
    runs = periodic_runs(8 * 3600, 5 * 3600, 2000, 2 * DAY, first_offset_s=1800)
    runs += [(2 * DAY + o, d, w) for o, d, w in periodic_runs(2400, 480, 700, 2 * DAY, 300)]
    power = power_series(T0, T0 + total, runs, step_s=30)
    outdoor = constant(T0, T0 + 2 * DAY, -2.0) + constant(T0 + 2 * DAY, T0 + total, 10.0)
    r = analyze_cycles(power, T0, T0 + total, outdoor_temp=outdoor)
    assert [b["outdoor_temp_from"] for b in r.by_outdoor_temp] == [-3.0, 9.0]
    assert r.per_day[0]["outdoor_temp_mean"] == -2.0
    assert "cycling_at_mild_weather" in {f.code for f in r.findings}


def test_report_is_json_serialisable():
    import json

    runs = periodic_runs(1800, 360, 900, DAY)
    r = analyze_cycles(power_series(T0, T0 + DAY, runs), T0, T0 + DAY)
    json.dumps(r.as_dict())


def test_binary_on_off_signal_gets_automatic_threshold():
    runs = periodic_runs(1500, 240, 1, DAY, 300)  # burner state 0/1
    power = power_series(T0, T0 + DAY, runs, idle_w=0)
    r = analyze_cycles(power, T0, T0 + DAY)
    assert r.threshold_method == "binary"
    assert r.cycles_complete == 58  # runs at 300 s + k·1500 s within one day
    assert r.rating == "problem"


def test_short_cycling_needs_three_days_for_act():
    runs = periodic_runs(1800, 360, 900, DAY, first_offset_s=600)
    one_day = analyze_cycles(power_series(T0, T0 + DAY, runs), T0, T0 + DAY)
    assert next(f for f in one_day.findings if f.code == "short_cycling").severity == "check"
    runs = periodic_runs(1800, 360, 900, 4 * DAY, first_offset_s=600)
    four_days = analyze_cycles(power_series(T0, T0 + 4 * DAY, runs), T0, T0 + 4 * DAY)
    finding = next(f for f in four_days.findings if f.code == "short_cycling")
    assert finding.severity == "act"
    assert "4.0 days" in finding.evidence
