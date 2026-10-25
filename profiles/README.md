# Device profiles

A device profile maps the entities of a known Home Assistant integration to Heat Pump
Insights roles, so users don't have to pick them by hand. Profiles are plain data – no Python
needed – and the easiest way to contribute.

> Status: format draft. Auto-detection in the config flow is planned for v0.5.

## Format (draft)

```yaml
# profiles/vicare.yaml
integration: vicare            # Home Assistant integration domain
name: Viessmann ViCare
verified_with:                 # models the mapping was checked on
  - Vitocal 250-A
roles:
  # Each role lists match rules, tried in order. A rule matches an entity of the
  # integration's device by translation_key (preferred) or entity_id suffix.
  flow_temp:
    - translation_key: supply_temperature
  return_temp:
    - translation_key: return_temperature
  outdoor_temp:
    - translation_key: outside_temperature
  power:
    - translation_key: power_consumption_today   # example only – verify!
notes: >
  Power from the cloud API updates slowly; a local sub-meter gives better cycle detection.
```

## Rules

- Prefer `translation_key` (stable across languages and renames) over entity IDs.
- List the models you verified on; mark everything else as unverified.
- Note sampling limits (cloud polling intervals) – they matter for cycle detection.
- Never include personal data.
