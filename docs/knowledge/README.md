# Knowledge base

The heat pump expertise behind the tools – written for owners, contributors and the AI
assistant alike (tool results link here). Each page explains the physics, how we detect the
pattern from Home Assistant data, which thresholds we use **and how certain they are**.

| Page | Topic | Used by |
|---|---|---|
| [Fundamentals](fundamentals.md) | COP, SPF, Carnot, why flow temperature matters, heat output from flow rate | all |
| [Compressor cycling](cycling.md) | Short cycling, the modulation gap, causes and remedies, detection method | `heatpump_analyze_cycles` |
| [Heating curve](heating-curve.md) | Slope, shift, heating limit, tuning procedure, fitting the actual curve | `heatpump_heating_curve` (planned) |
| [Energy signature](energy-signature.md) | Weather-normalised comparisons, degree days, similar days | `heatpump_energy_signature` (planned) |
| [Flow/return spread](flow-return-spread.md) | What ΔT tells you about flow rate and emitters | `heatpump_spread` (planned) |
| [Hot water and defrost](hot-water-and-defrost.md) | Two operating modes that distort every other analysis | all |
| [Home Assistant data](home-assistant-data.md) | Recorder retention, sampling, units, gaps – the limits of what we can see | all |

## Confidence labels

- **Physics** – follows from thermodynamics; safe to state.
- **Established practice** – standard installer / engineering guidance; widely agreed.
- **Heuristic** – community rule of thumb or our own default. Configurable, to be confirmed
  by the [validation plan](../validation.md). Tool output lists these under `assumptions`.

Contributions with sources (standards, manufacturer documentation, measurement studies) are
very welcome – please cite them.
