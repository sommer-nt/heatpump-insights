"""Room comfort analysis: which rooms are too warm, which limit the heating curve?

Uses the current and target temperature of any Home Assistant ``climate``
entity, so it works with every thermostat brand and every heat source. Rooms
that stay above their setpoint show headroom to lower the heating curve; the
room with the largest deficit is the one that limits it.

See ``docs/knowledge/rooms.md`` for the reasoning behind the defaults.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, tzinfo

from .cycles import ANALYSIS_VERSION, Finding
from .timeseries import Sample, Segment, segments


@dataclass(frozen=True, slots=True)
class RoomsConfig:
    """Tunable parameters. Defaults are documented heuristics, not norms."""

    cold_margin_k: float = 0.5
    """Below setpoint by more than this counts as too cold."""

    warm_margin_k: float = 1.0
    """Above setpoint by more than this counts as too warm."""

    overheated_share: float = 0.5
    """A room is overheated if it is too warm for at least this share of the time."""

    limiting_cold_share: float = 0.2
    """A room limits the curve if it is too cold for at least this share of the time."""

    min_coverage: float = 0.5
    """Rooms with less known data than this share are reported but not rated."""


@dataclass(slots=True)
class RoomsReport:
    analysis_version: str
    window_start: str
    window_end: str
    rooms: list[dict] = field(default_factory=list)
    overheated_rooms: list[str] = field(default_factory=list)
    limiting_room: str | None = None
    findings: list[Finding] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _paired(a: list[Segment], b: list[Segment]) -> list[tuple[float, float | None, float | None]]:
    """Walk two step series together: (duration, value_a, value_b) per common interval."""
    out = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i].start, b[j].start)
        end = min(a[i].end, b[j].end)
        if end > start:
            out.append((end - start, a[i].value, b[j].value))
        if a[i].end <= b[j].end:
            i += 1
        else:
            j += 1
    return out


def analyze_rooms(
    rooms: Mapping[str, tuple[Sequence[Sample], Sequence[Sample]]],
    start: float,
    end: float,
    *,
    tz: tzinfo = UTC,
    cfg: RoomsConfig | None = None,
) -> RoomsReport:
    """``rooms`` maps a room name to (current temperature samples, setpoint samples)."""
    cfg = cfg or RoomsConfig()

    def iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, UTC).astimezone(tz).isoformat(timespec="minutes")

    report = RoomsReport(
        analysis_version=ANALYSIS_VERSION,
        window_start=iso(start),
        window_end=iso(end),
        assumptions=[
            f"Too cold = more than {cfg.cold_margin_k} K below setpoint; too warm = more than "
            f"{cfg.warm_margin_k} K above setpoint.",
            "Setback periods count against the setpoint active at that time.",
            "Valve or actuator positions are not used (rarely available in Home Assistant).",
        ],
    )
    window = end - start
    rated: list[dict] = []
    for name, (actual, setpoint) in rooms.items():
        known = cold = warm = sum_a = sum_s = 0.0
        for dt, a, s in _paired(segments(actual, start, end), segments(setpoint, start, end)):
            if a is None or s is None:
                continue
            known += dt
            sum_a += a * dt
            sum_s += s * dt
            if a < s - cfg.cold_margin_k:
                cold += dt
            elif a > s + cfg.warm_margin_k:
                warm += dt
        coverage = known / window if window > 0 else 0.0
        entry: dict = {"room": name, "coverage_share": round(coverage, 3)}
        if known > 0:
            entry |= {
                "actual_mean_c": round(sum_a / known, 1),
                "setpoint_mean_c": round(sum_s / known, 1),
                "deviation_mean_k": round((sum_a - sum_s) / known, 2),
                "too_cold_share": round(cold / known, 3),
                "too_warm_share": round(warm / known, 3),
            }
        report.rooms.append(entry)
        if known > 0 and coverage >= cfg.min_coverage:
            rated.append(entry)

    report.rooms.sort(key=lambda r: r.get("deviation_mean_k", 0.0))
    _findings(report, rated, cfg)
    return report


def _findings(report: RoomsReport, rated: list[dict], cfg: RoomsConfig) -> None:
    unrated = [r["room"] for r in report.rooms if r not in rated]
    if unrated:
        report.findings.append(
            Finding("low_coverage", "info", "Too little data to rate: " + ", ".join(unrated) + ".")
        )
    if not rated:
        return
    report.overheated_rooms = [r["room"] for r in rated if r["too_warm_share"] >= cfg.overheated_share]
    if len(report.overheated_rooms) * 2 >= len(rated):
        report.findings.append(
            Finding(
                "rooms_overheated",
                "attention",
                f"{len(report.overheated_rooms)} of {len(rated)} rooms are mostly warmer than their "
                "setpoint: the heating curve likely has headroom to go down.",
            )
        )
    coldest = max(rated, key=lambda r: (r["too_cold_share"], -r["deviation_mean_k"]))
    if coldest["too_cold_share"] >= cfg.limiting_cold_share:
        report.limiting_room = coldest["room"]
        report.findings.append(
            Finding(
                "limiting_room",
                "info",
                f"{coldest['room']} is too cold {coldest['too_cold_share']:.0%} of the time and "
                "limits how far the curve can be lowered. Check it before changing the curve "
                "(hydraulic balancing, emitter size, setpoint).",
            )
        )
