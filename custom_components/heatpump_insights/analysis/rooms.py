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
from itertools import pairwise

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

    undersupplied_open_share: float = 0.8
    """Valve open at least this share of the time while the room is too cold: undersupplied."""

    few_open_share: float = 0.5
    """At most one circuit open for at least this share of the time: little water volume."""

    min_valve_days: float = 3.0
    """Valve-based statements need at least this many days of valve history."""

    high_setpoint_k: float = 1.0
    """A setpoint this far above the median of all rooms is called out as the simple explanation."""


@dataclass(slots=True)
class RoomsReport:
    analysis_version: str
    window_start: str
    window_end: str
    rooms: list[dict] = field(default_factory=list)
    overheated_rooms: list[str] = field(default_factory=list)
    limiting_room: str | None = None
    rated_rooms: int = 0
    """Rooms with enough data to be rated; 0 means no room statement is possible yet."""
    valves: dict | None = None
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
    valves: Mapping[str, Sequence[Sample]] | None = None,
    tz: tzinfo = UTC,
    cfg: RoomsConfig | None = None,
) -> RoomsReport:
    """``rooms`` maps a room name to (current temperature samples, setpoint samples).

    ``valves`` optionally maps a room name to its valve state (> 0.5 = open; works for
    on/off entities and for actuator power in watts).
    """
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
            "Valve open = state above 0.5 (on/off entity, or actuator power in watts)."
            if valves
            else "No valve states assigned: rooms throttled by their valve cannot be told apart.",
        ],
    )
    valve_segs = {name: segments(v, start, end) for name, v in (valves or {}).items()}
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
        if name in valve_segs:
            entry["valve_open_share"] = _open_share(valve_segs[name])
            entry["valve_history_days"] = round(
                sum(sg.duration for sg in valve_segs[name] if sg.value is not None) / 86400.0, 2
            )
        report.rooms.append(entry)
        if known > 0 and coverage >= cfg.min_coverage:
            rated.append(entry)

    report.rooms.sort(key=lambda r: r.get("deviation_mean_k", 0.0))
    if valve_segs:
        report.valves = _circuits(valve_segs)
    report.rated_rooms = len(rated)
    _findings(report, rated, cfg)
    return report


def _open_share(segs: list[Segment]) -> float | None:
    known = sum(s.duration for s in segs if s.value is not None)
    if known <= 0:
        return None
    return round(sum(s.duration for s in segs if s.value is not None and s.value > 0.5) / known, 3)


def _circuits(valve_segs: Mapping[str, list[Segment]]) -> dict:
    """How many circuits are open at the same time (only while every valve state is known)."""
    edges = sorted({t for segs in valve_segs.values() for s in segs for t in (s.start, s.end)})
    weighted = 0.0
    known = 0.0
    at_most_one = 0.0
    cursors = {name: 0 for name in valve_segs}
    for a, b in pairwise(edges):
        mid = (a + b) / 2
        values = []
        for name, segs in valve_segs.items():
            i = cursors[name]
            while i < len(segs) and segs[i].end <= mid:
                i += 1
            cursors[name] = i
            values.append(segs[i].value if i < len(segs) and segs[i].start <= mid else None)
        if any(v is None for v in values):
            continue
        count = sum(v > 0.5 for v in values)
        weighted += count * (b - a)
        known += b - a
        if count <= 1:
            at_most_one += b - a
    return {
        "circuits": len(valve_segs),
        "mean_open": round(weighted / known, 2) if known else None,
        "at_most_one_open_share": round(at_most_one / known, 3) if known else None,
    }


