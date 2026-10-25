"""Key figures as sensors, so they show up on dashboards and keep long-term statistics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ROOMS, DOMAIN, ROLES
from .coordinator import InsightsCoordinator, InsightsData
from .runner import has_curve_roles, settings_of

RATINGS = ["good", "attention", "problem", "insufficient_data"]


@dataclass(frozen=True, kw_only=True)
class InsightsSensorDescription(SensorEntityDescription):
    value_fn: Callable[[InsightsData], Any]
    attrs_fn: Callable[[InsightsData], dict] | None = None
    needs: str | None = None
    """'curve' or 'rooms': only created when those roles are assigned."""


def _pct(value: float | None) -> float | None:
    return round(value * 100, 1) if value is not None else None


def _today_runtime(d: InsightsData) -> float | None:
    if d.today is None or not d.today.per_day:
        return None
    return d.today.per_day[-1]["runtime_h"]


def _findings(report) -> list[dict]:
    if report is None:
        return []
    return [
        {"code": f.code, "severity": f.severity, "message": f.message, "evidence": f.evidence}
        for f in report.findings
    ]


def _rooms_rated(data) -> bool:
    return data.rooms_week is not None and data.rooms_week.rated_rooms > 0


SENSORS: tuple[InsightsSensorDescription, ...] = (
    InsightsSensorDescription(
        key="starts_today",
        translation_key="starts_today",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: sum(day["starts"] for day in d.today.per_day) if d.today else None,
    ),
    InsightsSensorDescription(
        key="runtime_today",
        translation_key="runtime_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_today_runtime,
    ),
    InsightsSensorDescription(
        key="starts_per_day",
        translation_key="starts_per_day",
        icon="mdi:chart-bar",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.week.starts_per_day if d.week else None,
    ),
    InsightsSensorDescription(
        key="run_time_median",
        translation_key="run_time_median",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.week.run_time_min["median"] if d.week and d.week.run_time_min else None,
    ),
    InsightsSensorDescription(
        key="short_cycle_share",
        translation_key="short_cycle_share",
        icon="mdi:timer-alert-outline",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _pct(d.week.short_cycle_share) if d.week else None,
    ),
    InsightsSensorDescription(
        key="cycling_rating",
        translation_key="cycling_rating",
        icon="mdi:heat-pump",
        device_class=SensorDeviceClass.ENUM,
        options=RATINGS,
        value_fn=lambda d: d.week.rating if d.week else None,
        attrs_fn=lambda d: {
            "findings": _findings(d.week),
            "data_days": d.week.data_days if d.week else None,
        },
    ),
    InsightsSensorDescription(
        key="curve_slope",
        translation_key="curve_slope",
        icon="mdi:chart-line-variant",
        native_unit_of_measurement="K/K",
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        needs="curve",
        value_fn=lambda d: d.curve.slope_k_per_k if d.curve else None,
        attrs_fn=lambda d: {
            "hours_used": d.curve.hours_used if d.curve else None,
            "outdoor_range_c": d.curve.outdoor_range_c if d.curve else None,
            "r2": d.curve.r2 if d.curve else None,
            "findings": _findings(d.curve),
        },
    ),
    InsightsSensorDescription(
        key="flow_deviation",
        translation_key="flow_deviation",
        icon="mdi:thermometer-minus",
        native_unit_of_measurement="K",
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        needs="curve",
        value_fn=lambda d: (
            d.curve.tracking["mean_actual_minus_target_k"] if d.curve and d.curve.tracking else None
        ),
    ),
    InsightsSensorDescription(
        key="overheated_rooms",
        translation_key="overheated_rooms",
        icon="mdi:home-thermometer",
        state_class=SensorStateClass.MEASUREMENT,
        needs="rooms",
        value_fn=lambda d: len(d.rooms_week.overheated_rooms) if _rooms_rated(d) else None,
        attrs_fn=lambda d: {
            "rooms": d.rooms_week.overheated_rooms if d.rooms_week else [],
            "findings": _findings(d.rooms_week),
        },
    ),
    InsightsSensorDescription(
        key="limiting_room",
        translation_key="limiting_room",
        icon="mdi:home-alert-outline",
        needs="rooms",
        value_fn=lambda d: (d.rooms_week.limiting_room or "none") if _rooms_rated(d) else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator: InsightsCoordinator = entry.runtime_data
    settings = settings_of(entry)
    available = {"curve": has_curve_roles(settings), "rooms": bool(settings.get(CONF_ROOMS))}
    entities: list[SensorEntity] = [
        InsightsSensor(coordinator, description)
        for description in SENSORS
        if description.needs is None or available[description.needs]
    ]
    entities += [ValveOpenSensor(coordinator, room) for room in sorted(coordinator.data.valve_of)]
    entities.append(RolesSensor(coordinator))
    async_add_entities(entities)


class _Base(CoordinatorEntity[InsightsCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: InsightsCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Heat Pump Insights",
            model="Heating analysis",
            entry_type=DeviceEntryType.SERVICE,
        )


class InsightsSensor(_Base, SensorEntity):
    entity_description: InsightsSensorDescription

    def __init__(self, coordinator: InsightsCoordinator, description: InsightsSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None


class ValveOpenSensor(_Base, SensorEntity):
    """Share of the last 24 hours a room's valve was open."""

    _attr_translation_key = "valve_open"
    _attr_icon = "mdi:valve"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: InsightsCoordinator, room: str) -> None:
        super().__init__(coordinator)
        self._room = room
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_valve_open_{room}"
        self._attr_translation_placeholders = {"room": room}

    def _entry(self) -> dict | None:
        report = self.coordinator.data.rooms_day
        if report is None:
            return None
        return next((r for r in report.rooms if r["room"] == self._room), None)

    @property
    def native_value(self) -> float | None:
        entry = self._entry()
        return _pct(entry.get("valve_open_share")) if entry else None

    @property
    def extra_state_attributes(self) -> dict:
        entry = self._entry() or {}
        return {
            "room": self._room,
            "valve_entity": self.coordinator.data.valve_of.get(self._room),
            "valve_history_hours": round(entry.get("valve_history_days", 0) * 24, 1),
        }


class RolesSensor(_Base, SensorEntity):
    """Diagnostic sensor that tells dashboards which entities fill which role."""

    _attr_translation_key = "configuration"
    _attr_icon = "mdi:cog-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: InsightsCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_configuration"

    @property
    def native_value(self) -> str:
        return "ok"

    @property
    def extra_state_attributes(self) -> dict:
        settings = settings_of(self.coordinator.config_entry)
        return {
            "heat_pump": self.coordinator.config_entry.title,
            "roles": {role: settings.get(role) for role in ROLES if settings.get(role)},
            "valves_by_room": self.coordinator.data.valve_of,
        }
