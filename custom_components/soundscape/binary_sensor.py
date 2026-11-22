"""One binary sensor per kind of sound, for automations."""
from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN, SENSOR_CLASSES
from .entity import SoundscapeEntity
from .fusion import AIR, CLASSES


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    hub = hass.data[DOMAIN]
    async_add_entities(Heard(hub, cls) for cls in SENSOR_CLASSES)


class Heard(SoundscapeEntity, BinarySensorEntity):
    def __init__(self, hub, cls: str) -> None:
        super().__init__(hub, cls)
        self._cls = cls
        self._attr_name = CLASSES[cls][0] if cls != "tiltrotor" else "Osprey"
        self._attr_icon = CLASSES[cls][1]

    def _events(self):
        match = AIR if self._cls == "aircraft" else (self._cls,)
        return [e for e in self.hub.fusion.active.values() if e.cls in match]

    def _value(self):
        ev = self._events()
        return (bool(ev), ev[0].label if ev else None, ev[0].mic if ev else None)

    @property
    def is_on(self) -> bool:
        return bool(self._events())

    @property
    def extra_state_attributes(self):
        ev = self._events()
        if not ev:
            return {}
        d = ev[0].as_dict()
        return {k: d[k] for k in ("label", "detail", "mic", "compass", "bearing", "conf", "evidence")}
