"""Run the integration inside a real Home Assistant test instance."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import the repo's package before Home Assistant mounts its test config directory,
# which has its own ``custom_components`` package that would otherwise win.
import custom_components.heatpump_insights  # noqa: E402,F401


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    return
