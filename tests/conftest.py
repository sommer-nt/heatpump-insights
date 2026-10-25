"""Make the HA-free analysis package importable without Home Assistant installed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "heatpump_insights"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
