"""Interactive playground: analyse heating data from a Home Assistant history export.

Run locally:  streamlit run streamlit_app.py
The analysis is the same core the Home Assistant integration uses.
"""

from __future__ import annotations

import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "custom_components" / "heatpump_insights"))
sys.path.insert(0, str(ROOT / "tests"))

from analysis import CycleConfig, Sample, analyze_cycles  # noqa: E402
from analysis.cycles import detect_cycles  # noqa: E402
from analysis.timeseries import segments  # noqa: E402
from synth import constant, periodic_runs, power_series  # noqa: E402

st.set_page_config(page_title="Thermal Twin · Playground", page_icon="🔥", layout="wide")

# ---------------------------------------------------------------- look & feel
FLOW, RETURN, MUTED, GOOD, WARN, BAD = "#ff6b3d", "#3d8bff", "#8a94a6", "#22c55e", "#f5a524", "#ef4444"
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    h1, h2, h3 { font-family: 'Inter Tight', sans-serif !important; letter-spacing: -0.02em; }
    .hero { padding: 28px 30px; border-radius: 18px;
            background: radial-gradient(120% 140% at 0% 0%, rgba(255,107,61,.22), transparent 55%),
                        radial-gradient(120% 140% at 100% 100%, rgba(61,139,255,.22), transparent 55%);
            border: 1px solid rgba(138,148,166,.25); margin-bottom: 8px; }
    .hero h1 { margin: 0 0 6px 0; font-size: 2.4rem; }
    .hero p { margin: 0; opacity: .8; font-size: 1.05rem; max-width: 70ch; }
    .tag { display:inline-block; font: 500 .72rem 'JetBrains Mono', monospace; letter-spacing: .08em;
           text-transform: uppercase; opacity: .7; margin-bottom: 10px; }
    .finding { padding: 12px 16px; border-radius: 12px; margin: 6px 0; border: 1px solid rgba(138,148,166,.25); }
    .finding b { font-family: 'Inter Tight', sans-serif; }
    .sev-problem { border-left: 4px solid #ef4444; } .sev-attention { border-left: 4px solid #f5a524; }
    .sev-info { border-left: 4px solid #3d8bff; }
    div[data-testid="stMetricValue"] { font-family: 'Inter Tight', sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)


def style(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter Tight, sans-serif", "size": 13},
        hoverlabel={"font": {"family": "JetBrains Mono, monospace"}},
        legend={"orientation": "h", "y": 1.08, "x": 0},
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(138,148,166,.18)", zeroline=False)
    return fig


GENERATORS = {
    "Wärmepumpe": {"unit": "Verdichter", "short": 10},
    "Gas-/Öl-Brennwertkessel": {"unit": "Brenner", "short": 10},
    "Pelletkessel": {"unit": "Brenner", "short": 30},
    "Sonstiger Erzeuger": {"unit": "Erzeuger", "short": 10},
}

# ---------------------------------------------------------------- data
T0 = datetime(2026, 1, 12, tzinfo=UTC).timestamp()
DAY = 86400.0


@st.cache_data
def example(name: str) -> tuple[list[Sample], list[Sample], str, float]:
    """Synthetic examples: (signal, outdoor, generator, start)."""
    if "Wärmepumpe" in name:
        runs = periodic_runs(6 * 3600, 4 * 3600, 1600, 3 * DAY, 1800)
        runs += [(3 * DAY + o, d, w) for o, d, w in periodic_runs(2200, 450, 720, 4 * DAY, 400)]
        sig = power_series(T0, T0 + 7 * DAY, runs, step_s=30, noise_w=70, seed=5)
        out = constant(T0, T0 + 3 * DAY, -3.0) + constant(T0 + 3 * DAY, T0 + 7 * DAY, 11.0)
        return sig, out, "Wärmepumpe", T0
    runs = periodic_runs(1500, 240, 1, 5 * DAY, 300)  # burner on/off, 4 min every 25 min
    sig = power_series(T0, T0 + 5 * DAY, runs, idle_w=0, step_s=20)
    out = constant(T0, T0 + 5 * DAY, 6.0)
    return sig, out, "Gas-/Öl-Brennwertkessel", T0


ON_WORDS = {
    "on": 1.0,
    "off": 0.0,
    "true": 1.0,
    "false": 0.0,
    "an": 1.0,
    "aus": 0.0,
    "heating": 1.0,
    "idle": 0.0,
}


def parse_ha_csv(raw: bytes) -> dict[str, list[Sample]]:
    """Home Assistant history export: columns entity_id, state, last_changed."""
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"entity_id", "state", "last_changed"} <= set(df.columns):
        raise ValueError(
            "Erwartet werden die Spalten entity_id, state, last_changed (HA-Verlauf → Daten herunterladen)."
        )
    series: dict[str, list[Sample]] = {}
    ts = pd.to_datetime(df["last_changed"], utc=True, format="ISO8601")
    for entity, state, t in zip(df["entity_id"], df["state"].astype(str), ts, strict=True):
        s = state.strip().lower()
        if s in ON_WORDS:
            value: float | None = ON_WORDS[s]
        else:
            try:
                value = float(s)
            except ValueError:
                value = None
        series.setdefault(entity, []).append(Sample(t.timestamp(), value))
    return series


# ---------------------------------------------------------------- hero
st.markdown(
    """
    <div class="hero"><span class="tag">Thermal Twin · Playground · v0.1</span>
    <h1>Verstehe, warum deine Heizung tut, was sie tut.</h1>
    <p>Lade einen Verlauf aus Home Assistant hoch oder nimm ein Beispiel. Die Analyse erkennt Läufe von Verdichter
    oder Brenner, bewertet das Takten und zeigt, <i>wann</i> es passiert. Herstellerunabhängig: Es reicht ein
    Leistungs- oder Ein/Aus-Signal.</p></div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Daten")
    source = st.radio(
        "Quelle",
        ["Beispiel: Wärmepumpe (kalt → mild)", "Beispiel: Gaskessel taktet", "Eigener HA-Export (CSV)"],
        label_visibility="collapsed",
    )
    tz = ZoneInfo(st.selectbox("Zeitzone", ["Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "UTC"]))
    signal: list[Sample] = []
    outdoor: list[Sample] | None = None
    generator = "Wärmepumpe"
    if source.startswith("Beispiel"):
        signal, outdoor, generator, _ = example(source)
        st.caption("Synthetische Beispieldaten.")
    else:
        st.caption("Home Assistant → Verlauf → Entitäten wählen → ⋮ → Daten herunterladen.")
        st.caption(
            "🔒 Die Datei wird nur für diese Sitzung im Arbeitsspeicher ausgewertet und nicht "
            "gespeichert. Sie wird dafür aber an den Server dieser App übertragen. Volle Kontrolle: "
            "die App lokal starten (`streamlit run streamlit_app.py`)."
        )
        up = st.file_uploader("CSV", type="csv", label_visibility="collapsed")
        if up:
            try:
                series = parse_ha_csv(up.getvalue())
            except ValueError as err:
                st.error(str(err))
                st.stop()
            ids = sorted(series)
            sig_id = st.selectbox("Signal (Leistung, Modulation oder Ein/Aus)", ids)
            out_id = st.selectbox("Außentemperatur (optional)", ["–", *ids])
            signal = series[sig_id]
            outdoor = series.get(out_id) if out_id != "–" else None
            generator = st.selectbox("Wärmeerzeuger", list(GENERATORS))
    st.divider()
    st.header("Einstellungen")
    gen = GENERATORS[generator]
    short_min = st.slider("Kurztakt-Grenze (min)", 3, 45, gen["short"])
    auto = st.toggle("Schwelle automatisch", value=True)
    thr = None if auto else st.number_input("Einschaltschwelle", value=300.0)

if not signal:
    st.info("Wähle links ein Beispiel oder lade einen Home-Assistant-Export hoch.")
    st.stop()

start = min(s.ts for s in signal)
end = max(s.ts for s in signal)
cfg = CycleConfig(on_threshold_w=thr, short_cycle_s=short_min * 60)
report = analyze_cycles(signal, start, end, tz=tz, outdoor_temp=outdoor, cfg=cfg)
unit = gen["unit"]

# ---------------------------------------------------------------- verdict
RATING = {
    "good": ("Gesund", GOOD),
    "attention": ("Auffällig", WARN),
    "problem": ("Problem", BAD),
    "insufficient_data": ("Zu wenig Daten", MUTED),
}
label, color = RATING[report.rating]
st.markdown(
    f"<h2 style='margin-top:6px'>Bewertung: <span style='color:{color}'>{label}</span></h2>",
    unsafe_allow_html=True,
)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(f"{unit}starts / Tag", report.starts_per_day if report.starts_per_day is not None else "–")
c2.metric("Laufzeit (Median)", f"{report.run_time_min['median']:.0f} min" if report.run_time_min else "–")
c3.metric(
    "Anteil Kurztakte", f"{report.short_cycle_share:.0%}" if report.short_cycle_share is not None else "–"
)
c4.metric("Max. Starts / Stunde", report.max_starts_in_one_hour)
c5.metric("Datenabdeckung", f"{report.coverage_share:.0%}")

FINDINGS_DE = {
    "short_cycling": ("Kurztakten", "{share:.0%} der vollständigen Läufe sind kürzer als {short} min."),
    "some_short_cycles": (
        "Einige Kurztakte",
        "{share:.0%} der vollständigen Läufe sind kürzer als {short} min.",
    ),
    "many_starts_per_hour": ("Viele Starts pro Stunde", "Bis zu {hour} Starts innerhalb einer Stunde."),
    "cycling_at_mild_weather": (
        "Takten bei mildem Wetter",
        "An milden Tagen steigen die Starts stark an. Der Wärmebedarf liegt dann vermutlich unter der "
        "kleinsten Leistung des Erzeugers (Modulationslücke).",
    ),
    "too_few_cycles": (
        "Wenige Läufe",
        "Weniger als drei vollständige Läufe. Lange Dauerläufe sind gut, kurze Zeiträume nicht aussagekräftig.",
    ),
    "low_coverage": ("Lückenhafte Daten", "Nur {cov:.0%} des Zeitraums haben Daten."),
    "no_distinct_levels": (
        "Kein klares Ein/Aus erkennbar",
        "Das Signal wechselt nicht deutlich zwischen Ruhe und Betrieb. Lege die Schwelle von Hand fest.",
    ),
}
values = {
    "share": report.short_cycle_share or 0,
    "short": short_min,
    "hour": report.max_starts_in_one_hour,
    "cov": report.coverage_share,
}
for f in report.findings:
    title, text = FINDINGS_DE.get(f.code, (f.code, f.message))
    st.markdown(
        f"<div class='finding sev-{f.severity}'><b>{title}</b><br>{text.format(**values)}</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------- charts
tab1, tab2, tab3, tab4 = st.tabs(
    ["Zeitverlauf", "Laufzeiten", "Nach Außentemperatur", "Heizkurve simulieren"]
)

threshold = report.threshold_w
cycles = detect_cycles(signal, start, end, threshold, cfg) if threshold is not None else []

with tab1:
    segs = segments(signal, start, end)
    xs, ys = [], []
    for sg in segs:
        xs += [datetime.fromtimestamp(sg.start, tz), datetime.fromtimestamp(sg.end, tz)]
        ys += [sg.value, sg.value]
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=xs,
            y=ys,
            mode="lines",
            line={"color": FLOW, "width": 1.4},
            name="Signal",
            fill="tozeroy",
            fillcolor="rgba(255,107,61,.12)",
        )
    )
    for c in cycles:
        short = not c.truncated and c.duration_s < cfg.short_cycle_s
        fig.add_vrect(
            x0=datetime.fromtimestamp(c.start, tz),
            x1=datetime.fromtimestamp(c.end, tz),
            fillcolor=BAD if short else RETURN,
            opacity=0.10,
            line_width=0,
        )
    if threshold is not None:
        fig.add_hline(
            y=threshold,
            line={"color": MUTED, "dash": "dot", "width": 1},
            annotation_text=f"Schwelle {threshold:g}",
            annotation_position="top left",
        )
    last = datetime.fromtimestamp(end, tz)
    fig.update_xaxes(
        range=[last.replace(microsecond=0) - pd.Timedelta(hours=24), last],
        rangeslider={"visible": True, "thickness": 0.08},
    )
    st.plotly_chart(style(fig, 460), width="stretch")
    st.caption(
        "Letzte 24 Stunden. Blau = Lauf, rot = Kurztakt. Mit dem Schieberegler unten durch den ganzen Zeitraum fahren."
    )

with tab2:
    complete = [c for c in cycles if not c.truncated]
    if complete:
        df = pd.DataFrame({"min": [c.duration_s / 60 for c in complete]})
        df["Art"] = ["Kurztakt" if m < short_min else "Lauf" for m in df["min"]]
        fig = go.Figure()
        for art, col in (("Lauf", RETURN), ("Kurztakt", BAD)):
            part = df[df["Art"] == art]
            fig.add_trace(go.Histogram(x=part["min"], name=art, marker_color=col, nbinsx=40, opacity=0.9))
        fig.add_vline(x=short_min, line={"color": MUTED, "dash": "dot"})
        fig.update_layout(barmode="stack", xaxis_title="Laufzeit (min)", yaxis_title="Anzahl Läufe")
        st.plotly_chart(style(fig), width="stretch")
    else:
        st.info("Keine vollständigen Läufe erkannt.")

with tab3:
    if report.by_outdoor_temp:
        b = pd.DataFrame(report.by_outdoor_temp)
        b["Bereich"] = b.apply(lambda r: f"{r.outdoor_temp_from:+.0f} … {r.outdoor_temp_to:+.0f} °C", axis=1)
        fig = go.Figure(
            go.Bar(
                x=b["Bereich"],
                y=b["starts_per_day"],
                marker_color=[FLOW if t >= 6 else RETURN for t in b["outdoor_temp_from"]],
                text=b["starts_per_day"],
                textposition="outside",
            )
        )
        fig.update_layout(yaxis_title=f"{unit}starts pro Tag")
        st.plotly_chart(style(fig), width="stretch")
        st.caption(
            "Viele Starts an milden Tagen deuten auf die Modulationslücke hin: Das Haus braucht weniger "
            "Wärme, als der Erzeuger auf kleinster Stufe liefert."
        )
    else:
        st.info("Ordne eine Außentemperatur zu, um das Takten nach Wetter zu sehen.")
    st.dataframe(pd.DataFrame(report.per_day), width="stretch", hide_index=True)

with tab4:
    st.markdown(
        "Verschiebe die Heizkurve und sieh sofort die Vorlauftemperaturen und, bei Wärmepumpen, die "
        "Wirkung auf die Effizienz. *Modell, keine Messung.*"
    )
    a, b_, c_ = st.columns(3)
    slope = a.slider("Steigung", 0.2, 2.0, 0.8, 0.05)
    shift = b_.slider("Niveau (K)", -10, 10, 0, 1)
    room = c_.slider("Raumsoll (°C)", 18, 24, 20, 1)
    t = list(range(-15, 21))

    def flow_temp(to: float, s: float, sh: float) -> float:
        return room + s * (room - to) + sh

    def cop(fl: float, to: float) -> float:
        tc, te = fl + 3 + 273.15, to - 6 + 273.15
        return 0.55 * tc / (tc - te)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=t,
            y=[flow_temp(x, 0.8, 0) for x in t],
            name="Ausgangskurve",
            line={"color": MUTED, "dash": "dot"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=t,
            y=[flow_temp(x, slope, shift) for x in t],
            name="Deine Kurve",
            line={"color": FLOW, "width": 3},
        )
    )
    fig.update_layout(xaxis_title="Außentemperatur (°C)", yaxis_title="Vorlauftemperatur (°C)")
    st.plotly_chart(style(fig), width="stretch")
    base = sum(1 / cop(flow_temp(x, 0.8, 0), x) for x in range(-10, 15))
    new = sum(1 / cop(flow_temp(x, slope, shift), x) for x in range(-10, 15))
    st.metric("Strombedarf Wärmepumpe ggü. Ausgangskurve (gleiche Wärme)", f"{(new / base - 1):+.1%}")
    st.caption(
        "Grobe Abschätzung: COP = 0,55 × Carnot, gleichmäßig über −10 … +14 °C gewichtet. "
        "Der digitale Zwilling wird das künftig mit deinem gelernten Gebäudemodell rechnen."
    )

with st.expander("Details für Entwickler (JSON wie für den KI-Assistenten)"):
    st.json(report.as_dict())

st.caption(
    f"Analyse v{report.analysis_version} · Zeitraum {report.window_start} – {report.window_end} · "
    f"erstellt {datetime.now(tz):%d.%m.%Y %H:%M}"
)