def _findings(report: RoomsReport, rated: list[dict], cfg: RoomsConfig) -> None:
    """Findings are graded: info (context), check (worth a look). Room findings never
    reach ``act``: temperatures alone cannot prove what a circuit or a setting needs."""
    unrated = [r["room"] for r in report.rooms if r not in rated]
    if unrated:
        report.findings.append(
            Finding("low_coverage", "info", "Too little data to rate: " + ", ".join(unrated) + ".")
        )
    if not rated:
        return
    days = max((r["coverage_share"] for r in rated), default=0.0) * _window_days(report)
    setpoints = sorted(r["setpoint_mean_c"] for r in rated)
    median_setpoint = setpoints[len(setpoints) // 2]

    report.overheated_rooms = [r["room"] for r in rated if r["too_warm_share"] >= cfg.overheated_share]
    if len(report.overheated_rooms) * 2 >= len(rated):
        report.findings.append(
            Finding(
                "rooms_overheated",
                "check",
                f"{len(report.overheated_rooms)} of {len(rated)} rooms are mostly warmer than their "
                "setpoint. If this holds over several days of normal weather, the heating curve "
                "probably has headroom to go down (in small steps).",
                f"{days:.1f} days of room temperatures",
            )
        )

    valve_rooms = [r for r in rated if r.get("valve_open_share") is not None]
    short_history = [r for r in valve_rooms if r.get("valve_history_days", 0) < cfg.min_valve_days]
    if short_history:
        report.findings.append(
            Finding(
                "insufficient_valve_history",
                "info",
                f"Valve history covers less than {cfg.min_valve_days:.0f} days for "
                f"{len(short_history)} room(s); valve-based statements are held back until then.",
                f"shortest valve history {min(r['valve_history_days'] for r in short_history):.1f} days",
            )
        )
    undersupplied = [
        r
        for r in valve_rooms
        if r.get("valve_history_days", 0) >= cfg.min_valve_days
        and r["valve_open_share"] >= cfg.undersupplied_open_share
        and r["too_cold_share"] >= cfg.limiting_cold_share
    ]
    if undersupplied:
        report.findings.append(
            Finding(
                "undersupplied_room",
                "check",
                "Valve open almost all the time, yet still below setpoint: "
                + ", ".join(r["room"] for r in undersupplied)
                + ". First compare the setpoint with other rooms. If it is normal and this persists, "
                "the circuit may deliver too little heat – a question for the installer, not a "
                "setting to change blindly.",
                ", ".join(
                    f"{r['room']}: valve open {r['valve_open_share']:.0%} over "
                    f"{r['valve_history_days']:.1f} days"
                    for r in undersupplied
                ),
            )
        )
    if (
        report.valves
        and report.valves["circuits"] >= 4
        and (report.valves["at_most_one_open_share"] or 0) >= cfg.few_open_share
        and all(r.get("valve_history_days", 0) >= cfg.min_valve_days for r in valve_rooms)
    ):
        report.findings.append(
            Finding(
                "few_open_circuits",
                "info",
                f"At most one of {report.valves['circuits']} circuits is open "
                f"{report.valves['at_most_one_open_share']:.0%} of the time. Little circulating water can "
                "shorten compressor runs (less relevant with a buffer tank).",
            )
        )

    coldest = max(rated, key=lambda r: (r["too_cold_share"], -r["deviation_mean_k"]))
    if coldest["too_cold_share"] >= cfg.limiting_cold_share:
        report.limiting_room = coldest["room"]
        high = coldest["setpoint_mean_c"] >= median_setpoint + cfg.high_setpoint_k
        report.findings.append(
            Finding(
                "limiting_room",
                "info",
                f"{coldest['room']} is below its setpoint {coldest['too_cold_share']:.0%} of the time "
                "and limits how far the curve can be lowered. "
                + (
                    f"Its setpoint ({coldest['setpoint_mean_c']:.1f} °C) is higher than in most rooms "
                    f"(median {median_setpoint:.1f} °C) – the simplest explanation."
                    if high
                    else "Watch whether this persists before drawing conclusions."
                ),
                f"mean {coldest['actual_mean_c']:.1f} °C vs setpoint {coldest['setpoint_mean_c']:.1f} °C",
            )
        )


def _window_days(report: RoomsReport) -> float:
    start = datetime.fromisoformat(report.window_start)
    end = datetime.fromisoformat(report.window_end)
    return max((end - start).total_seconds() / 86400.0, 0.0)


_GENERIC_WORDS = {
    "wandthermostat",
    "thermostat",
    "hmip",
    "access",
    "point",
    "schaltaktor",
    "stellregler",
    "stellantrieb",
    "valve",
    "ventil",
    "heizung",
    "heating",
    "room",
    "raum",
    "climate",
    "switch",
    "binary",
    "sensor",
    "power",
    "leistung",
    "fbh",
}


def _tokens(text: str) -> set[str]:
    words = "".join(c.lower() if c.isalnum() else " " for c in text).split()
    return {w[:5] for w in words if len(w) >= 4 and w not in _GENERIC_WORDS}


def match_valves(
    rooms: Mapping[str, tuple[str, str | None, str | None]],
    valves: Mapping[str, tuple[str, str | None, str | None]],
) -> tuple[dict[str, str], list[str]]:
    """Assign each valve to a room.

    ``rooms``: id → (name, area, heating group / device name);
    ``valves``: id → (name, area, heating group hint).
    Order: same heating group, then same area, then the only room sharing a name word.
    Returns (valve id → room id, unmatched valve ids).
    """
    matched: dict[str, str] = {}
    unmatched: list[str] = []
    for vid, (vname, varea, vgroup) in valves.items():
        room = None
        if vgroup:
            hits = [rid for rid, (_, _, g) in rooms.items() if g and g.casefold() == vgroup.casefold()]
            room = hits[0] if len(hits) == 1 else None
        if room is None and varea:
            hits = [rid for rid, (_, a, _) in rooms.items() if a and a == varea]
            room = hits[0] if len(hits) == 1 else None
        if room is None:
            vt = _tokens(vname)
            scores = {
                rid: len(vt & (_tokens(name) | _tokens(group or "")))
                for rid, (name, _, group) in rooms.items()
            }
            best = max(scores.values(), default=0)
            hits = [rid for rid, sc in scores.items() if sc == best and best > 0]
            room = hits[0] if len(hits) == 1 else None
        if room is None:
            unmatched.append(vid)
        else:
            matched[vid] = room
    return matched, unmatched
