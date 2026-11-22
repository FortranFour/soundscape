"""What is being heard right now."""
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .entity import SoundscapeEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([NowHearing(hass.data[DOMAIN])])


class NowHearing(SoundscapeEntity, SensorEntity):
    _attr_name = "Now hearing"
    _attr_icon = "mdi:waveform"

    def __init__(self, hub) -> None:
        super().__init__(hub, "now_hearing")

    def _active(self):
        return sorted(self.hub.fusion.active.values(), key=lambda e: -e.conf)

    def _value(self):
        return tuple((e.id, e.label, e.mic) for e in self._active())

    @property
    def native_value(self) -> str:
        ev = self._active()
        return ev[0].label if ev else "Quiet"

    @property
    def extra_state_attributes(self):
        return {"sounds": [
            {k: d[k] for k in ("label", "detail", "mic", "compass", "conf")}
            for d in (e.as_dict() for e in self._active())]}
