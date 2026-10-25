"""Valve state sensors bridged from Homematic IP (optional, opt-in).

Homematic IP wall thermostats with a built-in relay (e.g. HmIP-BWTH) and
switch actuators in a heating group drive underfloor heating actuators. The
Homematic IP cloud reports whether that output is on, but the Home Assistant
integration does not create an entity for it. These binary sensors read it
from the running Homematic IP integration so the recorder keeps a history.

This is a bridge: it reads raw data of another integration and may need an
update if that integration changes. It becomes unnecessary once Home
Assistant exposes the value itself.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_HMIP_VALVES

HMIP_DOMAIN = "homematicip_cloud"
SWITCH_CHANNEL_TYPES = {"SWITCH_CHANNEL", "SWITCH_MEASURING_CHANNEL"}


def _valve_channel(device: Any, in_heating_group: bool) -> tuple[str, str] | None:
    """Return (channel key, field) holding the valve output state, if any."""
    channels = (getattr(device, "_rawJSONData", None) or {}).get("functionalChannels", {})
    for key, channel in channels.items():
        kind = channel.get("functionalChannelType")
        if kind == "INTERNAL_SWITCH_CHANNEL" and "valvePosition" in channel:
            return key, "valvePosition"
        if in_heating_group and kind in SWITCH_CHANNEL_TYPES and "on" in channel:
            return key, "on"
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    settings = entry.options or entry.data
    if not settings.get(CONF_HMIP_VALVES):
        return
    entities: list[HmipValveSensor] = []
    for hmip_entry in hass.config_entries.async_loaded_entries(HMIP_DOMAIN):
        home = getattr(getattr(hmip_entry, "runtime_data", None), "home", None)
        if home is None:
            continue
        group_of: dict[str, str] = {}
        for group in getattr(home, "groups", []):
            if getattr(group, "groupType", None) == "HEATING":
                for device in getattr(group, "devices", None) or []:
                    group_of[device.id] = group.label
        for device in getattr(home, "devices", []):
            room = group_of.get(device.id)
            if (found := _valve_channel(device, room is not None)) is not None:
                entities.append(HmipValveSensor(device, room, *found))
    async_add_entities(entities)


class HmipValveSensor(BinarySensorEntity):
    """On = valve actuator powered/open."""

    _attr_has_entity_name = True
    _attr_translation_key = "valve"
    _attr_device_class = BinarySensorDeviceClass.OPENING
    _attr_should_poll = False

    def __init__(self, device: Any, room: str | None, channel: str, field: str) -> None:
        self._device = device
        self._channel = channel
        self._field = field
        self._attr_unique_id = f"hmip_valve_{device.id}_{channel}"
        self._attr_device_info = DeviceInfo(identifiers={(HMIP_DOMAIN, device.id)})
        self._attr_extra_state_attributes = {"heating_group": room, "source": "homematicip_cloud"}

    def _channel_data(self) -> dict:
        channels = (getattr(self._device, "_rawJSONData", None) or {}).get("functionalChannels", {})
        return channels.get(self._channel, {})

    @property
    def available(self) -> bool:
        return self._field in self._channel_data() and not getattr(self._device, "unreach", False)

    @property
    def is_on(self) -> bool | None:
        value = self._channel_data().get(self._field)
        if value is None:
            return None
        return bool(value) if isinstance(value, bool) else float(value) > 0

    async def async_added_to_hass(self) -> None:
        self._device.on_update(self._device_changed)
        self.async_on_remove(lambda: self._device.remove_callback(self._device_changed))

    @callback
    def _device_changed(self, *args: Any, **kwargs: Any) -> None:
        self.async_write_ha_state()
