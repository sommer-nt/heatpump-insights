"""Synthetic heat pump data for tests and documentation figures.

Every series is labelled synthetic wherever it is shown. Real-world validation
data is collected separately (see docs/validation.md).
"""

from __future__ import annotations

import random
from collections.abc import Iterable

from analysis import Sample


def power_series(
    start: float,
    end: float,
    runs: Iterable[tuple[float, float, float]],
    *,
    idle_w: float = 40.0,
    step_s: float = 10.0,
    noise_w: float = 0.0,
    seed: int = 1,
) -> list[Sample]:
    """Power samples every ``step_s`` seconds; ``runs`` = (offset_s, duration_s, watts)."""
    rng = random.Random(seed)
    runs = sorted(runs)
    out: list[Sample] = []
    t = start
    while t < end:
        level = idle_w
        for off, dur, watts in runs:
            if start + off <= t < start + off + dur:
                level = watts
                break
        jitter = rng.uniform(-noise_w, noise_w) if noise_w else 0.0
        jitter = jitter if level > idle_w else jitter * 0.1
        out.append(Sample(t, round(level + jitter, 1)))
        t += step_s
    return out


def periodic_runs(
    period_s: float, run_s: float, watts: float, total_s: float, first_offset_s: float = 0.0
) -> list[tuple[float, float, float]]:
    runs = []
    t = first_offset_s
    while t < total_s:
        runs.append((t, run_s, watts))
        t += period_s
    return runs


def constant(start: float, end: float, value: float, step_s: float = 3600) -> list[Sample]:
    t = start
    out = []
    while t < end:
        out.append(Sample(t, value))
        t += step_s
    return out
