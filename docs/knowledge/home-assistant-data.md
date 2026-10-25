# Home Assistant data – what we can and cannot see

## Retention

| Data | Resolution | Kept | Needed for |
|---|---|---|---|
| **States** (history) | every state change | `recorder: purge_keep_days`, **default 10 days** | cycle detection, run times |
| **Short-term statistics** | 5-minute mean/min/max | same period as states | coarse cycling, daily figures |
| **Long-term statistics** | hourly mean/min/max (or sum for energy) | **forever**, but only for sensors with a `state_class` | heating curve, energy signature over seasons |

If you want cycle analysis over longer periods, increase `purge_keep_days` (e.g. 30) – at the
cost of database size. Long-term statistics require the sensor to have `state_class:
measurement` (temperatures, power) or `total`/`total_increasing` (energy).

## Sampling

- Home Assistant stores a new state only when the value changes (or the integration pushes an
  update). A power sensor that reports every few seconds gives an excellent picture; one that
  reports every 5 minutes cannot resolve runs shorter than ~10 minutes.
- We treat every series as a **step function**: a value is valid until the next one. We never
  interpolate between samples.
- The History panel's "significant changes only" filter does not apply to our tools; we read all
  state changes.

## Gaps and units

- `unknown` / `unavailable` (restarts, Wi-Fi drops) become **gaps**. Runs that touch a gap are
  marked truncated; results report `coverage_share` and `longest_data_gap_min`.
- Units are converted from the entity's current unit: kW/MW → W, °F → °C.

## Privacy

Tools return aggregates (per day, per temperature bin), never raw series or entity names other
than those the user mapped.
