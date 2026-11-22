"""Shared entity base."""
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, VERSION


class SoundscapeEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub, key: str) -> None:
        self.hub = hub
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.entry.entry_id)}, name="Soundscape",
            entry_type=DeviceEntryType.SERVICE, sw_version=VERSION)
        self._last = None

    def _value(self):
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, f"{DOMAIN}_update", self._changed))

    @callback
    def _changed(self) -> None:
        value = self._value()
        if value != self._last:
            self._last = value
            self.async_write_ha_state()
