# Contributing

Thank you! Heat Pump Insights only works for "every heat pump" if owners of every heat pump help.

## Ways to help

1. **Share data (most valuable right now).** Anonymised 10-day exports from your installation
   let us validate and tune the analyses. See [validation plan](docs/validation.md#phase-1--real-data-collection).
   Open an issue "Data: <brand> <model class>" to volunteer.
2. **Device profiles.** Map your integration's entities to roles – see [profiles/](profiles/README.md).
3. **Knowledge.** Improve the [knowledge base](docs/knowledge/README.md), with sources.
4. **Code.** Analyses, tests, the export tool – see the [roadmap](docs/roadmap.md).
5. **Translations.** `custom_components/heatpump_insights/translations/`.

## Development

```bash
pip install pytest ruff
python -m pytest -q          # analysis core tests, no Home Assistant needed
ruff check . && ruff format --check .
python tools/make_figures.py # regenerate docs/figures (needs numpy)
```

Rules:
- `analysis/` must not import Home Assistant.
- Every analysis change comes with tests; changes that alter results bump `ANALYSIS_VERSION`.
- Thresholds are documented in the knowledge base with their confidence label.
- Tool results: machine-readable finding codes, no prose advice in code.
