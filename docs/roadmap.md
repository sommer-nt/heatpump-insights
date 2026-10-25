# Roadmap

Milestones are gated by the [validation plan](validation.md), not by dates.

## v0.1 – Foundations ✅
- [x] Analysis core: step-function time series, coverage, local calendar days (DST-safe)
- [x] `heatpump_analyze_cycles`: power-based cycle detection, auto threshold, rating, outdoor bins
- [x] `heatpump_describe`: roles, current values, missing sensors
- [x] Config flow with role mapping, options for tuning; English and German UI
- [x] Knowledge base, figures, architecture, validation plan

## v0.2 – Real data
- [ ] `tools/export_history.py` + anonymised fixture format
- [ ] Fixtures from ≥ 10 installations / ≥ 5 brands; ground-truth labelling
- [ ] Tune cycle detection on real data; regression tests per fixture
- [ ] Operating-mode role (heating / hot water / defrost) to split runs

## v0.2+ – Heating curve and rooms ✅
- [x] `heatpump_heating_curve` on long-term statistics (controller target + actual flow, robust fit)
- [x] `heating_rooms`: room comfort from any climate entity, overheated and limiting rooms
- [x] Valve role per circuit; Homematic IP valve sensors bridge (BWTH relay, FSM in heating groups)
- [ ] Upstream: expose the HmIP-BWTH relay state in Home Assistant's Homematic IP integration
- [ ] Correlate closing circuits with compressor starts

## v0.4 – Base for every user ✅
- [x] Key figures as sensors with long-term statistics (cycling, heating curve, rooms, valve open share)
- [x] Dashboard strategy `custom:heatpump-insights`, generated from roles – no manual dashboard needed
- [x] Graded findings (info / check / act) with evidence; no physical-work recommendations

## v0.5 – Energy signature
- [ ] `heatpump_energy_signature`: before/after, similar days, degree days
- [ ] Automatic change detection for setting entities (curve slope/shift as HA entities)

## v0.4 – Spread and efficiency
- [ ] `heatpump_spread`
- [ ] `heatpump_efficiency`: COP/SPF from heat meter or flow rate, backup heater included

## v0.5 – Device profiles
- [ ] Profile format and auto-detection in the config flow
- [ ] Profiles for the most common integrations (ViCare, myPyllant, Daikin Onecta / P1P2,
      NIBE, Panasonic Aquarea / HeishaMon, MELCloud, ebusd, Stiebel Eltron ISG, Lambda, …)

## v1.0 – Public release
- [ ] Assistant evaluation passed (Phase 3)
- [ ] HACS default repository
- [ ] Documentation site, more translations

## Later / ideas
- PV surplus and household consumption ("Home Energy Expert")
- Optional chart images in tool results
- Opt-in write tools with explicit allow-list (e.g. adjust curve shift), always with before/after verification
- Standalone MCP server reusing the analysis core (for users outside Home Assistant)
- Proposal for Home Assistant core
