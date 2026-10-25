"""Collect what Home Assistant knows about each entity, for role discovery."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .analysis.discovery import EntityInfo, discover_roles, room_candidates
from .const import DOMAIN

DOMAINS = ("sensor", "number", "input_number", "climate")


def entity_infos(hass: HomeAssistant) -> list[EntityInfo]:
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    infos = []
    for state in hass.states.async_all(DOMAINS):
        entry = entities.async_get(state.entity_id)
        if entry is not None and entry.platform == DOMAIN:
            continue
        device = devices.async_get(entry.device_id) if entry and entry.device_id else None
        infos.append(
            EntityInfo(
                state.entity_id,
                str(state.attributes.get("friendly_name") or ""),
                device_class=state.attributes.get("device_class"),
                unit=state.attributes.get("unit_of_measurement"),
                state_class=state.attributes.get("state_class"),
                platform=entry.platform if entry else "",
                device_name=(device.name_by_user or device.name or "") if device else "",
                translation_key=(entry.translation_key or "") if entry else "",
                available=state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN),
            )
        )
    return infos


def discover(hass: HomeAssistant) -> tuple[dict[str, dict], list[str]]:
    infos = entity_infos(hass)
    return discover_roles(infos), room_candidates(infos)
