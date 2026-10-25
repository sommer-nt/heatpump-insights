"""Time series primitives with Home Assistant state semantics.

A Home Assistant state is valid from the moment it was set until the next
state arrives. Every analysis therefore treats a series as a *step function*
(sample-and-hold), not as points to interpolate between. ``None`` marks an
unknown value (``unknown``/``unavailable`` or a non-numeric state).

This module has no Home Assistant imports so it can be tested and reused on
its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from itertools import pairwise


@dataclass(frozen=True, slots=True)
class Sample:
    """One state change: a timestamp (UTC seconds) and its numeric value."""

    ts: float
    value: float | None


@dataclass(frozen=True, slots=True)
class Segment:
    """A time span during which the series held one value."""

    start: float
    end: float
    value: float | None

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Coverage:
    """How much of the analysis window is backed by known values."""

    window_s: float
    known_s: float
    samples: int
    longest_silence_s: float

    @property
    def known_share(self) -> float:
        return self.known_s / self.window_s if self.window_s > 0 else 0.0


def segments(samples: Sequence[Sample], start: float, end: float) -> list[Segment]:
    """Turn state changes into step segments clipped to ``[start, end)``.

    The value before the first sample is unknown. The last value is held until
    ``end``, exactly like Home Assistant shows it.
    """
    ordered = sorted(samples, key=lambda s: s.ts)
    result: list[Segment] = []
    current: float | None = None
    cursor = start
    for sample in ordered:
        if sample.ts <= start:
            current = sample.value
            continue
        if sample.ts >= end:
            break
        if sample.ts > cursor:
            result.append(Segment(cursor, sample.ts, current))
        cursor = sample.ts
        current = sample.value
    if end > cursor:
        result.append(Segment(cursor, end, current))
    return _merge_equal(result)


def _merge_equal(items: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for seg in items:
        if merged and merged[-1].value == seg.value and merged[-1].end == seg.start:
            merged[-1] = Segment(merged[-1].start, seg.end, seg.value)
        else:
            merged.append(seg)
    return merged


def coverage(samples: Sequence[Sample], start: float, end: float) -> Coverage:
    """Describe data coverage for the window."""
    segs = segments(samples, start, end)
    known = sum(s.duration for s in segs if s.value is not None)
    in_window = sorted(s.ts for s in samples if start <= s.ts < end)
    edges = [start, *in_window, end]
    silence = max((b - a for a, b in pairwise(edges)), default=0.0)
    return Coverage(
        window_s=end - start,
        known_s=known,
        samples=len(in_window),
        longest_silence_s=silence,
    )


def weighted_percentile(segs: Iterable[Segment], q: float) -> float | None:
    """Time-weighted percentile (``q`` in 0..1) of the known segment values."""
    known = sorted((s.value, s.duration) for s in segs if s.value is not None and s.duration > 0)
    total = sum(d for _, d in known)
    if total <= 0:
        return None
    threshold = q * total
    acc = 0.0
    for value, duration in known:
        acc += duration
        if acc >= threshold:
            return value
    return known[-1][0]


def time_weighted_mean(segs: Iterable[Segment], start: float, end: float) -> float | None:
    """Mean value over ``[start, end)``, ignoring unknown spans."""
    total = 0.0
    weight = 0.0
    for seg in segs:
        a = max(seg.start, start)
        b = min(seg.end, end)
        if b <= a or seg.value is None:
            continue
        total += seg.value * (b - a)
        weight += b - a
    return total / weight if weight > 0 else None


def day_bounds(start: float, end: float, tz: tzinfo) -> list[tuple[str, float, float]]:
    """Split ``[start, end)`` into local calendar days: ``(date, day_start, day_end)``."""
    result: list[tuple[str, float, float]] = []
    local = datetime.fromtimestamp(start, UTC).astimezone(tz)
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    while day.timestamp() < end:
        # Aware datetime arithmetic is wall-clock arithmetic, so this is the next
        # local midnight even on 23 h / 25 h daylight saving days.
        nxt = day + timedelta(days=1)
        a = max(day.timestamp(), start)
        b = min(nxt.timestamp(), end)
        if b > a:
            result.append((day.date().isoformat(), a, b))
        day = nxt
    return result
