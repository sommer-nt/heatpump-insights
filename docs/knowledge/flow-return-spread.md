# Flow/return spread (ΔT)

Spread = flow temperature − return temperature, while water is circulating and the compressor runs.

## What it tells you

With the heat output roughly fixed, spread and flow rate are inversely related
(`Q̇ ≈ 1.163 × V̇ × ΔT`, see [fundamentals](fundamentals.md#heat-output-from-flow-rate-and-spread)).

| Observation (space heating, steady run) | Interpretation | Confidence |
|---|---|---|
| ~3–7 K | Typical for heat pump systems (many are designed around 5 K) | Established practice |
| Consistently large (> 8–10 K) | Flow rate too low: pump speed, closed valves, dirty filter, air in the system. Forces a higher flow temperature → lower COP | Established practice; thresholds heuristic |
| Very small (< 2 K) at high output | Flow rate higher than necessary – more pump electricity; or sensors badly placed | Heuristic |
| Very small at low output | Normal for a modulating heat pump at minimum speed | Physics |

## Caveats

- Ignore the first minutes after a start and the time around defrost (spread turns negative
  during reverse-cycle defrost).
- Hot-water charging usually has its own, larger spread – analyse it separately.
- Clamp-on pipe sensors read lower than immersion sensors; a constant offset between flow and
  return sensors distorts the spread directly. Compare during standstill with the pump running
  (spread should be ~0).
