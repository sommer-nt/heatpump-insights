# Use cases

Each use case is a question a real owner asks, the tools the assistant should call, and what
a **good answer** must contain. These are the acceptance tests for the product: a release is
only as good as its answers to these questions (see [validation](validation.md)).

Status: ✅ implemented · 🔜 planned

---

## UC1 – "Is my heat pump OK?" (health check) ✅ partly

**Who:** any owner, basic setup.
**Tools:** `heatpump_describe` → `heatpump_analyze_cycles` (→ later all analyses).

A good answer:
- states the overall rating and the 1–3 most important findings in plain language,
- quotes the numbers (starts per day, median run time, share of short cycles),
- mentions data coverage and what could not be checked because a sensor is missing,
- offers one next step ("add a flow temperature sensor to check the heating curve").

## UC2 – "Is my heat pump short cycling? Why?" ✅

**Who:** owner who hears the unit switch on and off a lot.
**Tools:** `heatpump_analyze_cycles` with outdoor temperature.

A good answer:
- distinguishes *how often* (starts/day, worst hour) from *how short* (run time distribution),
- uses `by_outdoor_temp` to say **when** it happens – typically on mild days, the
  [modulation gap](knowledge/cycling.md#the-modulation-gap),
- lists likely causes in order of probability for this pattern and the matching, reversible
  remedies (see knowledge base), one change at a time,
- suggests re-running the analysis after a week to verify.

## UC3 – "Should I change my heating curve?" 🔜

**Who:** owner with flow and outdoor temperature (most vendor integrations).
**Tools:** `heatpump_heating_curve`, `heatpump_analyze_cycles`, room temperatures if mapped.

A good answer:
- shows the fitted actual curve (slope, offset, heating limit) and its scatter,
- relates it to comfort: rooms too warm → curve can go down; specific rooms cold → hydraulic
  balancing issue, not the curve,
- recommends a concrete step (e.g. "lower the parallel shift by 1–2 K") with the expected
  efficiency effect ([≈ 1.5–2.5 % per K](knowledge/fundamentals.md#flow-temperature-is-the-biggest-lever)).

## UC4 – "Did my change work?" 🔜

**Who:** owner who changed a setting last week.
**Tools:** `heatpump_energy_signature` (before vs. after), `heatpump_analyze_cycles` for both periods.

A good answer:
- compares **weather-normalised** consumption (energy signature / similar days), never raw totals,
- says how confident the comparison is (number of comparable days, temperature overlap),
- detects the change date automatically if the setting is a Home Assistant entity.

## UC5 – "Compare yesterday with a similar day last month" 🔜

**Tools:** `heatpump_energy_signature` with similar-day matching (outdoor mean, solar gain).

## UC6 – "How efficient is my heat pump really?" 🔜

**Who:** owner with a heat meter (or vendor heat estimates – flagged as estimates).
**Tools:** `heatpump_efficiency`.

A good answer separates measured COP from vendor-estimated values, reports seasonal
performance factor per period and splits heating and hot water when a mode sensor exists.

## UC7 – "Can I use more of my PV surplus for the heat pump?" 🔜 (later)

**Tools:** energy signature + PV production/grid sensors. Out of scope for v1, listed so the
architecture keeps room for it.

---

## Example dialogue (UC2)

> **User:** My heat pump seems to switch on and off constantly. Can you check the last week?
>
> **Assistant** *(calls `heatpump_describe`, then `heatpump_analyze_cycles(days=7)`)*:
> Over the last 7 days (98 % data coverage) your compressor started **31 times per day** on
> average. **64 % of runs were shorter than 10 minutes**, with up to 4 starts in a single hour.
> It is concentrated on mild days: at 9–12 °C outdoors there were 52 starts per day, at
> 0–3 °C only 9. That pattern means the house needs less heat than the heat pump can deliver
> at its lowest output, so it switches on and off.
>
> Things to try, one at a time:
> 1. If room thermostats close underfloor circuits, open them fully – the heat pump then sees
>    more water volume and runs longer.
> 2. If rooms get warmer than needed, lower the heating curve slightly – overheated rooms make
>    thermostats close, which cuts the water flow and shortens runs.
> 3. If your controller has a minimum pause or switching hysteresis setting, increase it.
>
> I can't check the heating curve itself because no flow temperature sensor is configured.
> Re-run this analysis in a week to see whether the starts per day went down.

*(Figures in this dialogue are illustrative.)*
