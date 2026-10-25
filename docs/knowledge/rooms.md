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

## Valves: is the room throttled or starved?

With a valve state per circuit (role *valves*: a switch, binary sensor or the actuator's power),
the analysis also reports how much of the time each circuit is open and how many circuits are
open at once. Valves are matched to rooms automatically (same heating group, then same area,
then a shared name word); ambiguous ones are listed as `unmatched_valves`.

| Valve | Room | Meaning |
|---|---|---|
| open almost always (≥ 80 %) | too cold | `undersupplied_room`: the circuit cannot deliver – flow through the circuit, balancing, emitter size, or the curve is too low for this room |
| rarely open | too warm | heat arrives anyway (neighbouring rooms, sun, thermal mass); the curve can likely go down |
| mostly ≤ 1 of ≥ 4 circuits open | – | `few_open_circuits`: little circulating water; can shorten compressor runs (less relevant with a buffer tank) |

### Homematic IP: valve sensors bridge

Wall thermostats with a built-in relay (HmIP-BWTH) switch underfloor actuators directly; switch
actuators (HmIP-FSM) do the same for other thermostats. The Homematic IP cloud reports the relay
state (`valvePosition` of the internal switch channel), but Home Assistant's Homematic IP
integration does not create an entity for it. With the option **Create Homematic IP valve
sensors**, Heat Pump Insights adds one binary sensor per thermostat relay and per switch actuator
in a heating group, attached to the existing device. History starts when the option is enabled.
This is a bridge until Home Assistant exposes the value itself.

## Limitations

- Without valve states, a throttled room (valve mostly closed) and a starved room look alike
  from the temperature alone.
- Thermal (wax) actuators need a few minutes to open; short relay pulses are not full openings.
- Thermostats measure at one spot; sun, cooking or open windows show up as deviations.
- Rooms whose thermostat is in "off" or frost-protection mode should be left out.
