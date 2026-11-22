"""Outside sources: BirdNET-Go, ADS-B, fire dispatch."""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import re

import aiohttp

from .const import ADSB_PROVIDERS, TYPES_URL, USER_AGENT

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
