"""Periodic analyses that feed the sensors.

"Today" figures are refreshed every 15 minutes; the multi-day analyses (cycling over
7 days, heating curve over 30 days, rooms) once an hour, because they read much
more history from the recorder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .analysis import CurveReport, CycleReport, RoomsReport
from .const import CONF_ROOMS, DOMAIN
from .runner import async_run_curve, async_run_cycles, async_run_rooms, has_curve_roles, settings_of

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=15)
HEAVY_INTERVAL = timedelta(hours=1)
CYCLE_DAYS = 7
CURVE_DAYS = 30
ROOM_DAYS = 7


@dataclass(slots=True)
class InsightsData:
    today: CycleReport | None = None
    week: CycleReport | None = None
    curve: CurveReport | None = None
    rooms_day: RoomsReport | None = None
    rooms_week: RoomsReport | None = None
    valve_of: dict[str, str] = field(default_factory=dict)
    """Room name → valve entity used for that room."""
    heavy_updated: datetime | None = None


class InsightsCoordinator(DataUpdateCoordinator[InsightsData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.data = InsightsData()

    async def _async_update_data(self) -> InsightsData:
        entry = self.config_entry
        now = dt_util.utcnow()
        data = self.data
        if data.heavy_updated is None or now - data.heavy_updated >= HEAVY_INTERVAL:
            settings = settings_of(entry)
            data.week = await self._safe(
                "cycles",
                async_run_cycles(self.hass, entry, now - timedelta(days=CYCLE_DAYS), now),
                data.week,
            )
            if has_curve_roles(settings):
                data.curve = await self._safe(
                    "curve",
                    async_run_curve(self.hass, entry, now - timedelta(days=CURVE_DAYS), now),
                    data.curve,
                )
            if settings.get(CONF_ROOMS):
                rooms = await self._safe(
                    "rooms",
                    async_run_rooms(self.hass, entry, now - timedelta(days=ROOM_DAYS), now, days=(1,)),
                    None,
                )
                if rooms is not None:
                    data.rooms_week, data.valve_of, _, (data.rooms_day,) = rooms
            data.heavy_updated = now
        threshold = data.week.threshold_w if data.week else None
        data.today = await self._safe(
            "today",
            async_run_cycles(self.hass, entry, dt_util.start_of_local_day(), now, threshold_w=threshold),
            data.today,
        )
        return data

    async def _safe(self, what: str, job, previous):
        """One failing analysis must not take the others (or the sensors) down."""
        try:
            return await job
        except Exception:
            _LOGGER.exception("Heat Pump Insights: %s analysis failed", what)
            return previous
