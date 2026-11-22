"""Soundscape: what the microphones around the house hear, and where."""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event as HAEvent, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify

from .capture import Capture
from .const import (
    CONF_ADSB, CONF_ADSB_RADIUS, CONF_ADSB_URL, CONF_BIRDNET_URL, CONF_CAMERAS, CONF_DISPATCH,
    CONF_FRIGATE_URL, CONF_GEOMETRY, CONF_IGNORE, CONF_OVERRIDES, CONF_TEMPLATE, DEFAULT_TEMPLATE,
    DOMAIN, EVENT, SAMPLE_RATE, VERSION,
)
from .dsp import DB_MAX, DB_MIN, N_BANDS, Analyzer
from .fusion import AIR, FRIGATE_AUDIO, FRIGATE_MOVING, Fusion, Mic, prepare_aircraft
from .providers import Dispatch, birdnet_stream, fetch_aircraft, fetch_types, norm

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
SIGNAL = f"{DOMAIN}_update"
BACKLOG_S = 90
CARD_URL = f"/{DOMAIN}_static/soundscape-card.js"


def parse_overrides(text: str) -> dict[str, str]:
    out = {}
    for line in (text or "").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            name, url = line.split("=", 1)
            if name.strip() and url.strip():
                out[name.strip()] = url.strip()
    return out


async def fetch_frigate_cameras(hass: HomeAssistant, url: str) -> dict[str, dict]:
    """Camera name -> {audio: bool, path: restream path or None}."""
    session = async_get_clientsession(hass)
    async with session.get(url.rstrip("/") + "/api/config", timeout=aiohttp.ClientTimeout(total=10)) as resp:
        resp.raise_for_status()
        config = await resp.json(content_type=None)
    out = {}
    for name, cam in (config.get("cameras") or {}).items():
        inputs = (cam.get("ffmpeg") or {}).get("inputs") or []
        inputs.sort(key=lambda i: 0 if "audio" in (i.get("roles") or []) else 1)
        path = None
        for item in inputs:
            parts = urlsplit(item.get("path") or "")
            if parts.hostname in ("127.0.0.1", "localhost") and parts.scheme == "rtsp":
                path = parts.path.lstrip("/")  # a go2rtc restream: reachable on Frigate's host
                break
        out[name] = {"audio": bool((cam.get("audio") or {}).get("enabled")), "path": path}
    return out


