# Heating curve

The heating curve (*Heizkurve*, weather compensation) sets the target flow temperature from the
outdoor temperature: colder outside → warmer water. It is the single most important setting
for efficiency ([fundamentals](fundamentals.md#flow-temperature-is-the-biggest-lever)).

![Heating curve](../figures/heating_curve.svg)

## Parameters

| Parameter | Effect | Vendor names (examples) |
|---|---|---|
| **Slope** (*Neigung*) | How much the flow temperature rises per kelvin of colder weather | slope, gradient, curve number |
| **Parallel shift** (*Niveau*) | Moves the whole curve up/down by a fixed amount | shift, offset, level, room setpoint |
| **Heating limit** (*Heizgrenze*) | Outdoor temperature above which heating stops | summer/winter switch-over, heating limit |
| Min/max flow temperature | Clamp the curve | – |

Vendors define curves differently (some by slope and shift, some by a design point such as
"35 °C flow at −10 °C"), and many curves are slightly bent rather than straight. We therefore
analyse the **actual** flow temperature against outdoor temperature, not the vendor's formula.
*Established practice.*

## Typical ranges

| Emitters | Typical design flow temperature at design outdoor temperature | Confidence |
|---|---|---|
| Underfloor heating | ~30–35 °C | Established practice |
| Low-temperature / oversized radiators | ~40–45 °C | Established practice |
| Standard radiators, older buildings | ~45–55 °C | Established practice |

Heating limits of roughly 15 °C for older and 12 °C or lower for well-insulated buildings are
common starting points. *Heuristic.*

## Tuning procedure (what the assistant should recommend)

*Established practice:*
1. Set all room thermostats/valves fully open in the rooms the heat pump controls.
2. Problem appears **in cold weather** (rooms cold/warm when it is freezing) → adjust the
   **slope**. Problem appears **in mild weather** → adjust the **shift**.
3. Change in small steps (1–2 K shift, or one slope step) and wait 1–2 days – underfloor
   heating reacts slowly.
4. Go down until the coldest room you care about is *just* comfortable; single rooms that stay
   cold are a hydraulic balancing / emitter issue, not a curve issue.

## How we will analyse it (`heatpump_heating_curve`, planned)

- Hourly means of flow and outdoor temperature from long-term statistics (works over whole seasons).
- Only hours with the compressor running in **heating** mode (exclude hot water, defrost,
  standstill – flow temperature then says nothing about the curve).
- Linear fit (robust regression) → slope, flow temperature at 0 °C and at design temperature,
  scatter (R², residuals). Curvature check with a quadratic term.
- With room temperatures: are rooms above setpoint? → headroom to lower the curve.
- With the energy signature: estimated heating limit (zero crossing).
- Output always includes the number of hours used and the outdoor temperature range covered –
  a curve fitted only between 5 and 12 °C says little about −10 °C.
