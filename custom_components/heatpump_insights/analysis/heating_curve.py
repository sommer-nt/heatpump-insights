"""Heating curve analysis: how does the flow temperature really follow the weather?

Works on hourly means (Home Assistant long-term statistics), so it can look at
whole weeks or months. If the controller exposes its own target flow
temperature, the curve is fitted on that target (the controller's curve,
undisturbed by hot water or defrost) and the actual flow is used to judge how
well the curve is delivered.

See ``docs/knowledge/heating-curve.md`` for the reasoning behind the defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, tzinfo
from statistics import median, pstdev

from .cycles import ANALYSIS_VERSION, Finding

MAX_FIT_POINTS = 800
"""Theil–Sen is O(n²); thin evenly beyond this many hours."""


@dataclass(frozen=True, slots=True)
class CurveConfig:
    """Tunable parameters. Defaults are documented heuristics, not norms."""

    min_hours: int = 24
    """Fewer usable hours: no curve is reported."""

    min_outdoor_range_k: float = 8.0
    """Narrower outdoor temperature span: the slope is an extrapolation risk."""

    min_r2: float = 0.5
    """Below this the flow temperature does not follow the weather well."""

    undersupply_k: float = 2.0
    """Actual flow this far below target counts as an undersupplied hour."""

    max_outdoor_c: float | None = None
    """Ignore hours warmer than this (heating usually off). ``None``: keep all."""

    min_flow_c: float = 15.0
    """Flow values below this mean 'no heat requested' (controllers report frost-protection
    or placeholder targets such as 5 °C); such hours are left out."""


@dataclass(slots=True)
class CurveReport:
    analysis_version: str
    window_start: str
    window_end: str
    source: str
    """``target`` (controller's target flow) or ``actual`` (measured flow)."""
    hours_used: int
    hours_without_demand: int
    outdoor_range_c: dict[str, float] | None
    slope_k_per_k: float | None
    """Flow temperature rise per kelvin of colder outdoor temperature."""
    flow_at_outdoor_c: dict[str, dict] = field(default_factory=dict)
    r2: float | None = None
    residual_std_k: float | None = None
    tracking: dict | None = None
    current_curve_setting: float | None = None
    findings: list[Finding] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def theil_sen(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Robust line fit: median of pairwise slopes, median intercept."""
    n = len(xs)
    if n > MAX_FIT_POINTS:
        step = n / MAX_FIT_POINTS
        idx = [int(i * step) for i in range(MAX_FIT_POINTS)]
        xs = [xs[i] for i in idx]
        ys = [ys[i] for i in idx]
        n = len(xs)
    slopes = [
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(n)
        for j in range(i + 1, n)
        if abs(xs[j] - xs[i]) > 1e-9
    ]
    if not slopes:
        raise ValueError("all x values are equal")
    b = median(slopes)
    a = median(y - b * x for x, y in zip(xs, ys, strict=True))
    return a, b


def analyze_heating_curve(
    outdoor: Mapping[float, float],
    flow_actual: Mapping[float, float] | None,
    flow_target: Mapping[float, float] | None = None,
    *,
    start: float,
    end: float,
    tz: tzinfo = UTC,
    curve_setting: float | None = None,
    cfg: CurveConfig | None = None,
) -> CurveReport:
    """Fit the effective heating curve from hourly means keyed by hour start (UTC seconds)."""
    cfg = cfg or CurveConfig()

    def iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, UTC).astimezone(tz).isoformat(timespec="minutes")

    source = "target" if flow_target else "actual"
    flow = flow_target or flow_actual or {}
    candidates = [
        h for h in flow if h in outdoor and (cfg.max_outdoor_c is None or outdoor[h] <= cfg.max_outdoor_c)
    ]
    hours = sorted(h for h in candidates if flow[h] >= cfg.min_flow_c)
    report = CurveReport(
        analysis_version=ANALYSIS_VERSION,
        window_start=iso(start),
        window_end=iso(end),
        source=source,
        hours_used=len(hours),
        hours_without_demand=len(candidates) - len(hours),
        outdoor_range_c=None,
        slope_k_per_k=None,
        current_curve_setting=curve_setting,
        assumptions=[
            "Hourly means from Home Assistant statistics; one point per hour.",
            "Robust Theil–Sen line: single outliers (hot water, defrost) barely move it.",
            "Curve fitted on the controller's target flow."
            if source == "target"
            else "Curve fitted on the measured flow; hot-water or defrost hours may add scatter.",
            f"Hours with a flow value below {cfg.min_flow_c:.0f} °C count as 'no heat requested' "
            "and are left out.",
            "Vendor curve settings use their own scales; the fitted slope is in kelvin per kelvin "
            "and need not equal the controller's slope number.",
        ],
    )
    if len(hours) < cfg.min_hours:
        report.findings.append(
            Finding(
                "insufficient_data",
                "info",
                f"Only {len(hours)} hours with both flow and outdoor temperature (need {cfg.min_hours}).",
            )
        )
        return report

    xs = [outdoor[h] for h in hours]
    ys = [flow[h] for h in hours]
    lo, hi = min(xs), max(xs)
    report.outdoor_range_c = {"min": round(lo, 1), "max": round(hi, 1)}
    try:
        a, b = theil_sen(xs, ys)
    except ValueError:
        report.findings.append(
            Finding("insufficient_data", "info", "Outdoor temperature did not vary in the window.")
        )
        return report

    residuals = [y - (a + b * x) for x, y in zip(xs, ys, strict=True)]
    mean_y = sum(ys) / len(ys)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum(r * r for r in residuals)
    report.slope_k_per_k = round(-b, 3)
    report.r2 = round(1 - ss_res / ss_tot, 3) if ss_tot > 0 else None
    report.residual_std_k = round(pstdev(residuals), 2)
    for t in (10.0, 0.0, -10.0):
        report.flow_at_outdoor_c[f"{t:+.0f}"] = {
            "flow_c": round(a + b * t, 1),
            "extrapolated": not (lo <= t <= hi),
        }

    if flow_target and flow_actual:
        both = [h for h in hours if h in flow_actual]
        if both:
            diffs = [flow_actual[h] - flow_target[h] for h in both]
            report.tracking = {
                "hours": len(both),
                "mean_actual_minus_target_k": round(sum(diffs) / len(diffs), 2),
                "undersupply_share": round(sum(d < -cfg.undersupply_k for d in diffs) / len(diffs), 3),
            }

    _findings(report, cfg, hi - lo)
    return report


def _findings(report: CurveReport, cfg: CurveConfig, span: float) -> None:
    if span < cfg.min_outdoor_range_k:
        report.findings.append(
            Finding(
                "narrow_outdoor_range",
                "info",
                f"Outdoor temperature only spanned {span:.1f} K; flow temperatures for colder "
                "weather are extrapolated.",
            )
        )
    if report.r2 is not None and report.r2 < cfg.min_r2:
        report.findings.append(
            Finding(
                "curve_fit_poor",
                "check",
                f"Flow temperature follows the weather only loosely (R² {report.r2:.2f}). Common, "
                "harmless reasons: mild weather with little outdoor variation, room-temperature "
                "influence of a room unit, or setpoint changes. Not a fault by itself.",
                f"{report.hours_used} hours with heat demand",
            )
        )
    if report.tracking and report.tracking["undersupply_share"] >= 0.2:
        report.findings.append(
            Finding(
                "poor_tracking",
                "check",
                f"In {report.tracking['undersupply_share']:.0%} of hours the actual flow stayed more "
                f"than {cfg.undersupply_k:.0f} K below target.",
                f"{report.tracking['hours']} hours with target and actual flow",
            )
        )
