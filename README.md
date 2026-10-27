# Heat Pump Insights

**Your AI assistant understands why your heat pump behaves the way it does – and how to set it up better.**

Heat Pump Insights is an open-source Home Assistant integration that gives AI assistants
(cloud or local models – anything that talks to Home Assistant via MCP or Assist) a set of
**expert analysis tools** for heat pumps. It works with any brand: all it needs is the heat
pump's electrical power. Every additional sensor unlocks more analyses.

> *"Analyse my heat pump over the last seven days. Is it running efficiently, and should I change the heating curve?"*

Instead of handing raw sensor history to a language model and hoping it does the maths, the
integration computes the domain-specific figures – compressor cycles, short cycling, heating
curve, energy signature – and hands the assistant **structured, verifiable results** with data
coverage and assumptions attached. The model explains; the code calculates.

```
Home Assistant  = data           (your sensors and their history)
MCP / LLM API   = interface      (built into Home Assistant)
This project    = expertise      (heat pump knowledge as tested code)
LLM             = interpretation (dialogue in your language)
```

| | |
|---|---|
| ![Short cycling detected from a power sensor](docs/figures/cycling_patterns.svg) | ![The modulation gap](docs/figures/modulation_gap.svg) |

## How you use it

| Where | What you get |
|---|---|
| **Dashboard** in Home Assistant | Key figures as sensors (starts today, runtime, short cycles, rating, actual heating-curve slope, overheated rooms, valve open share per room) and a ready-made dashboard generated from your roles, with a compressor view for high pressure and hot gas if you assign them |
| **AI assistant** (via MCP or Assist) | The *why*: graded findings with the evidence they rest on, explained in your language |
| **Streamlit playground** | Try the analysis without installing, with examples or a history export |

## Status

**Early development (v0.4).** Cycle, heating curve and room analyses are implemented and
tested; cycle detection has been checked against a vendor compressor status on a real
installation. Findings are graded **info / check / act**: *act* only with clear data and only
for reversible settings – the tools never recommend physical work.

## What it does

| Tool | Needs | Answers |
|---|---|---|
| `heatpump_describe` | – | Which heat pumps and sensors are configured, which analyses are available, what is missing |
| `heatpump_discover_sensors` | – | Finds the right sensors for each role on any heat pump and gives the reasons; the user confirms |
| `heatpump_analyze_cycles` ✅ | power (+ outdoor temp) | How often does the compressor start? Is it short cycling? When – on mild days? |
| `heatpump_heating_curve` ✅ | circuit flow (or controller target) + outdoor temp | What is my real heating curve (K/K, flow at 0 / −10 °C)? Does the heat source deliver it? |
| `heating_rooms` ✅ | room thermostats (+ valves) | Which rooms are too warm or too cold? How often are their valves open? Which room limits the curve? |
| `heatpump_energy_signature` 🔜 | energy + outdoor temp | Did my change actually save energy, weather-corrected? |
| `heatpump_efficiency` 🔜 | heat meter | Real COP and seasonal performance factor |

All tools are **read-only**. Nothing is ever controlled.

## Works with any heat pump

There is no list of supported models. Home Assistant describes every sensor the same way
(type, unit, name, device), so Heat Pump Insights recognises the roles itself – in English,
German, French, Dutch, Scandinavian and Italian wording, for ISG, ViCare, Daikin, Aquarea/HeishaMon,
Luxtronik, ESPHome sensors and anything else. The setup form is pre-filled where one sensor
clearly fits; where two fit equally well, you (or your assistant, asking you) choose. Unknown wording? Add
the word to `analysis/discovery.py` – one line helps every user of that integration.

## Dashboard

After setting up the integration, create a new dashboard (*Settings → Dashboards → Add dashboard →
New dashboard from scratch*), open the raw configuration editor and enter:

```yaml
strategy:
  type: custom:heatpump-insights
  # heat_pump: Heat pump   # only needed with several heat pumps
```

The dashboard builds itself from the integration's sensors and your role mapping: overview with
key figures and findings, heating curve, rooms with valves. Thermostat and setting tiles are
display-only.

## Principles

1. **Vendor-independent** – roles instead of brand-specific entities.
2. **Computed, not guessed** – every number comes from tested code, with coverage and assumptions.
3. **Honest about limits** – missing sensors and data gaps are reported, never papered over.
4. **Local and private** – runs inside Home Assistant; the user decides what the assistant sees.
5. **Explainable knowledge** – every threshold is documented in the [knowledge base](docs/knowledge/README.md) with its reasoning.

## Try it without installing

`streamlit run streamlit_app.py` opens an interactive playground: load the bundled examples or a
Home Assistant history export (*History → ⋮ → Download data*) and see the cycle analysis with
interactive charts – for heat pumps and burners (gas, oil, pellets) alike.

## Requirements

**Must have**

- Home Assistant **2026.10** or newer, with the recorder enabled (it is by default).
- HACS (or copy `custom_components/heatpump_insights` by hand).
- An **electrical power sensor for the heat pump alone** (W or kW) – a meter or smart plug on its
  circuit, or the power your heat pump integration reports. It should update about once a minute:
  values polled from a vendor cloud every 5–15 minutes miss short runs.

**Optional – each sensor unlocks more**

| Sensor | Unlocks |
|---|---|
| Outdoor temperature | Cycling by weather |
| + heating circuit flow or the controller's target flow (with long-term statistics) | Heating curve |
| Room thermostats (`climate` entities) | Overheated rooms, the room that limits the curve |
| Valve state per heating circuit | Valve open share, undersupplied rooms |
| Refrigerant high pressure, hot gas temperature | Compressor view on the dashboard |

**Data takes time.** The cycling rating appears once at least 80 % of the last 7 days are recorded;
valve statements need 3 days of valve history; the heating curve becomes meaningful with cold days.

**AI assistant (optional).** Sensors and dashboard work without any AI. For the assistant you need
Home Assistant's *Model Context Protocol Server* integration and an MCP client (cloud clients need
remote access to Home Assistant), or an Assist conversation agent with the **Heat Pump Insights**
LLM API enabled.

**Not (yet) a fit:** systems without their own power measurement, values only from a slow cloud,
and burners without a power or burner-on signal.

## Installation (preview)

Requires Home Assistant **2026.10** or newer.

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/sommer-nt/heatpump-insights` (type *Integration*).
2. Install **Heat Pump Insights**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Heat Pump Insights*, assign your sensors.
4. Expose the tools to your assistant:
   - **MCP clients:** *Model Context Protocol Server* integration → select the LLM API **Heat Pump Insights** (alongside *Assist* if you like).
   - **Assist with a conversation agent** (cloud or local): in the agent's options, enable **Heat Pump Insights** as an LLM API.

## Documentation

- [Vision and aim](docs/vision.md) – what we build, for whom, and what we deliberately do not build
- [Use cases](docs/use-cases.md) – concrete questions the assistant must answer well
- [Architecture](docs/architecture.md) – layers, data flow, roles, tool contract
- [Validation plan](docs/validation.md) – how we prove the analyses are right
- [Roadmap](docs/roadmap.md)
- [Knowledge base](docs/knowledge/README.md) – the heat pump expertise behind the tools
- [Contributing](CONTRIBUTING.md) – device profiles, data, code, translations

## License

Apache-2.0
