# Room comfort

The heating curve is right when the rooms the heating serves are *just* comfortable. Room
thermostats already in Home Assistant – any brand, any heat source – tell us whether that is
the case.

## What we look at (`heating_rooms`)

For every assigned `climate` entity, its current temperature is compared with its setpoint at
the same moment (setback periods count against the setback setpoint):

| Figure | Meaning |
|---|---|
| `deviation_mean_k` | time-weighted mean of actual − setpoint |
| `too_cold_share` | share of time more than 0.5 K below setpoint |
| `too_warm_share` | share of time more than 1 K above setpoint |
| `coverage_share` | share of the window with data; rooms below 50 % are not rated |

Findings *(heuristics, to be validated)*:
- `rooms_overheated` – at least half of the rated rooms are too warm for at least half of the
  time: the heating delivers more than needed, the **curve likely has headroom to go down**
  (each kelvin of lower flow temperature saves efficiency, see
  [fundamentals](fundamentals.md#flow-temperature-is-the-biggest-lever)).
- `limiting_room` – the room that is too cold most often (≥ 20 % of the time). It limits how far
  the curve can be lowered. *Established practice:* fix it rather than raising the whole curve –
  hydraulic balancing, flow through its circuit, emitter size, or simply its setpoint.

## Interpreting with the heating curve

| Rooms | Curve analysis | Likely action |
|---|---|---|
| Most rooms too warm | any | Lower the curve (shift first) in small steps |
| One room cold, others fine | fits well | Balance that room's circuit; don't raise the curve |
| Many rooms cold | `poor_tracking` | Heat source does not deliver the target – check source and flow |
| Rooms fine, setpoints high (≥ 23 °C) | any | Setpoint is a comfort choice; each kelvin of room temperature costs roughly 6 % heating energy *(commonly quoted rule of thumb)* |

## Limitations

- **Valve and actuator positions** (e.g. underfloor actuators) are rarely exposed as entities in
  Home Assistant. Without them we cannot see whether rooms are throttled by their valves – which
  would hide overheating and can cause compressor cycling. A future optional role.
- Thermostats measure at one spot; sun, cooking or open windows show up as deviations.
- Rooms whose thermostat is in "off" or frost-protection mode should be left out.
