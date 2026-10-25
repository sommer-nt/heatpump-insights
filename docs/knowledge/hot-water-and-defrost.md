# Hot water and defrost

Two operating modes that look like anomalies in every other analysis. Recognising them is
essential.

## Domestic hot water (DHW)

- The heat pump switches a valve and heats the tank to ~45–55 °C (higher with the backup
  heater). Higher temperature lift → **lower COP** than space heating. *Physics.*
- **Signature in the data:** flow temperature jumps well above the heating curve; often a
  distinct power level; regular timing (schedules) or after large draws.
- **Legionella / anti-bacteria programmes** heat to 60 °C or more, often weekly, often with the
  electric backup heater – visible as a power step and a COP of ~1 for that period.
- In a summer energy signature, DHW is the baseline that remains above the heating limit.

Without an operating-mode sensor we cannot reliably separate DHW from heating; tools say so in
their `assumptions`. A mode role is on the roadmap.

## Defrost (air-source only)

- When the outdoor coil is below 0 °C and the air is humid, frost builds up and blocks the
  airflow. Defrost is most frequent roughly between −5 and +5 °C at high humidity; in very cold,
  dry air it is rarer. *Physics / established practice.*
- Most units defrost by **reversing the cycle**: for a few minutes heat is taken *from* the
  heating water. **Signature:** flow temperature drops, spread becomes negative, power changes,
  outdoor fan stops.
- Defrost energy is a real cost and part of the measured COP – don't exclude it from
  efficiency figures, but do exclude defrost periods when fitting the heating curve.
- Unusually frequent defrosts at mild, dry conditions suggest airflow problems (placement,
  obstruction, snow) – an installer topic.

For cycle detection, defrost pauses shorter than 2 minutes are bridged; longer ones may split a
run (see [cycling](cycling.md#known-limitations)).
