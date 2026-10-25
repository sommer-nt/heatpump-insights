# Knowledge base

The heat pump expertise behind the tools – written for owners, contributors and the AI
assistant alike (tool results link here). Each page explains the physics, how we detect the
pattern from Home Assistant data, which thresholds we use **and how certain they are**.

| Page | Topic | Used by |
|---|---|---|
| [Fundamentals](fundamentals.md) | COP, SPF, Carnot, why flow temperature matters, heat output from flow rate | all |
| [Compressor cycling](cycling.md) | Short cycling, the modulation gap, causes and remedies, detection method | `heatpump_analyze_cycles` |
| [Heating curve](heating-curve.md) | Slope, shift, heating limit, tuning procedure, fitting the actual curve | `heatpump_heating_curve` |
| [Room comfort](rooms.md) | Overheated rooms, the room that limits the curve | `heating_rooms` |
| [Energy signature](energy-signature.md) | Weather-normalised comparisons, degree days, similar days | `heatpump_energy_signature` (planned) |
| [Flow/return spread](flow-return-spread.md) | What ΔT tells you about flow rate and emitters | `heatpump_spread` (planned) |
| [Hot water and defrost](hot-water-and-defrost.md) | Two operating modes that distort every other analysis | all |
| [Home Assistant data](home-assistant-data.md) | Recorder retention, sampling, units, gaps – the limits of what we can see | all |

## How findings are graded

Every finding a tool returns carries a **severity** and the **evidence** it rests on:

| Severity | Meaning | What the assistant may do |
|---|---|---|
| `info` | context, an observation | explain it |
| `check` | worth watching or verifying; not proven yet | suggest watching it, name the data still missing |
| `act` | clear data over enough days | suggest **one reversible setting change** |

Physical work (flushing, hydraulic balancing, replacing parts) is never recommended by a tool;
at most a persistent pattern is something to discuss with the installer. Simple explanations
(a setpoint, the weather, too little data) are named first. Valve-based statements wait for at
least 3 days of valve history.

## Confidence labels

- **Physics** – follows from thermodynamics; safe to state.
- **Established practice** – standard installer / engineering guidance; widely agreed.
- **Heuristic** – community rule of thumb or our own default. Configurable, to be confirmed
  by the [validation plan](../validation.md). Tool output lists these under `assumptions`.

Contributions with sources (standards, manufacturer documentation, measurement studies) are
very welcome – please cite them.
