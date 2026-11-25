"""Diagnostics: what your answers have taught, and the state of each source."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    hub = hass.data.get(DOMAIN)
    if hub is None:
        return {}
    answers = list(hub.calibration.answers.values())
    return {
        "learning": hub.learn,
        "calibration": hub.calibration.summary(),
        "answers": {"total": len(answers),
                    "right": sum(a["verdict"] == "right" for a in answers),
                    "wrong": sum(a["verdict"] == "wrong" for a in answers)},
        "labeled_folder": str(hub.labeled_dir),
        "sources": hub.status,
        "microphones": [{"id": m["id"], "ok": m["ok"], "error": m.get("error")} for m in hub.snapshot()["mics"]],
    }
