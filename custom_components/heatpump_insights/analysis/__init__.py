"""Vendor-independent heating analysis (no Home Assistant imports)."""

from .cycles import ANALYSIS_VERSION, CycleConfig, CycleReport, analyze_cycles
from .heating_curve import CurveConfig, CurveReport, analyze_heating_curve
from .rooms import RoomsConfig, RoomsReport, analyze_rooms
from .timeseries import Sample

__all__ = [
    "ANALYSIS_VERSION",
    "CurveConfig",
    "CurveReport",
    "CycleConfig",
    "CycleReport",
    "RoomsConfig",
    "RoomsReport",
    "Sample",
    "analyze_cycles",
    "analyze_heating_curve",
    "analyze_rooms",
]
