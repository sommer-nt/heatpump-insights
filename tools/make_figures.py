"""Generate the explanatory figures in docs/figures as hand-built SVG.

Run: python tools/make_figures.py   (needs numpy)

The SVGs carry their own light and dark theme (they follow the viewer's colour scheme,
also on GitHub) and use the system sans-serif, so they look native everywhere. Figures
are illustrative: physical models and synthetic data, labelled as such.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "heatpump_insights"))
sys.path.insert(0, str(ROOT / "tests"))

from analysis import CycleConfig  # noqa: E402
from analysis.cycles import detect_cycles  # noqa: E402
from synth import periodic_runs, power_series  # noqa: E402

OUT = ROOT / "docs" / "figures"
W, H = 960, 560

# Validated reference palette: categorical slots 1-3, stepped per mode.
STYLE = """
.root{--surface:#fcfcfb;--plane:#f4f3ef;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.08);--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a}
@media (prefers-color-scheme:dark){.root{--surface:#1a1a19;--plane:#232321;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.08);
--s1:#3987e5;--s2:#d95926;--s3:#199e70}}
text{font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;fill:var(--ink)}
.t{font-size:26px;font-weight:650;letter-spacing:-.01em}
.st{font-size:15px;fill:var(--ink2)}
.eb{font-size:12px;font-weight:600;letter-spacing:.08em;fill:var(--muted)}
.tick{font-size:12.5px;fill:var(--muted);font-variant-numeric:tabular-nums}
.ax{font-size:12.5px;fill:var(--ink2)}
.lbl{font-size:13.5px;font-weight:600}
.lbl2{font-size:12.5px;fill:var(--ink2)}
.note{font-size:12px;fill:var(--muted)}
.big{font-size:34px;font-weight:650;letter-spacing:-.02em}
.grid{stroke:var(--grid);stroke-width:1}
.base{stroke:var(--axis);stroke-width:1.2}
.halo{paint-order:stroke;stroke:var(--surface);stroke-width:5px;stroke-linejoin:round}
.ln{fill:none;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}
"""


def fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


@dataclass
class Plot:
    """A plot area with linear scales; appends SVG elements to ``parts``."""

    left: float
    top: float
    width: float
    height: float
    x: tuple[float, float]
    y: tuple[float, float]
    parts: list[str] = field(default_factory=list)

    def sx(self, v):
        return self.left + (np.asarray(v) - self.x[0]) / (self.x[1] - self.x[0]) * self.width

    def sy(self, v):
        return self.top + self.height - (np.asarray(v) - self.y[0]) / (self.y[1] - self.y[0]) * self.height

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def path(self, xs, ys) -> str:
        px, py = self.sx(xs), self.sy(ys)
        return "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(px, py, strict=True))

    def grid(self, yticks, xticks, yfmt=fmt, xfmt=fmt, x_title="", y_title="") -> None:
        for v in yticks:
            y = float(self.sy(v))
            self.parts.append(
                f'<line class="grid" x1="{self.left}" x2="{self.left + self.width}" y1="{y:.1f}" y2="{y:.1f}"/>'
            )
            self.parts.append(
                f'<text class="tick" x="{self.left - 10}" y="{y + 4:.1f}" text-anchor="end">{yfmt(v)}</text>'
            )
        self.parts.append(
            f'<line class="base" x1="{self.left}" x2="{self.left + self.width}" '
            f'y1="{self.bottom}" y2="{self.bottom}"/>'
        )
        for v in xticks:
            x = float(self.sx(v))
            self.parts.append(
                f'<text class="tick" x="{x:.1f}" y="{self.bottom + 20}" text-anchor="middle">{xfmt(v)}</text>'
            )
        if x_title:
            self.parts.append(
                f'<text class="ax" x="{self.left + self.width}" y="{self.bottom + 44}" '
                f'text-anchor="end">{escape(x_title)}</text>'
            )
        if y_title:
            self.parts.append(
                f'<text class="ax" x="{self.left - 40}" y="{self.top - 24}" text-anchor="start">{escape(y_title)}</text>'
            )

    def line(self, xs, ys, color: str, width: float = 2.5, dash: str = "") -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<path class="ln" d="{self.path(xs, ys)}" stroke="var({color})" stroke-width="{width}"{d}/>'
        )

    def area(self, xs, ys, color: str, gradient_id: str, base=None) -> None:
        base_y = self.y[0] if base is None else base
        xs, ys = np.asarray(xs), np.asarray(ys)
        lower = np.full_like(ys, base_y, dtype=float) if np.isscalar(base_y) else np.asarray(base_y)
        d = (
            self.path(xs, ys)
            + " L"
            + " L".join(
                f"{a:.1f},{b:.1f}" for a, b in zip(self.sx(xs[::-1]), self.sy(lower[::-1]), strict=True)
            )
            + " Z"
        )
        self.parts.append(f'<path d="{d}" fill="url(#{gradient_id})" stroke="none"/>')

    def end_label(self, x, y, text: str, color: str, dy: float = 0, sub: str = "") -> None:
        px, py = float(self.sx(x)), float(self.sy(y)) + dy
        self.parts.append(
            f'<circle cx="{float(self.sx(x)):.1f}" cy="{float(self.sy(y)):.1f}" r="4.5" '
            f'fill="var({color})" stroke="var(--surface)" stroke-width="2"/>'
        )
        self.parts.append(f'<text class="lbl halo" x="{px + 12:.1f}" y="{py + 5:.1f}">{escape(text)}</text>')
        if sub:
            self.parts.append(f'<text class="lbl2" x="{px + 12:.1f}" y="{py + 22:.1f}">{escape(sub)}</text>')

    def dots(self, xs, ys, color: str, r: float = 4.5, shape: str = "circle") -> None:
        for a, b in zip(self.sx(xs), self.sy(ys), strict=True):
            if shape == "square":
                self.parts.append(
                    f'<rect x="{a - r:.1f}" y="{b - r:.1f}" width="{2 * r}" height="{2 * r}" rx="1.5" '
                    f'fill="var({color})" fill-opacity=".85" stroke="var(--surface)" stroke-width="1.5"/>'
                )
            else:
                self.parts.append(
                    f'<circle cx="{a:.1f}" cy="{b:.1f}" r="{r}" fill="var({color})" fill-opacity=".85" '
                    f'stroke="var(--surface)" stroke-width="1.5"/>'
                )


def gradient(gid: str, color: str, top: float = 0.28) -> str:
    return (
        f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="var({color})" stop-opacity="{top}"/>'
        f'<stop offset="1" stop-color="var({color})" stop-opacity="0.02"/></linearGradient>'
    )


def figure(
    name: str,
    eyebrow: str,
    title: str,
    subtitle: str,
    note: str,
    body: list[str],
    defs: list[str] = (),
    height: int = H,
    desc: str = "",
) -> None:
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" '
        f'role="img" aria-labelledby="title desc" class="root">',
        f'<title id="title">{escape(title)}</title><desc id="desc">{escape(desc or subtitle)}</desc>',
        f"<style>{STYLE}</style>",
        "<defs>" + "".join(defs) + "</defs>",
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="20" fill="var(--surface)" '
        f'stroke="var(--ring)"/>',
        f'<text class="eb" x="40" y="48">{escape(eyebrow.upper())}</text>',
        f'<text class="t" x="40" y="84">{escape(title)}</text>',
        f'<text class="st" x="40" y="112">{escape(subtitle)}</text>',
        *body,
        f'<text class="note" x="40" y="{height - 24}">{escape(note)}</text>',
        "</svg>",
    ]
    (OUT / name).write_text("\n".join(svg) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- figures


def cycling_patterns() -> None:
    t0 = datetime(2026, 1, 12, tzinfo=UTC).timestamp()
    day = 86400.0
    cases = [
        ("Cold day", "healthy", periodic_runs(6 * 3600, 4.5 * 3600, 1500, day, 1800), "--s1", "g1"),
        ("Mild day", "short cycling", periodic_runs(2100, 420, 750, day, 600), "--s2", "g2"),
    ]
    body: list[str] = []
    defs = [gradient("g1", "--s1", 0.32), gradient("g2", "--s2", 0.32)]
    panel_h, top = 150, 160
    for i, (label, verdict, runs, color, gid) in enumerate(cases):
        p = Plot(240, top + i * (panel_h + 70), 680, panel_h, (0, 24), (0, 2000))
        power = power_series(t0, t0 + day, runs, step_s=30, noise_w=40, seed=3)
        xs = np.array([(s.ts - t0) / 3600 for s in power])
        ys = np.array([s.value for s in power])
        # step function as explicit corners
        sx = np.repeat(xs, 2)[1:]
        sy = np.repeat(ys, 2)[:-1]
        cycles = detect_cycles(power, t0, t0 + day, 250, CycleConfig())
        short = sum(1 for c in cycles if c.duration_s < 600)
        p.grid(
            [0, 1000, 2000],
            range(0, 25, 3) if i == 1 else [],
            yfmt=lambda v: f"{v / 1000:.0f} kW" if v else "0",
            xfmt=lambda v: f"{v:02d}:00",
        )
        p.area(sx, sy, color, gid)
        p.line(sx, sy, color, width=1.6)
        # run track: one rounded pill per detected run, above the plot
        for c in cycles:
            a, b = float(p.sx((c.start - t0) / 3600)), float(p.sx((c.end - t0) / 3600))
            body.append(
                f'<rect x="{a:.1f}" y="{p.top - 20}" width="{max(b - a - 1.5, 2.5):.1f}" height="8" rx="4" '
                f'fill="var({color})"/>'
            )
        body += p.parts
        # headline per panel
        y = p.top + 10
        body += [
            f'<text class="eb" x="40" y="{y}">{escape(label.upper())}</text>',
            f'<text class="big" x="40" y="{y + 42}">{len(cycles)} starts</text>',
            f'<text class="lbl2" x="40" y="{y + 68}">{short} shorter than 10 min</text>',
            f'<rect x="40" y="{y + 84}" width="{len(verdict) * 7.6 + 24:.0f}" height="26" rx="13" '
            f'fill="var({color})" fill-opacity=".14"/>',
            f'<circle cx="54" cy="{y + 97}" r="4" fill="var({color})"/>',
            f'<text class="lbl2" x="64" y="{y + 101.5}" style="fill:var(--ink)">{escape(verdict)}</text>',
        ]
    figure(
        "cycling_patterns.svg",
        "Compressor cycling",
        "Few long runs, or many short ones?",
        "The same heat pump on two days, as seen by its electrical power. Bars above each chart are detected runs.",
        "Synthetic data. Runs detected by heatpump_analyze_cycles; a run under 10 minutes counts as a short cycle.",
        body,
        defs,
        height=620,
    )


def modulation_gap() -> None:
    t = np.linspace(-15, 18, 331)
    design_t, design_load, limit = -12.0, 8.0, 15.0
    demand = np.clip(design_load * (limit - t) / (limit - design_t), 0, None)
    max_out = 7.0 + 0.12 * (t - design_t)
    min_out = 2.6 + 0.035 * (t - design_t)
    cross = float(t[np.argmin(np.abs(demand - min_out))])
    p = Plot(80, 180, 640, 282, (-15, 18), (0, 11))
    p.grid(
        [0, 2, 4, 6, 8, 10],
        [-15, -10, -5, 0, 5, 10, 15],
        yfmt=lambda v: f"{v:.0f}",
        xfmt=lambda v: f"{v:+.0f}°" if v else "0°",
        x_title="Outdoor temperature (°C)",
        y_title="Heat (kW)",
    )
    p.area(t, max_out, "--s3", "band", base=min_out)
    gap = (t >= cross) & (demand > 0)
    gx = t[gap]
    p.area(gx, min_out[gap], "--s2", "gap", base=demand[gap])
    p.line(t, max_out, "--s3", width=1.5)
    p.line(t, min_out, "--s3", width=1.5)
    p.line(t[demand > 0], demand[demand > 0], "--s1")
    x = float(p.sx(cross))
    p.parts.append(
        f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{p.top}" y2="{p.bottom}" stroke="var(--ink2)" '
        f'stroke-width="1" stroke-dasharray="3 4"/>'
    )
    p.parts.append(f'<text class="lbl2" x="{x + 8:.1f}" y="{p.top + 14}">≈ {cross:+.0f} °C</text>')
    p.parts.append(
        f'<text class="lbl" x="{float(p.sx(-9.5)):.1f}" y="{float(p.sy(5.0)):.1f}" '
        f'style="fill:var(--ink2);font-weight:500">modulation range</text>'
    )
    body = p.parts
    # right-hand annotation column
    rx = 760
    body += [
        f'<circle cx="{rx + 6}" cy="186" r="5" fill="var(--s1)"/>',
        f'<text class="lbl" x="{rx + 20}" y="191">Heat demand</text>',
        f'<text class="lbl2" x="{rx + 20}" y="210">of the building</text>',
        f'<rect x="{rx}" y="236" width="12" height="12" rx="3" fill="var(--s3)" fill-opacity=".35"/>',
        f'<text class="lbl" x="{rx + 20}" y="247">Modulation range</text>',
        f'<text class="lbl2" x="{rx + 20}" y="266">min. to max. output</text>',
        f'<rect x="{rx}" y="292" width="12" height="12" rx="3" fill="var(--s2)" fill-opacity=".55"/>',
        f'<text class="lbl" x="{rx + 20}" y="303">The gap</text>',
        f'<text class="lbl2" x="{rx + 20}" y="322">demand below minimum:</text>',
        f'<text class="lbl2" x="{rx + 20}" y="340">the pump has to cycle</text>',
    ]
    figure(
        "modulation_gap.svg",
        "Why heat pumps cycle",
        "The modulation gap",
        f"Above about {cross:+.0f} °C outdoor, the house needs less heat than the pump can deliver at its lowest.",
        "Illustrative: 8 kW design load at −12 °C, heating limit 15 °C, typical inverter air-to-water unit.",
        body,
        [
            gradient("band", "--s3", 0.22).replace('stop-opacity="0.02"', 'stop-opacity="0.12"'),
            gradient("gap", "--s2", 0.5).replace('stop-opacity="0.02"', 'stop-opacity="0.3"'),
        ],
    )


def cop_vs_flow() -> None:
    eta, d_cond, d_evap = 0.55, 3.0, 6.0
    flow = np.linspace(25, 60, 200)
    p = Plot(80, 180, 680, 282, (25, 60), (1, 7))
    p.grid(
        [1, 2, 3, 4, 5, 6, 7],
        [25, 30, 35, 40, 45, 50, 55, 60],
        yfmt=lambda v: f"{v:.0f}",
        xfmt=lambda v: f"{v:.0f}°",
        x_title="Flow temperature (°C)",
        y_title="COP – heat out per kWh electricity",
    )
    last_y = -1e9
    for t_out, color in ((7, "--s1"), (2, "--s2"), (-7, "--s3")):
        tc = flow + d_cond + 273.15
        cop = eta * tc / (tc - (t_out - d_evap + 273.15))
        p.line(flow, cop, color)
        y = float(p.sy(cop[-1]))
        label_y = max(y, last_y + 19)  # keep end labels apart
        last_y = label_y
        p.end_label(flow[-1], cop[-1], f"{t_out:+d} °C outdoor", color, dy=label_y - y)

    # annotate the 35 vs 55 °C difference on the +2 °C line
    def cop_at(f, t_out=2):
        tc = f + d_cond + 273.15
        return eta * tc / (tc - (t_out - d_evap + 273.15))

    for f in (35, 55):
        p.parts.append(
            f'<circle cx="{float(p.sx(f)):.1f}" cy="{float(p.sy(cop_at(f))):.1f}" r="5" '
            f'fill="var(--surface)" stroke="var(--s2)" stroke-width="2.5"/>'
        )
        p.parts.append(
            f'<text class="lbl" x="{float(p.sx(f)):.1f}" y="{float(p.sy(cop_at(f))) - 14:.1f}" '
            f'text-anchor="middle">{cop_at(f):.1f}</text>'
        )
    figure(
        "cop_vs_flow_temperature.svg",
        "Efficiency",
        "Every degree of flow temperature counts",
        f"At +2 °C outdoor, 35 °C flow gives a COP of {cop_at(35):.1f}; 55 °C only {cop_at(55):.1f}.",
        "Illustrative model: COP = 0.55 × Carnot, air source, 3 K / 6 K heat exchanger approach.",
        p.parts,
    )


def heating_curve() -> None:
    room = 20.0
    t = np.linspace(-15, 15, 200)
    p = Plot(80, 180, 640, 282, (-15, 20), (15, 60))
    p.grid(
        [20, 30, 40, 50, 60],
        [-15, -10, -5, 0, 5, 10, 15, 20],
        yfmt=lambda v: f"{v:.0f}°",
        xfmt=lambda v: f"{v:+.0f}°" if v else "0°",
        x_title="Outdoor temperature (°C)",
        y_title="Flow temperature (°C)",
    )
    labels = {
        0.4: ("Slope 0.4", "underfloor"),
        0.8: ("Slope 0.8", "low-temp radiators"),
        1.2: ("Slope 1.2", "old radiators"),
    }
    for slope, color in ((1.2, "--s3"), (0.8, "--s2"), (0.4, "--s1")):
        flow = room + slope * (room - t)
        p.line(t, flow, color)
    rng = np.random.default_rng(4)
    tm = rng.uniform(-8, 13, 60)
    meas = room + 0.55 * (room - tm) + 2.0 + rng.normal(0, 1.1, tm.size)
    for a, b in zip(p.sx(tm), p.sy(meas), strict=True):
        p.parts.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.6" fill="var(--ink2)" fill-opacity=".45"/>')
    k, b = np.polyfit(tm, meas, 1)
    xs = np.array([-8, 13])
    p.line(xs, k * xs + b, "--ink", width=2, dash="6 5")
    x15 = float(p.sx(15))
    p.parts.append(
        f'<line x1="{x15:.1f}" x2="{x15:.1f}" y1="{p.top}" y2="{p.bottom}" stroke="var(--muted)" '
        f'stroke-width="1" stroke-dasharray="3 4"/>'
    )
    p.parts.append(f'<text class="lbl2" x="{x15 + 8:.1f}" y="{p.bottom - 10}">heating limit</text>')
    body = p.parts
    rx, y = 760, 186
    for slope, color in ((1.2, "--s3"), (0.8, "--s2"), (0.4, "--s1")):
        name, sub = labels[slope]
        body += [
            f'<rect x="{rx}" y="{y - 7}" width="14" height="4" rx="2" fill="var({color})"/>',
            f'<text class="lbl" x="{rx + 22}" y="{y}">{name}</text>',
            f'<text class="lbl2" x="{rx + 22}" y="{y + 18}">{sub}</text>',
        ]
        y += 50
    body += [
        f'<circle cx="{rx + 7}" cy="{y - 5}" r="3.6" fill="var(--ink2)" fill-opacity=".45"/>',
        f'<text class="lbl" x="{rx + 22}" y="{y}">Measured hours</text>',
        f'<text class="lbl2" x="{rx + 22}" y="{y + 18}">fit: slope {-k:.2f}</text>',
    ]
    figure(
        "heating_curve.svg",
        "Heating curve",
        "Colder outside, warmer flow",
        "The fitted line through measured hours shows the curve the system really runs – not the setting.",
        "Simplified linear curve: flow = room + slope × (room − outdoor). Synthetic measurements.",
        body,
    )


def energy_signature() -> None:
    rng = np.random.default_rng(7)
    p = Plot(80, 180, 640, 282, (-7, 17), (0, 16))
    p.grid(
        [0, 4, 8, 12, 16],
        [-5, 0, 5, 10, 15],
        yfmt=lambda v: f"{v:.0f}",
        xfmt=lambda v: f"{v:+.0f}°" if v else "0°",
        x_title="Daily mean outdoor temperature (°C)",
        y_title="Electricity per day (kWh)",
    )
    fits = []
    for ua, color, shape in ((0.62, "--s1", "circle"), (0.55, "--s2", "square")):
        t = rng.uniform(-6, 14, 40)
        kwh = np.clip(ua * (15.5 - t) + rng.normal(0, 0.9, t.size), 0.3, None)
        k, b = np.polyfit(t, kwh, 1)
        fits.append((k, b))
        p.dots(t, kwh, color, r=4 if shape == "circle" else 3.6, shape=shape)
        xs = np.array([-6.5, -b / k])
        p.line(xs, k * xs + b, color, width=2.5)
    # saving arrow at 0 °C
    y_before = fits[0][0] * 0 + fits[0][1]
    y_after = fits[1][0] * 0 + fits[1][1]
    x0 = float(p.sx(0))
    p.parts.append(
        f'<line x1="{x0:.1f}" x2="{x0:.1f}" y1="{float(p.sy(y_before)) + 8:.1f}" '
        f'y2="{float(p.sy(y_after)) - 8:.1f}" stroke="var(--ink)" stroke-width="1.5"/>'
    )
    p.parts.append(
        f'<text class="lbl halo" x="{x0 - 10:.1f}" y="{float(p.sy(y_before)) - 18:.1f}" '
        f'text-anchor="end">−{(1 - y_after / y_before) * 100:.0f} % at 0 °C</text>'
    )
    body = p.parts
    rx = 760
    body += [
        f'<circle cx="{rx + 6}" cy="186" r="4.5" fill="var(--s1)"/>',
        f'<text class="lbl" x="{rx + 20}" y="191">Before</text>',
        f'<text class="lbl2" x="{rx + 20}" y="210">steep heating curve</text>',
        f'<rect x="{rx + 2}" y="232" width="8" height="8" rx="1.5" fill="var(--s2)"/>',
        f'<text class="lbl" x="{rx + 20}" y="241">After</text>',
        f'<text class="lbl2" x="{rx + 20}" y="260">curve lowered by 3 K</text>',
        f'<text class="lbl2" x="{rx}" y="300">Same weather,</text>',
        f'<text class="lbl2" x="{rx}" y="318">less electricity:</text>',
        f'<text class="lbl2" x="{rx}" y="336">the change worked.</text>',
    ]
    figure(
        "energy_signature.svg",
        "Energy signature",
        "Did the change really save energy?",
        "Each dot is one day. Comparing at equal outdoor temperature removes the weather from the verdict.",
        "Synthetic data. The line reaches zero near the heating limit.",
        body,
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cycling_patterns()
    modulation_gap()
    cop_vs_flow()
    heating_curve()
    energy_signature()
    print("figures written to", OUT)
