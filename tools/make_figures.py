"""Generate the explanatory figures in docs/figures.

Run: python tools/make_figures.py   (needs matplotlib, numpy)

Figures are illustrative: physical models and synthetic data, labelled as
such. They explain concepts; they are not measurements.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "heatpump_insights"))
sys.path.insert(0, str(ROOT / "tests"))

from analysis import CycleConfig  # noqa: E402
from analysis.cycles import detect_cycles  # noqa: E402
from synth import periodic_runs, power_series  # noqa: E402

OUT = ROOT / "docs" / "figures"

# Reference palette (validated categorical slots 1-3, light mode).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
WARN = "#eda100"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "font.size": 10.5,
        "font.family": "DejaVu Sans",
        "lines.linewidth": 2,
        "legend.frameon": False,
        "svg.fonttype": "none",
    }
)


def note(ax, text: str, y: float = -0.16) -> None:
    ax.text(1.0, y, text, transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=INK_2)


def save(fig, name: str) -> None:
    fig.savefig(OUT / name, bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def cop_vs_flow() -> None:
    """COP from a Carnot model with a constant quality factor."""
    eta, d_cond, d_evap = 0.55, 3.0, 6.0
    flow = np.linspace(25, 60, 200)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for t_out, color in ((7, BLUE), (2, ORANGE), (-7, AQUA)):
        tc = flow + d_cond + 273.15
        te = t_out - d_evap + 273.15
        cop = eta * tc / (tc - te)
        ax.plot(flow, cop, color=color, label=f"outdoor {t_out:+d} °C")
        ax.annotate(
            f"{t_out:+d} °C",
            (flow[-1], cop[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            color=INK_2,
            va="center",
            fontsize=9.5,
        )
    ax.set_title("Lower flow temperature, higher efficiency")
    ax.set_xlabel("Flow temperature (°C)")
    ax.set_ylabel("COP (heat out / electricity in)")
    ax.set_xlim(25, 64)
    ax.legend(loc="upper right")
    note(ax, "Illustrative model: COP = 0.55 × Carnot, air source, 3 K / 6 K heat exchanger approach.")
    save(fig, "cop_vs_flow_temperature.svg")


def modulation_gap() -> None:
    t = np.linspace(-15, 18, 300)
    design_t, design_load, limit = -12.0, 8.0, 15.0
    demand = np.clip(design_load * (limit - t) / (limit - design_t), 0, None)
    max_out = 7.0 + 0.12 * (t - design_t)
    min_out = 2.6 + 0.035 * (t - design_t)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.fill_between(
        t, 0, demand, where=(demand < min_out) & (demand > 0), color=WARN, alpha=0.22, linewidth=0
    )
    ax.plot(t, demand, color=BLUE, label="building heat demand")
    ax.plot(t, max_out, color=ORANGE, label="heat pump maximum output")
    ax.plot(t, min_out, color=AQUA, label="heat pump minimum output")
    cross = t[np.argmin(np.abs(demand - min_out))]
    ax.axvline(cross, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(
        cross + 0.4,
        6.4,
        f"above ≈{cross:.0f} °C outdoor:\ndemand < minimum output\n→ the pump must cycle",
        color=INK,
        fontsize=9.5,
        va="top",
    )
    ax.text(-14.5, 0.5, "demand within modulation range", color=INK_2, fontsize=9.5)
    ax.set_title("The modulation gap: why heat pumps cycle on mild days")
    ax.set_xlabel("Outdoor temperature (°C)")
    ax.set_ylabel("Heat (kW)")
    ax.set_ylim(0, 11)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=9.5)
    note(
        ax,
        "Illustrative: 8 kW design load at −12 °C, heating limit 15 °C; typical inverter air-to-water unit.",
        y=-0.27,
    )
    save(fig, "modulation_gap.svg")


def cycling_patterns() -> None:
    t0 = datetime(2026, 1, 12, tzinfo=UTC).timestamp()
    day = 86400.0
    cases = [
        ("Healthy: few long runs (cold day)", periodic_runs(6 * 3600, 4.5 * 3600, 1500, day, 1800), BLUE),
        ("Short cycling: many short runs (mild day)", periodic_runs(2100, 420, 750, day, 600), ORANGE),
    ]
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 5.0), sharex=True)
    for ax, (title, runs, color) in zip(axes, cases, strict=True):
        power = power_series(t0, t0 + day, runs, step_s=30, noise_w=60, seed=3)
        x = np.array([(s.ts - t0) / 3600 for s in power])
        y = np.array([s.value for s in power])
        cycles = detect_cycles(power, t0, t0 + day, 250, CycleConfig())
        for c in cycles:
            ax.axvspan((c.start - t0) / 3600, (c.end - t0) / 3600, color=color, alpha=0.12, linewidth=0)
        ax.step(x, y, where="post", color=color, linewidth=1.4)
        short = sum(1 for c in cycles if c.duration_s < 600)
        ax.set_title(title, fontsize=11.5)
        ax.text(
            0.99,
            0.92,
            f"{len(cycles)} runs · {short} shorter than 10 min",
            transform=ax.transAxes,
            ha="right",
            va="top",
            color=INK,
            fontsize=9.5,
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 2},
        )
        ax.set_ylabel("Power (W)")
        ax.set_ylim(0, 2100)
    axes[-1].set_xlabel("Hour of day")
    axes[-1].set_xticks(range(0, 25, 3))
    axes[-1].set_xlim(0, 24)
    note(axes[-1], "Synthetic data. Shaded = runs detected by heatpump_analyze_cycles.", y=-0.3)
    fig.tight_layout()
    save(fig, "cycling_patterns.svg")


def heating_curve() -> None:
    room = 20.0
    t = np.linspace(-15, 20, 200)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for slope, color, label in (
        (0.4, BLUE, "0.4 · underfloor"),
        (0.8, ORANGE, "0.8 · low-temp radiators"),
        (1.2, AQUA, "1.2 · old radiators"),
    ):
        flow = room + slope * (room - t)
        ax.plot(t, flow, color=color, label=f"slope {label}")
    rng = np.random.default_rng(4)
    tm = rng.uniform(-8, 13, 70)
    meas = room + 0.55 * (room - tm) + 2.0 + rng.normal(0, 1.1, tm.size)
    ax.scatter(
        tm,
        meas,
        s=22,
        color=INK_2,
        alpha=0.55,
        edgecolors=SURFACE,
        linewidths=0.6,
        label="measured hourly means (synthetic)",
    )
    k, b = np.polyfit(tm, meas, 1)
    xs = np.array([-8, 13])
    ax.plot(xs, k * xs + b, color=INK, linewidth=1.2, linestyle=(0, (4, 2)), label=f"fit: slope {-k:.2f}")
    ax.axvline(15, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(14.6, 60, "heating limit", color=INK_2, fontsize=9.5, va="top", ha="right")
    ax.set_title("Heating curve: flow temperature follows outdoor temperature")
    ax.set_xlabel("Outdoor temperature (°C)")
    ax.set_ylabel("Flow temperature (°C)")
    ax.set_ylim(15, 62)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=9)
    note(
        ax,
        "Simplified linear curve: flow = room + slope × (room − outdoor). Vendors add offsets and curvature.",
        y=-0.43,
    )
    save(fig, "heating_curve.svg")


def energy_signature() -> None:
    rng = np.random.default_rng(7)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for label, ua, color, marker in (
        ("before: steep curve", 0.62, BLUE, "o"),
        ("after: curve lowered 3 K", 0.55, ORANGE, "s"),
    ):
        t = rng.uniform(-6, 14, 45)
        kwh = np.clip(ua * (15.5 - t) + rng.normal(0, 0.9, t.size), 0.3, None)
        ax.scatter(
            t,
            kwh,
            s=24,
            color=color,
            marker=marker,
            alpha=0.75,
            edgecolors=SURFACE,
            linewidths=0.6,
            label=label,
        )
        k, b = np.polyfit(t, kwh, 1)
        xs = np.array([-6, -b / k])
        ax.plot(xs, k * xs + b, color=color, linewidth=1.6)
    ax.text(-5.6, 2.2, "same weather, less electricity\n→ the change worked", color=INK, fontsize=9.5)
    ax.set_title("Energy signature: fair before/after comparison")
    ax.set_xlabel("Daily mean outdoor temperature (°C)")
    ax.set_ylabel("Electricity per day (kWh)")
    ax.set_xlim(-7, 17)
    ax.set_ylim(0, 16)
    ax.legend(loc="upper right")
    note(ax, "Synthetic data. Each dot is one day; the line crosses zero near the heating limit.")
    save(fig, "energy_signature.svg")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cop_vs_flow()
    modulation_gap()
    cycling_patterns()
    heating_curve()
    energy_signature()
    print("figures written to", OUT)
