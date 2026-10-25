"""Tests for the heating curve fit."""

import json
import random
from datetime import UTC, datetime

import pytest

from analysis import CurveConfig, analyze_heating_curve
from analysis.heating_curve import theil_sen

T0 = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
H = 3600.0


def hourly(values):
    return {T0 + i * H: v for i, v in enumerate(values)}


def curve(t_out, slope=0.4, room=20.0, shift=0.0):
    return room + slope * (room - t_out) + shift


def outdoor_series(n=24 * 20, lo=-6.0, hi=12.0, seed=1):
    rng = random.Random(seed)
    return [rng.uniform(lo, hi) for _ in range(n)]


def test_recovers_slope_from_target_flow():
    out = outdoor_series()
    r = analyze_heating_curve(
        hourly(out), None, hourly([curve(t) for t in out]), start=T0, end=T0 + len(out) * H
    )
    assert r.source == "target"
    assert r.slope_k_per_k == pytest.approx(0.4, abs=0.01)
    assert r.flow_at_outdoor_c["+0"]["flow_c"] == pytest.approx(28.0, abs=0.1)
    assert r.flow_at_outdoor_c["-10"]["extrapolated"] is True
    assert r.r2 == pytest.approx(1.0, abs=1e-6)
    assert r.findings == []


def test_robust_against_hot_water_outliers():
    out = outdoor_series(seed=2)
    flow = [curve(t) for t in out]
    for i in range(0, len(flow), 12):  # every 12th hour: hot water, 55 °C
        flow[i] = 55.0
    r = analyze_heating_curve(hourly(out), hourly(flow), start=T0, end=T0 + len(out) * H)
    assert r.source == "actual"
    assert r.slope_k_per_k == pytest.approx(0.4, abs=0.03)


def test_narrow_outdoor_range_is_flagged():
    out = outdoor_series(lo=8, hi=12)
    r = analyze_heating_curve(hourly(out), hourly([curve(t) for t in out]), start=T0, end=T0)
    assert "narrow_outdoor_range" in {f.code for f in r.findings}


def test_tracking_detects_undersupply():
    out = outdoor_series(seed=3)
    target = [curve(t) for t in out]
    actual = [v - 3.0 if i % 2 else v for i, v in enumerate(target)]
    r = analyze_heating_curve(hourly(out), hourly(actual), hourly(target), start=T0, end=T0)
    assert r.tracking["undersupply_share"] == pytest.approx(0.5, abs=0.01)
    assert r.tracking["mean_actual_minus_target_k"] == pytest.approx(-1.5, abs=0.01)
    assert "poor_tracking" in {f.code for f in r.findings}


def test_too_few_hours():
    out = outdoor_series(n=10)
    r = analyze_heating_curve(hourly(out), hourly([curve(t) for t in out]), start=T0, end=T0)
    assert r.slope_k_per_k is None
    assert r.findings[0].code == "insufficient_data"


def test_warm_hours_can_be_excluded():
    out = outdoor_series(lo=-5, hi=20, seed=4)
    flow = [curve(t) if t < 15 else 20.0 for t in out]  # heating off above 15 °C
    r = analyze_heating_curve(hourly(out), hourly(flow), start=T0, end=T0, cfg=CurveConfig(max_outdoor_c=15))
    assert r.slope_k_per_k == pytest.approx(0.4, abs=0.01)
    assert r.outdoor_range_c["max"] <= 15


def test_theil_sen_thins_large_inputs():
    xs = [i / 10 for i in range(5000)]
    a, b = theil_sen(xs, [2 * x + 1 for x in xs])
    assert b == pytest.approx(2) and a == pytest.approx(1)


def test_report_is_json_serialisable():
    out = outdoor_series()
    r = analyze_heating_curve(hourly(out), hourly([curve(t) for t in out]), start=T0, end=T0)
    json.dumps(r.as_dict())