class Hub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self.opt = {**entry.data, **entry.options}
        self.session = async_get_clientsession(hass)
        self.captures: dict[str, Capture] = {}
        self.backlog: dict[str, bytearray] = {}
        self.subscribers: dict[int, tuple] = {}
        self.fusion: Fusion | None = None
        self.types: dict = {}
        self.meta: dict = {}
        self._unsubs: list = []
        self._tasks: list[asyncio.Task] = []
        self._tracked: set[str] = set()
        self._untrack = None
        self._slug: dict[str, str] = {}
        self._dispatch: Dispatch | None = None
        self._air_hint = 0.0
        self.status: dict[str, str] = {}

    # ------------------------------------------------------------ lifecycle
    async def async_start(self) -> None:
        hass, opt = self.hass, self.opt
        overrides = parse_overrides(opt.get(CONF_OVERRIDES, ""))
        frigate_url = (opt.get(CONF_FRIGATE_URL) or "").rstrip("/")
        frigate_host = urlsplit(frigate_url).hostname or ""
        paths: dict[str, dict] = {}
        if frigate_url:
            try:
                paths = await fetch_frigate_cameras(hass, frigate_url)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Soundscape: could not read Frigate's configuration (%s); "
                                "using the stream template for every camera", err)
        names = list(dict.fromkeys([*opt.get(CONF_CAMERAS, []), *overrides]))
        geometry = opt.get(CONF_GEOMETRY) or {}
        template = opt.get(CONF_TEMPLATE) or DEFAULT_TEMPLATE
        mics, urls = [], {}
        for i, name in enumerate(names):
            bearing, distance = geometry.get(name) or (round(i * 360 / max(1, len(names))), 10)
            mics.append(Mic(name, name.replace("_", " ").strip().capitalize(), float(bearing), float(distance)))
            self._slug[slugify(name)] = name
            path = (paths.get(name) or {}).get("path") or name
            urls[name] = overrides.get(name) or template.format(host=frigate_host, camera=path)

        sun = lambda: (s := hass.states.get("sun.sun")) is not None and s.state == "below_horizon"  # noqa: E731
        self.fusion = Fusion(mics, hass.config.latitude, hass.config.longitude,
                             ignore=opt.get(CONF_IGNORE) or (), adsb=opt.get(CONF_ADSB, "off") != "off",
                             night=sun)
        ref = Analyzer(SAMPLE_RATE)
        self.meta = {"bands": N_BANDS, "edges": [round(float(x), 1) for x in ref.band_edges],
                     "cols_per_s": ref.cols_per_s, "db_min": DB_MIN, "db_max": DB_MAX,
                     "backlog_s": BACKLOG_S, "version": VERSION}
        self._backlog_bytes = int(BACKLOG_S * ref.cols_per_s) * N_BANDS

        ffmpeg = get_ffmpeg_manager(hass).binary
        for mic in mics:
            self.backlog[mic.id] = bytearray()
            cap = Capture(ffmpeg, mic.id, urls[mic.id], SAMPLE_RATE, self._from_thread)
            self.captures[mic.id] = cap
            cap.start()

        self._unsubs.append(async_track_time_interval(hass, self._tick, timedelta(seconds=1)))
        self._unsubs.append(async_track_time_interval(hass, self._scan_entities, timedelta(minutes=2)))
        self._scan_entities()
        bg = self.entry.async_create_background_task
        if base := (opt.get(CONF_BIRDNET_URL) or "").strip():
            self._tasks.append(bg(hass, birdnet_stream(self.session, base, self._on_birdnet), "soundscape-birdnet"))
        if opt.get(CONF_ADSB, "off") != "off":
            self._tasks.append(bg(hass, self._aircraft_loop(), "soundscape-adsb"))
        if opt.get(CONF_DISPATCH, "off") == "sdfd":
            self._dispatch = Dispatch(self.session, hass.config.latitude, hass.config.longitude)
            self._tasks.append(bg(hass, self._dispatch_loop(), "soundscape-dispatch"))

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        if self._untrack:
            self._untrack()
        for task in self._tasks:
            task.cancel()
        for cap in self.captures.values():
            cap.stop()
        await self.hass.async_add_executor_job(lambda: [c.join(5) for c in self.captures.values()])

    # ------------------------------------------------------------- audio in
    def _from_thread(self, mic: str, cols: bytes, n: int, feats) -> None:
        self.hass.loop.call_soon_threadsafe(self._on_audio, mic, cols, n, feats)

    @callback
    def _on_audio(self, mic: str, cols: bytes, n: int, feats) -> None:
        now = time.time()
        if feats is not None and self.fusion:
            self.fusion.on_features(mic, feats, now)
        if not n:
            return
        log = self.backlog[mic]
        log += cols
        if len(log) > self._backlog_bytes * 1.25:
            del log[: len(log) - self._backlog_bytes]
        if self.subscribers:
            payload = {"type": "spec", "mic": mic, "t": now, "n": n,
                       "data": base64.b64encode(cols).decode()}
            for conn, msg_id, wanted in list(self.subscribers.values()):
                if wanted is None or mic in wanted:
                    conn.send_message(websocket_api.event_message(msg_id, payload))

    # ---------------------------------------------------- Frigate's entities
    @callback
    def _scan_entities(self, _now=None) -> None:
        """Find Frigate's audio sensors and object counts for our cameras."""
        found = set()
        slugs = sorted(self._slug, key=len, reverse=True)
        for state in self.hass.states.async_all(("binary_sensor", "sensor")):
            if self._parse(state.entity_id, slugs):
                found.add(state.entity_id)
        if found != self._tracked:
            if self._untrack:
                self._untrack()
            self._tracked = found
            self._untrack = (async_track_state_change_event(self.hass, list(found), self._on_state)
                             if found else None)
            for entity_id in found:
                if (st := self.hass.states.get(entity_id)) and st.state == "on":
                    self._apply(entity_id, st.state)

    def _parse(self, entity_id: str, slugs=None):
        domain, obj = entity_id.split(".", 1)
        for slug in slugs or sorted(self._slug, key=len, reverse=True):
            if not obj.startswith(slug + "_"):
                continue
            rest = obj[len(slug) + 1:]
            if domain == "binary_sensor" and rest.endswith("_sound") and rest[:-6] in FRIGATE_AUDIO:
                return self._slug[slug], "audio", rest[:-6]
            if domain == "sensor" and rest.endswith("_active_count") and rest[:-13] in FRIGATE_MOVING:
                return self._slug[slug], "object", rest[:-13]
            if domain == "sensor" and rest == "dog_count":
                return self._slug[slug], "object", "dog"
            return None
        return None

    @callback
    def _on_state(self, event: HAEvent) -> None:
        if new := event.data.get("new_state"):
            self._apply(event.data["entity_id"], new.state)

    def _apply(self, entity_id: str, state: str) -> None:
        parsed = self._parse(entity_id)
        if not parsed or not self.fusion:
            return
        mic, kind, label = parsed
        now = time.time()
        if kind == "audio":
            self.fusion.on_frigate_audio(mic, label, state == "on", now)
            if FRIGATE_AUDIO[label] in AIR and state == "on":
                self._air_hint = now
        else:
            try:
                count = int(float(state))
            except ValueError:
                count = 0
            self.fusion.on_frigate_object(mic, label, count, now)

    # ------------------------------------------------------------ BirdNET-Go
    def _mic_for(self, *names) -> str | None:
        for name in names:
            for mic in self.fusion.mics.values():
                if name and norm(name) in (norm(mic.id), norm(mic.name)):
                    return mic.id
        return None

    @callback
    def _on_birdnet(self, kind: str, payload) -> None:
        now = time.time()
        if kind == "detection":
            src = payload.get("source") or {}
            self.fusion.on_birdnet(self._mic_for(src.get("displayName"), src.get("id")),
                                   payload.get("commonName") or "", payload.get("scientificName") or "",
                                   float(payload.get("confidence") or 0), now)
            return
        for item in payload if isinstance(payload, list) else [payload]:
            if item.get("status") != "active":
                continue
            self.fusion.on_birdnet(self._mic_for(item.get("source"), item.get("sourceID")),
                                   item.get("species") or "", item.get("scientificName") or "", 0.0, now, ttl=8)

    # ----------------------------------------------------------------- loops
    async def _aircraft_loop(self) -> None:
        store = Store(self.hass, 1, f"{DOMAIN}_aircraft_types")
        saved = await store.async_load() or {}
        self.types = saved.get("types") or {}
        if time.time() - saved.get("at", 0) > 30 * 86400:
            try:
                self.types = await fetch_types(self.session)
                await store.async_save({"at": time.time(), "types": self.types})
            except Exception as err:  # noqa: BLE001
                _LOGGER.info("Soundscape: aircraft type list not refreshed (%s)", err)
        opt, cfg = self.opt, self.hass.config
        fails = 0
        while True:
            try:
                raw = await fetch_aircraft(self.session, opt.get(CONF_ADSB),
                                           (opt.get(CONF_ADSB_URL) or "") if opt.get(CONF_ADSB) == "custom" else "",
                                           cfg.latitude, cfg.longitude, float(opt.get(CONF_ADSB_RADIUS, 15)))
                self.fusion.set_aircraft(prepare_aircraft(raw, cfg.latitude, cfg.longitude, self.types), time.time())
                self.status["adsb"], fails = "ok", 0
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                fails += 1
                self.status["adsb"] = f"unreachable: {err}"[:120]
            # Ask often only while something in the air is being heard or looked at.
            busy = self.subscribers or time.time() - self._air_hint < 60
            await asyncio.sleep(min(300, (10 if busy else 40) * (1 + fails)))

    async def _dispatch_loop(self) -> None:
        done: dict[int, int] = {}
        while True:
            await asyncio.sleep(45)
            now = time.time()
            sirens = [e for e in [*self.fusion.active.values(), *self.fusion.history]
                      if e.cls == "siren" and now - e.start < 20 * 60 and done.get(e.id, 0) < 6]
            if not sirens:
                continue
            for ev in sirens:
                done[ev.id] = done.get(ev.id, 0) + 1
                try:
                    hits = await self._dispatch.nearby(dt_util.as_local(datetime.fromtimestamp(ev.start, dt_util.UTC)))
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001
                    self.status["dispatch"] = f"unreachable: {err}"[:120]
                    break
                self.status["dispatch"] = "ok"
                if hits:
                    ev.extra["dispatch"] = hits
                    first = hits[0]
                    line = f"Dispatch: {first['type']}, {first['address']} ({first['units']}), about {first['km']} km"
                    ev.evidence = [x for x in ev.evidence if not x.startswith("Dispatch")] + [line]

    # ------------------------------------------------------------------ tick
    @callback
    def _tick(self, _now=None) -> None:
        now = time.time()
        started, ended = self.fusion.tick(now)
        for ev, phase in [*((e, "start") for e in started), *((e, "end") for e in ended)]:
            self.hass.bus.async_fire(EVENT, {"phase": phase, **{k: v for k, v in ev.as_dict().items()
                                                              if k not in ("levels", "extra")}})
        if any(e.cls in AIR for e in self.fusion.active.values()) or any(
                m.feats and now - m.feats_at < 4 and m.feats.excess.get("low", 0) > 4
                for m in self.fusion.mics.values()):
            self._air_hint = now
        async_dispatcher_send(self.hass, SIGNAL)
        if self.subscribers:
            snap = {"type": "state", **self.snapshot()}
            for conn, msg_id, _ in list(self.subscribers.values()):
                conn.send_message(websocket_api.event_message(msg_id, snap))

    def snapshot(self) -> dict:
        snap = self.fusion.snapshot(time.time())
        for mic in snap["mics"]:
            cap = self.captures.get(mic["id"])
            mic["error"] = None if cap is None or cap.running else (cap.error or "connecting")
        snap["status"] = self.status
        return snap


