"""Compressor cycle detection and cycling assessment.

Works with the most common sensor a heat pump owner has: the electrical power
of the heat pump (a sub-meter such as a Shelly, or a value from the
manufacturer integration). No vendor-specific compressor status is required;
if one exists it can be fed in as a 0/1 "power" series with a threshold of 0.5.

See ``docs/knowledge/cycling.md`` for the reasoning behind every default.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, tzinfo
from itertools import pairwise
from statistics import median

from .timeseries import (
    Sample,
    Segment,
    coverage,
    day_bounds,
    segments,
    time_weighted_mean,
    weighted_percentile,
)

ANALYSIS_VERSION = "0.3.2"


@dataclass(frozen=True, slots=True)
class CycleConfig:
    """Tunable parameters. Defaults are documented heuristics, not norms."""

    on_threshold_w: float | None = None
    """Power above which the compressor counts as running. ``None``: automatic."""

    min_on_s: float = 60.0
    """Ignore 'on' blips shorter than this (sensor noise, controller wake-ups)."""

    merge_off_s: float = 120.0
    """Bridge 'off' gaps shorter than this (mode switch, defrost dip, metering jitter)."""

    short_cycle_s: float = 600.0
    """A complete cycle shorter than this counts as a short cycle."""

    min_level_contrast_w: float = 150.0
    """Automatic threshold needs this much difference between idle and running."""

    min_coverage: float = 0.8
    """Below this share of known data the result is flagged as unreliable."""


@dataclass(slots=True)
class Cycle:
    start: float
    end: float
    energy_wh: float
    truncated: bool
    """True if the cycle touches the window edge or a data gap (true length unknown)."""

    @property
    def duration_s(self) -> float:
        return self.end - self.start


@dataclass(slots=True)
class Finding:
    code: str
    severity: str
    """``info``, ``attention`` or ``problem``."""
    message: str


@dataclass(slots=True)
class CycleReport:
    analysis_version: str
    window_start: str
    window_end: str
    threshold_w: float | None
    threshold_method: str
    coverage_share: float
    longest_data_gap_min: float
    cycles_total: int
    cycles_complete: int
    starts_per_day: float | None
    run_time_min: dict[str, float] | None
    off_time_median_min: float | None
    short_cycle_share: float | None
    max_starts_in_one_hour: int
    runtime_share: float | None
    energy_kwh: float
    per_day: list[dict] = field(default_factory=list)
    by_outdoor_temp: list[dict] = field(default_factory=list)
    rating: str = "insufficient_data"
    findings: list[Finding] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def auto_threshold(segs: Sequence[Segment], min_contrast: float) -> tuple[float | None, str]:
    """Estimate the on/off threshold from the time-weighted signal distribution.

    A pure on/off signal (0/1, e.g. a burner or compressor state entity) gets 0.5.

    Idle level = 10th percentile, running level = 90th percentile. The threshold
    sits 15 % of the way from idle to running, but at least 80 W above idle, so
    a circulation pump running alone stays below it while a compressor at
    minimum modulation stays above it.
    """
    known = {s.value for s in segs if s.value is not None}
    if known and known <= {0.0, 1.0}:
        return (0.5, "binary") if known == {0.0, 1.0} else (None, "no_distinct_levels")
    idle = weighted_percentile(segs, 0.10)
    running = weighted_percentile(segs, 0.90)
    if idle is None or running is None:
        return None, "no_data"
    if running - idle < min_contrast:
        return None, "no_distinct_levels"
    return idle + max(80.0, 0.15 * (running - idle)), "auto"


def detect_cycles(
    power: Sequence[Sample], start: float, end: float, threshold: float, cfg: CycleConfig
) -> list[Cycle]:
    """Find compressor run periods in a power series."""
    segs = segments(power, start, end)

    # 1. Raw on-intervals. Unknown spans break a run and mark both sides truncated.
    raw: list[list] = []  # [start, end, energy_wh, truncated_start, truncated_end]
    prev_unknown = True  # the window start behaves like a gap
    for seg in segs:
        if seg.value is None:
            if raw and raw[-1][1] == seg.start:
                raw[-1][4] = True
            prev_unknown = True
            continue
        if seg.value >= threshold:
            wh = seg.value * seg.duration / 3600.0
            if raw and raw[-1][1] == seg.start and not prev_unknown:
                raw[-1][1] = seg.end
                raw[-1][2] += wh
            else:
                raw.append([seg.start, seg.end, wh, prev_unknown, False])
        prev_unknown = False
    if raw and raw[-1][1] >= end:
        raw[-1][4] = True

    # 2. Bridge short off-gaps (only gaps with known data in between).
    merged: list[list] = []
    for item in raw:
        if merged and not merged[-1][4] and not item[3] and item[0] - merged[-1][1] < cfg.merge_off_s:
            merged[-1][1] = item[1]
            merged[-1][2] += item[2]
            merged[-1][4] = item[4]
        else:
            merged.append(item)

    # 3. Drop blips, but never drop a truncated run (its real length is unknown).
    return [
        Cycle(start=a, end=b, energy_wh=wh, truncated=ts or te)
        for a, b, wh, ts, te in merged
        if (b - a) >= cfg.min_on_s or ts or te
    ]


def _max_starts_in_hour(starts: Sequence[float]) -> int:
    best = 0
    j = 0
    for i, t in enumerate(starts):
        while starts[j] <= t - 3600:
            j += 1
        best = max(best, i - j + 1)
    return best


def _pct(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


def analyze_cycles(
    power: Sequence[Sample],
    start: float,
    end: float,
    *,
    tz: tzinfo = UTC,
    outdoor_temp: Sequence[Sample] | None = None,
    cfg: CycleConfig | None = None,
) -> CycleReport:
    """Analyze compressor cycling over ``[start, end)`` and rate it."""
    cfg = cfg or CycleConfig()
    segs = segments(power, start, end)
    cov = coverage(power, start, end)

    def iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, UTC).astimezone(tz).isoformat(timespec="minutes")

    if cfg.on_threshold_w is not None:
        threshold, method = cfg.on_threshold_w, "configured"
    else:
        threshold, method = auto_threshold(segs, cfg.min_level_contrast_w)

    report = CycleReport(
        analysis_version=ANALYSIS_VERSION,
        window_start=iso(start),
        window_end=iso(end),
        threshold_w=round(threshold, 1) if threshold is not None else None,
        threshold_method=method,
        coverage_share=round(cov.known_share, 3),
        longest_data_gap_min=round(cov.longest_silence_s / 60, 1),
        cycles_total=0,
        cycles_complete=0,
        starts_per_day=None,
        run_time_min=None,
        off_time_median_min=None,
        short_cycle_share=None,
        max_starts_in_one_hour=0,
        runtime_share=None,
        energy_kwh=round(sum(s.value * s.duration for s in segs if s.value is not None) / 3.6e6, 2),
        assumptions=[
            "Power is treated as a step function (Home Assistant state semantics).",
            f"Short cycle = complete run shorter than {cfg.short_cycle_s / 60:.0f} min.",
            f"Off gaps shorter than {cfg.merge_off_s:.0f} s are bridged; runs shorter than "
            f"{cfg.min_on_s:.0f} s are ignored.",
            "Without an operating-mode sensor, space heating and hot water runs are not separated.",
        ],
    )

    if threshold is None:
        if method == "no_distinct_levels":
            report.findings.append(
                Finding(
                    "no_distinct_levels",
                    "info",
                    "Power never clearly switches between idle and running levels. The heat "
                    "pump either ran continuously, never ran, or the sensor is not the heat "
                    "pump's power. Configure an explicit on-threshold to analyze anyway.",
                )
            )
        return report

    cycles = detect_cycles(power, start, end, threshold, cfg)
    complete = [c for c in cycles if not c.truncated]
    starts = [c.start for c in cycles if c.start > start]
    known_days = cov.known_s / 86400.0

    report.cycles_total = len(cycles)
    report.cycles_complete = len(complete)
    report.starts_per_day = round(len(starts) / known_days, 1) if known_days > 0 else None
    report.max_starts_in_one_hour = _max_starts_in_hour(sorted(starts))
    on_time = sum(c.duration_s for c in cycles)
    report.runtime_share = round(on_time / cov.known_s, 3) if cov.known_s > 0 else None

    if complete:
        durations = [c.duration_s / 60 for c in complete]
        report.run_time_min = {
            "median": round(median(durations), 1),
            "p10": round(_pct(durations, 0.1), 1),
            "p90": round(_pct(durations, 0.9), 1),
        }
        short = [c for c in complete if c.duration_s < cfg.short_cycle_s]
        report.short_cycle_share = round(len(short) / len(complete), 3)
    gaps = [(b.start - a.end) / 60 for a, b in pairwise(cycles)]
    if gaps:
        report.off_time_median_min = round(median(gaps), 1)

    outdoor_segs = segments(outdoor_temp, start, end) if outdoor_temp else None
    for date, a, b in day_bounds(start, end, tz):
        day_cycles = [c for c in cycles if a <= c.start < b]
        entry = {
            "date": date,
            "starts": sum(1 for c in day_cycles if c.start > start),
            "short_cycles": sum(
                1 for c in day_cycles if not c.truncated and c.duration_s < cfg.short_cycle_s
            ),
            "runtime_h": round(sum(max(0.0, min(c.end, b) - max(c.start, a)) for c in cycles) / 3600, 2),
            "energy_kwh": round(
                sum(
                    s.value * (min(s.end, b) - max(s.start, a))
                    for s in segs
                    if s.value is not None and s.end > a and s.start < b
                )
                / 3.6e6,
                2,
            ),
        }
        if outdoor_segs is not None:
            mean = time_weighted_mean(outdoor_segs, a, b)
            entry["outdoor_temp_mean"] = round(mean, 1) if mean is not None else None
        report.per_day.append(entry)

    if outdoor_segs is not None:
        report.by_outdoor_temp = _bin_by_outdoor(report.per_day)

    _rate(report, cfg)
    return report


def _bin_by_outdoor(per_day: list[dict], width: float = 3.0) -> list[dict]:
    """Group full days by mean outdoor temperature to show *when* cycling happens."""
    bins: dict[float, list[dict]] = {}
    for day in per_day:
        t = day.get("outdoor_temp_mean")
        if t is None:
            continue
        lo = width * (t // width)
        bins.setdefault(lo, []).append(day)
    return [
        {
            "outdoor_temp_from": lo,
            "outdoor_temp_to": lo + width,
            "days": len(items),
            "starts_per_day": round(sum(d["starts"] for d in items) / len(items), 1),
            "runtime_h_per_day": round(sum(d["runtime_h"] for d in items) / len(items), 1),
        }
        for lo, items in sorted(bins.items())
    ]


def _rate(report: CycleReport, cfg: CycleConfig) -> None:
    findings = report.findings
    if report.coverage_share < cfg.min_coverage:
        findings.append(
            Finding(
                "low_coverage",
                "info",
                f"Only {report.coverage_share:.0%} of the window has data; results may be incomplete.",
            )
        )
    if report.cycles_complete < 3:
        findings.append(
            Finding(
                "too_few_cycles",
                "info",
                "Fewer than three complete cycles: not enough to rate cycling. "
                "Long continuous runs are good, short windows are inconclusive.",
            )
        )
        only_long_runs = report.cycles_total > 0 and not report.short_cycle_share
        if only_long_runs and report.coverage_share >= cfg.min_coverage:
            report.rating = "good"
        return

    severity = "good"
    share = report.short_cycle_share or 0.0
    if share >= 0.30:
        severity = "problem"
        findings.append(
            Finding("short_cycling", "problem", f"{share:.0%} of complete runs are short cycles.")
        )
    elif share >= 0.10:
        severity = "attention"
        findings.append(
            Finding("some_short_cycles", "attention", f"{share:.0%} of complete runs are short cycles.")
        )
    if report.max_starts_in_one_hour > 3:
        severity = "problem" if severity == "problem" else "attention"
        findings.append(
            Finding(
                "many_starts_per_hour",
                "attention",
                f"Up to {report.max_starts_in_one_hour} compressor starts within one hour.",
            )
        )
    mild = [b for b in report.by_outdoor_temp if b["outdoor_temp_from"] >= 6]
    cold = [b for b in report.by_outdoor_temp if b["outdoor_temp_to"] <= 3]
    if mild and cold:
        mild_starts = max(b["starts_per_day"] for b in mild)
        cold_starts = min(b["starts_per_day"] for b in cold)
        if mild_starts > 2 * max(cold_starts, 1):
            findings.append(
                Finding(
                    "cycling_at_mild_weather",
                    "info",
                    "Starts rise sharply on mild days: the heat demand likely falls below the "
                    "compressor's minimum output (see knowledge: modulation gap).",
                )
            )
    if report.coverage_share < cfg.min_coverage:
        report.rating = "insufficient_data"
    else:
        report.rating = severity
