# Heat Pump Insights

**Your AI assistant understands why your heat pump behaves the way it does – and how to set it up better.**

Heat Pump Insights is an open-source Home Assistant integration that gives AI assistants
(Claude, ChatGPT, local models via Ollama – anything that talks to Home Assistant) a set of
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

## Status

**Early development (v0.2).** Cycle, heating curve and room analyses are implemented and
tested; cycle detection has been checked against a vendor compressor status on a first real installation. Validation against real installations is the next milestone – see
[validation plan](docs/validation.md). **Help wanted: owners willing to share anonymised data.**

## What it does

| Tool | Needs | Answers |
|---|---|---|
| `heatpump_describe` | – | Which heat pumps and sensors are configured, what is missing and what it would unlock |
| `heatpump_analyze_cycles` ✅ | power (+ outdoor temp) | How often does the compressor start? Is it short cycling? When – on mild days? |
| `heatpump_heating_curve` ✅ | circuit flow (or controller target) + outdoor temp | What is my real heating curve (K/K, flow at 0 / −10 °C)? Does the heat source deliver it? |
| `heating_rooms` ✅ | room thermostats (climate) | Which rooms are too warm or too cold? Which room limits the curve? |
| `heatpump_energy_signature` 🔜 | energy + outdoor temp | Did my change actually save energy, weather-corrected? Similar days compared |
| `heatpump_spread` 🔜 | flow + return temp | Is the flow/return spread healthy for heating and hot water? |
| `heatpump_efficiency` 🔜 | heat meter | Real COP and seasonal performance factor |

All tools are **read-only**. Nothing is ever controlled.

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

## Installation (preview)

Requires Home Assistant **2026.10** or newer.

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/sommer-nt/heatpump-insights` (type *Integration*).
2. Install **Heat Pump Insights**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Heat Pump Insights*, assign your sensors.
4. Expose the tools to your assistant:
   - **Claude / other MCP clients:** *Model Context Protocol Server* integration → select the LLM API **Heat Pump Insights** (alongside *Assist* if you like).
   - **Assist with a conversation agent** (OpenAI, Anthropic, Ollama, …): in the agent's options, enable **Heat Pump Insights** as an LLM API.

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
