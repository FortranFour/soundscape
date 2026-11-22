"""Outside sources: BirdNET-Go, ADS-B, fire dispatch."""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from .const import ADSB_PROVIDERS, NOMINATIM_URL, SDFD_URL, TYPES_URL, USER_AGENT
from .fusion import geo_offset

_LOGGER = logging.getLogger(__name__)
HEADERS = {"User-Agent": USER_AGENT}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


async def birdnet_stream(session: aiohttp.ClientSession, base: str, on_event) -> None:
    """Follow BirdNET-Go's detection stream for ever. on_event(kind, payload)."""
    url = base.rstrip("/") + "/api/v2/detections/stream"
    wait = 15
    while True:
        try:
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=120)
            async with session.get(url, timeout=timeout, headers={"Accept": "text/event-stream"}) as resp:
                resp.raise_for_status()
                wait = 15
                kind, data = "message", []
                async for raw in resp.content:
                    line = raw.decode(errors="replace").rstrip("\r\n")
                    if line.startswith("event:"):
                        kind = line[6:].strip()
                    elif line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif not line:
                        if data and kind in ("detection", "pending"):
                            try:
                                on_event(kind, json.loads("\n".join(data)))
                            except Exception:  # noqa: BLE001
                                _LOGGER.debug("Soundscape: unreadable BirdNET-Go event", exc_info=True)
                        kind, data = "message", []
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Soundscape: BirdNET-Go stream dropped (%s)", err)
        await asyncio.sleep(wait)
        wait = min(300, wait * 2)


async def fetch_aircraft(session, provider: str, custom: str, lat: float, lon: float, km: float) -> list[dict]:
    """Aircraft near a point, readsb format. Works with a local tar1090 too."""
    template = custom or ADSB_PROVIDERS[provider]
    url = template.format(lat=round(lat, 4), lon=round(lon, 4), nm=max(1, round(km / 1.852)))
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=12), headers=HEADERS) as resp:
        resp.raise_for_status()
        body = await resp.json(content_type=None)
    return body.get("ac") or body.get("aircraft") or []


async def fetch_types(session) -> dict[str, list]:
    """ICAO type designators -> [name, description code such as L2J / H1T, wake class]."""
    async with session.get(TYPES_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        raw = await resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


class Dispatch:
    """San Diego Fire-Rescue's public incident list, matched to a siren by time and place.

    The list gives a street and cross street, never coordinates. Each street is
    looked up once with OpenStreetMap's geocoder, restricted to a box around the
    house, so "nearby" means: a street of that name runs within the box.
    """

    def __init__(self, session, lat: float, lon: float, radius_km: float = 6.0) -> None:
        self._session, self.lat, self.lon, self.radius = session, lat, lon, radius_km
        self._streets: dict[str, float | None] = {}

    async def nearby(self, start: datetime, window_min: int = 12) -> list[dict[str, Any]]:
        async with self._session.get(SDFD_URL, timeout=aiohttp.ClientTimeout(total=15), headers=HEADERS) as resp:
            resp.raise_for_status()
            incidents = await resp.json(content_type=None)
        out, lookups = [], 0
        for inc in incidents:
            try:
                when = datetime.fromisoformat(inc["ResponseDate"])
            except (KeyError, ValueError):
                continue
            if abs(when - start) > timedelta(minutes=window_min):
                continue
            street = re.split(r"[&/]", inc.get("Address") or "")[0].strip()
            street = re.sub(r"^\d+\s+(block\s+)?", "", street, flags=re.I)
            if not street:
                continue
            if street not in self._streets:
                if lookups >= 6:
                    continue
                lookups += 1
                try:
                    self._streets[street] = await self._locate(street)
                except Exception as err:  # noqa: BLE001 - try again next time
                    _LOGGER.debug("Soundscape: geocoding %s failed (%s)", street, err)
                    continue
                await asyncio.sleep(1.1)  # the geocoder asks for one request a second
            km = self._streets[street]
            if km is not None and km <= self.radius:
                out.append({"type": inc.get("CallType"), "address": (inc.get("Address") or "").strip(),
                            "cross": inc.get("CrossStreet") or "", "units": inc.get("UnitName") or "",
                            "time": inc["ResponseDate"], "km": round(km, 1)})
        out.sort(key=lambda i: i["km"])
        return out[:4]

    async def _locate(self, street: str) -> float | None:
        d = self.radius / 111.0 * 1.3
        params = {"q": f"{street}, San Diego, California", "format": "jsonv2", "limit": "5", "bounded": "1",
                  "viewbox": f"{self.lon - d},{self.lat + d},{self.lon + d},{self.lat - d}"}
        async with self._session.get(NOMINATIM_URL, params=params, headers=HEADERS,
                                     timeout=aiohttp.ClientTimeout(total=12)) as resp:
            resp.raise_for_status()
            hits = await resp.json(content_type=None)
        best = None
        for h in hits:
            m, _ = geo_offset(self.lat, self.lon, float(h["lat"]), float(h["lon"]))
            best = m / 1000 if best is None else min(best, m / 1000)
        return best
