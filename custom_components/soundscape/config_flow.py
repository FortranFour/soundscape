"""Config and options flow for Soundscape."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector as sel

from . import fetch_frigate_cameras, parse_overrides
from .const import (
    ADSB_PROVIDERS, CONF_ADSB, CONF_ADSB_RADIUS, CONF_ADSB_URL, CONF_BIRDNET_URL, CONF_CAMERAS,
    CONF_DISPATCH, CONF_FRIGATE_URL, CONF_GEOMETRY, CONF_IGNORE, CONF_OVERRIDES, CONF_TEMPLATE,
    DEFAULT_TEMPLATE, DOMAIN,
)
from .fusion import CLASSES


def _frigate_url(hass) -> str:
    for entry in hass.config_entries.async_entries("frigate"):
        if url := entry.data.get("url"):
            return url
    return ""


def _sources_schema(d: dict) -> vol.Schema:
    text = sel.TextSelector()
    return vol.Schema({
        vol.Optional(CONF_FRIGATE_URL, description={"suggested_value": d.get(CONF_FRIGATE_URL, "")}): text,
        vol.Optional(CONF_BIRDNET_URL, description={"suggested_value": d.get(CONF_BIRDNET_URL, "")}): text,
        vol.Required(CONF_ADSB, default=d.get(CONF_ADSB, "adsb.fi")): sel.SelectSelector(
            sel.SelectSelectorConfig(options=[*ADSB_PROVIDERS, "custom", "off"],
                                     mode=sel.SelectSelectorMode.DROPDOWN, translation_key="adsb")),
        vol.Optional(CONF_ADSB_URL, description={"suggested_value": d.get(CONF_ADSB_URL, "")}): text,
        vol.Required(CONF_ADSB_RADIUS, default=d.get(CONF_ADSB_RADIUS, 15)): sel.NumberSelector(
            sel.NumberSelectorConfig(min=3, max=60, step=1, unit_of_measurement="km",
                                     mode=sel.NumberSelectorMode.BOX)),
        vol.Required(CONF_DISPATCH, default=d.get(CONF_DISPATCH, "off")): sel.SelectSelector(
            sel.SelectSelectorConfig(options=["off", "sdfd"], mode=sel.SelectSelectorMode.DROPDOWN,
                                     translation_key="dispatch")),
    })


def _cameras_schema(d: dict, cameras: dict) -> vol.Schema:
    names = sorted(set(cameras) | set(d.get(CONF_CAMERAS, [])))
    default = d.get(CONF_CAMERAS) or [n for n, c in cameras.items() if c["audio"]]
    multi = lambda opts: sel.SelectSelector(sel.SelectSelectorConfig(  # noqa: E731
        options=opts, multiple=True, mode=sel.SelectSelectorMode.DROPDOWN))
    return vol.Schema({
        vol.Optional(CONF_CAMERAS, default=default): multi(names),
        vol.Required(CONF_TEMPLATE, default=d.get(CONF_TEMPLATE, DEFAULT_TEMPLATE)): sel.TextSelector(),
        vol.Optional(CONF_OVERRIDES, description={"suggested_value": d.get(CONF_OVERRIDES, "")}):
            sel.TextSelector(sel.TextSelectorConfig(multiline=True)),
        vol.Optional(CONF_IGNORE, default=d.get(CONF_IGNORE, [])): multi(
            [sel.SelectOptionDict(value=k, label=v[0]) for k, v in CLASSES.items()]),
    })


def _mic_names(d: dict) -> list[str]:
    return list(dict.fromkeys([*d.get(CONF_CAMERAS, []), *parse_overrides(d.get(CONF_OVERRIDES, ""))]))


def _geometry_schema(d: dict) -> vol.Schema:
    names = _mic_names(d)
    geo = d.get(CONF_GEOMETRY) or {}
    fields = {}
    for i, name in enumerate(names):
        bearing, distance = geo.get(name) or (round(i * 360 / len(names)), 10)
        fields[vol.Required(f"{name} bearing", default=bearing)] = sel.NumberSelector(
            sel.NumberSelectorConfig(min=0, max=359, step=1, unit_of_measurement="°",
                                     mode=sel.NumberSelectorMode.BOX))
        fields[vol.Required(f"{name} distance", default=distance)] = sel.NumberSelector(
            sel.NumberSelectorConfig(min=0, max=200, step=0.5, unit_of_measurement="m",
                                     mode=sel.NumberSelectorMode.BOX))
    return vol.Schema(fields)


def _geometry(d: dict, user_input: dict) -> dict:
    return {n: [user_input[f"{n} bearing"], user_input[f"{n} distance"]] for n in _mic_names(d)}


class _Steps:
    """The three steps, shared by first setup and by Configure."""

    _d: dict
    _cams: dict

    async def _sources(self, step: str, user_input):
        errors = {}
        if user_input is not None:
            self._d.update({k: "" for k in (CONF_FRIGATE_URL, CONF_BIRDNET_URL, CONF_ADSB_URL)})
            self._d.update(user_input)
            self._cams = {}
            if self._d.get(CONF_ADSB) == "custom" and not self._d.get(CONF_ADSB_URL):
                errors[CONF_ADSB_URL] = "adsb_url"
            if url := self._d.get(CONF_FRIGATE_URL):
                try:
                    self._cams = await fetch_frigate_cameras(self.hass, url)
                except Exception:  # noqa: BLE001
                    errors[CONF_FRIGATE_URL] = "cannot_connect"
            if not errors:
                return await self.async_step_cameras()
        return self.async_show_form(step_id=step, data_schema=_sources_schema(self._d), errors=errors)

    async def async_step_cameras(self, user_input=None):
        errors = {}
        if user_input is not None:
            self._d.update({CONF_OVERRIDES: "", **user_input})
            if _mic_names(self._d):
                return await self.async_step_geometry()
            errors["base"] = "no_mics"
        return self.async_show_form(step_id="cameras", data_schema=_cameras_schema(self._d, self._cams),
                                    errors=errors)

    async def async_step_geometry(self, user_input=None):
        if user_input is not None:
            self._d[CONF_GEOMETRY] = _geometry(self._d, user_input)
            return self._finish()
        return self.async_show_form(step_id="geometry", data_schema=_geometry_schema(self._d))


class SoundscapeConfigFlow(_Steps, ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._d, self._cams = {}, {}

    async def async_step_user(self, user_input=None):
        if not self._d:
            self._d = {CONF_FRIGATE_URL: _frigate_url(self.hass)}
        return await self._sources("user", user_input)

    def _finish(self):
        return self.async_create_entry(title="Soundscape", data={}, options=self._d)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SoundscapeOptionsFlow(entry)


class SoundscapeOptionsFlow(_Steps, OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self._d, self._cams = dict(entry.options), {}

    async def async_step_init(self, user_input=None):
        return await self._sources("init", user_input)

    def _finish(self):
        return self.async_create_entry(title="", data=self._d)