# ---------------------------------------------------------------- websocket
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/subscribe",
    vol.Optional("mics"): [str],
    vol.Optional("backlog", default=True): bool,
})
@callback
def ws_subscribe(hass: HomeAssistant, connection, msg) -> None:
    hub: Hub | None = hass.data.get(DOMAIN)
    if hub is None or hub.fusion is None:
        connection.send_error(msg["id"], "not_ready", "Soundscape is not set up")
        return
    key = id(connection) * 100000 + msg["id"]
    wanted = set(msg["mics"]) if msg.get("mics") else None
    hub.subscribers[key] = (connection, msg["id"], wanted)
    connection.subscriptions[msg["id"]] = lambda: hub.subscribers.pop(key, None)
    connection.send_result(msg["id"])
    backlog = {}
    if msg["backlog"]:
        for mic, data in hub.backlog.items():
            if wanted is None or mic in wanted:
                backlog[mic] = base64.b64encode(bytes(data[-hub._backlog_bytes:])).decode()
    connection.send_message(websocket_api.event_message(
        msg["id"], {"type": "init", "meta": hub.meta, "backlog": backlog, **hub.snapshot()}))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if f"{DOMAIN}_static" not in hass.data:
        hass.data[f"{DOMAIN}_static"] = True
        await hass.http.async_register_static_paths([
            StaticPathConfig(f"/{DOMAIN}_static", str(Path(__file__).parent / "www"), False)])
        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
        websocket_api.async_register_command(hass, ws_subscribe)
    hub = Hub(hass, entry)
    await hub.async_start()
    hass.data[DOMAIN] = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and (hub := hass.data.pop(DOMAIN, None)):
        await hub.async_stop()
    return ok
