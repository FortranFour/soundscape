"""Public emergency dispatch lists, matched to a siren by time and place.

Each feed below was live when it was added (November 2026). They are all
published by the agency itself; none needs an account. Agencies change these
without notice, so every parser is defensive and a feed that stops answering
simply contributes nothing.

Some feeds give coordinates. The rest give a street, a block or a ZIP code,
which is looked up once with OpenStreetMap's geocoder inside a box around the
house: "nearby" then means a street of that name runs within the box.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from .const import NOMINATIM_URL, USER_AGENT
from .fusion import geo_offset

_LOGGER = logging.getLogger(__name__)
HEADERS = {"User-Agent": USER_AGENT}


# ----------------------------------------------------------------- helpers
def _local(text: str, fmt: str, tz: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), fmt).replace(tzinfo=ZoneInfo(tz))
    except (ValueError, AttributeError):
        return None


def _iso(text: str, tz: str) -> datetime | None:
    try:
        when = datetime.fromisoformat((text or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=ZoneInfo(tz))


def _epoch_ms(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value) / 1000, UTC)
    except (TypeError, ValueError):
        return None


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(text) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))).replace("\xa0", " ").strip()


def html_rows(page: str, required: tuple[str, ...]) -> list[dict[str, str]]:
    """Rows of the first HTML table whose header names all of `required`."""
    for table in re.findall(r"<table\b.*?</table>", page, flags=re.S | re.I):
        rows = [[_clean(c) for c in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", r, flags=re.S | re.I)]
                for r in re.findall(r"<tr\b.*?</tr>", table, flags=re.S | re.I)]
        for i, head in enumerate(rows):
            low = [h.lower() for h in head]
            if all(any(req in h for h in low) for req in required):
                return [dict(zip(low, r)) for r in rows[i + 1:] if len(r) == len(head)]
    return []


def _col(row: dict[str, str], name: str) -> str:
    return next((v for k, v in row.items() if name in k), "")


def _inc(when, kind, address, cross="", units="", lat=None, lon=None, zip_code="") -> dict | None:
    if when is None:
        return None
    return {"when": when, "type": _clean(kind), "address": _clean(address), "cross": _clean(cross),
            "units": _clean(units), "lat": _num(lat), "lon": _num(lon), "zip": _clean(zip_code)}


# ----------------------------------------------------------------- parsers
def _sdfd(data, tz):
    return [_inc(_iso(i.get("ResponseDate"), tz), i.get("CallType"), i.get("Address"),
                 i.get("CrossStreet"), i.get("UnitName")) for i in data]


def _seattle(data, tz):
    return [_inc(_iso(i.get("datetime"), tz), i.get("type"), i.get("address"),
                 lat=i.get("latitude"), lon=i.get("longitude")) for i in data]


def _austin(data, tz):
    return [_inc(_iso(i.get("published_date"), tz), i.get("issue_reported"), i.get("address"),
                 units=i.get("agency"), lat=i.get("latitude"), lon=i.get("longitude")) for i in data]


def _dallas(data, tz):
    out = []
    for i in data:
        when = _iso(f"{(i.get('date') or '')[:10]}T{i.get('time') or ''}", tz)
        out.append(_inc(when, i.get("nature_of_call"), f"{i.get('block') or ''} {i.get('location') or ''}",
                        units=i.get("unit_number")))
    return out


def _tulsa(data, tz):
    items = ((data.get("Incidents") or {}).get("Incident")) or []
    out = []
    for i in items if isinstance(items, list) else [items]:
        cars = ((i.get("Vehicles") or {}).get("Vehicle")) or []
        cars = cars if isinstance(cars, list) else [cars]
        out.append(_inc(_local(i.get("ResponseDate"), "%m/%d/%Y %I:%M:%S %p", tz), i.get("Problem"),
                        i.get("Address"), units=", ".join(str(c.get("VehicleID") or "") for c in cars),
                        lat=i.get("Latitude"), lon=i.get("Longitude")))
    return out


def _ventura(data, tz):
    return [_inc(_local(i.get("responseDate"), "%m/%d/%y %H:%M", tz), i.get("incidentType"),
                 f"{i.get('block') or ''} {i.get('address') or ''}", units=i.get("units"),
                 lat=i.get("latitude"), lon=i.get("longitude")) for i in data]


def _sf(data, tz):
    return [_inc(_iso(i.get("received_datetime"), tz), i.get("call_type_final_desc") or i.get("call_type_original_desc"),
                 i.get("intersection_name"), units=i.get("agency"))
            for i in data if (i.get("intersection_name") or "Not Available") != "Not Available"]


def _phoenix(data, tz):
    out = []
    for f in data.get("features") or []:
        a, g = f.get("attributes") or {}, f.get("geometry") or {}
        out.append(_inc(_epoch_ms(a.get("Date")), a.get("NatureDesc"), a.get("GenLocInfo"),
                        units=re.sub(r":[^;]*", "", _clean(a.get("Units"))).replace(";", ","),
                        lat=g.get("y"), lon=g.get("x")))
    return out


def _nashville(data, tz):
    return [_inc(_epoch_ms(a.get("DispatchDateTime")), a.get("incident_type_id"), "", units=a.get("Unit_ID"),
                 zip_code=a.get("PostalCode"))
            for a in (f.get("attributes") or {} for f in data.get("features") or [])]


def _houston(page, tz):
    return [_inc(_local(_col(r, "call time"), "%m/%d/%Y %H:%M", tz), _col(r, "incident type"),
                 _col(r, "address"), _col(r, "cross street"), _col(r, "agency"))
            for r in html_rows(page, ("address", "call time", "incident type"))]


def _richmond(page, tz):
    return [_inc(_local(_col(r, "time received"), "%m/%d/%Y %H:%M", tz), _col(r, "call type"),
                 _col(r, "location"), units=f"{_col(r, 'agency')} {_col(r, 'unit')}")
            for r in html_rows(page, ("time received", "call type", "location"))]


def _orlando(page, tz):
    out = []
    for call in ET.fromstring(page).iter("CALL"):
        out.append(_inc(_local(call.findtext("DATE") or "", "%m/%d/%Y %H:%M", tz), call.findtext("DESC"),
                        call.findtext("LOCATION"), units=call.findtext("DISTRICT")))
    return out


_ARCGIS = "/query?where=1%3D1&outFields=*&f=json&outSR=4326&resultRecordCount=200&orderByFields="

# key: name, home of the agency (to offer the nearest), time zone, place for street lookups,
# address, parser. "text" marks feeds that are HTML or XML, not JSON.
FEEDS: dict[str, dict[str, Any]] = {
    "sdfd": {"name": "San Diego Fire-Rescue", "at": (32.72, -117.16), "tz": "America/Los_Angeles",
             "place": "San Diego, California", "parse": _sdfd,
             "url": "https://webapps.sandiego.gov/sdfiredispatch/api/v1/Incidents"},
    "seattle": {"name": "Seattle Fire", "at": (47.61, -122.33), "tz": "America/Los_Angeles",
                "place": "Seattle, Washington", "parse": _seattle,
                "url": "https://data.seattle.gov/resource/kzjm-xkqj.json?$order=datetime%20DESC&$limit=80"},
    "sf": {"name": "San Francisco law enforcement", "at": (37.77, -122.42), "tz": "America/Los_Angeles",
           "place": "San Francisco, California", "parse": _sf,
           "url": "https://data.sf.gov/resource/gnap-fj3t.json?$order=received_datetime%20DESC&$limit=200"},
    "ventura": {"name": "Ventura County Fire", "at": (34.27, -119.03), "tz": "America/Los_Angeles",
                "place": "Ventura County, California", "parse": _ventura,
                "url": "https://firefeeds.venturacounty.gov/api/incidents"},
    "phoenix": {"name": "Phoenix Fire (regional)", "at": (33.45, -112.07), "tz": "America/Phoenix",
                "place": "Phoenix, Arizona", "parse": _phoenix,
                "url": "https://maps.phoenix.gov/phxfire/rest/services/Active_Incidents__Public/MapServer/5"
                       + _ARCGIS + "Date%20DESC"},
    "austin": {"name": "Austin and Travis County Fire", "at": (30.27, -97.74), "tz": "America/Chicago",
               "place": "Austin, Texas", "parse": _austin,
               "url": "https://data.austintexas.gov/resource/wpu4-x69d.json?$order=published_date%20DESC&$limit=80"},
    "dallas": {"name": "Dallas Police", "at": (32.78, -96.80), "tz": "America/Chicago",
               "place": "Dallas, Texas", "parse": _dallas,
               "url": "https://www.dallasopendata.com/resource/9fxf-t2tr.json?$limit=400"},
    "houston": {"name": "Houston Fire and Police", "at": (29.76, -95.37), "tz": "America/Chicago",
                "place": "Houston, Texas", "parse": _houston, "text": True,
                "url": "https://cohweb.houstontx.gov/ActiveIncidents/Combined.aspx"},
    "tulsa": {"name": "Tulsa Fire", "at": (36.15, -95.99), "tz": "America/Chicago",
              "place": "Tulsa, Oklahoma", "parse": _tulsa,
              "url": "https://www.cityoftulsa.org/apps/opendata/tfd_dispatch.jsn"},
    "nashville": {"name": "Nashville Fire (by ZIP code)", "at": (36.16, -86.78), "tz": "America/Chicago",
                  "place": "Nashville, Tennessee", "parse": _nashville,
                  "url": "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/"
                         "Nashville_Fire_Department_Active_Incidents_view/FeatureServer/0"
                         + _ARCGIS + "DispatchDateTime%20DESC"},
    "orlando": {"name": "Orlando Police", "at": (28.54, -81.38), "tz": "America/New_York",
                "place": "Orlando, Florida", "parse": _orlando, "text": True,
                "url": "https://www1.cityoforlando.net/opd/activecalls/activecadpolice.xml"},
    "richmond": {"name": "Richmond, Virginia Police and Fire", "at": (37.54, -77.44), "tz": "America/New_York",
                 "place": "Richmond, Virginia", "parse": _richmond, "text": True,
                 "url": "https://apps.richmondgov.com/applications/activecalls/Home/ActiveCalls"},
}
AUTO_KM = 80.0


def nearest_feed(lat: float, lon: float) -> str | None:
    """The feed whose agency is closest to the house, if any is within reach."""
    best = min(FEEDS, key=lambda k: geo_offset(lat, lon, *FEEDS[k]["at"])[0])
    return best if geo_offset(lat, lon, *FEEDS[best]["at"])[0] <= AUTO_KM * 1000 else None


def resolve_feed(choice: str, lat: float, lon: float) -> str | None:
    if choice == "auto":
        return nearest_feed(lat, lon)
    return choice if choice in FEEDS else None


def street_of(address: str) -> str:
    """'3100 Rutz St', '7100-BLK JAHNKE RD', 'A ST / B ST', '8000 BLOCK & NW 1ST CT' -> the street."""
    parts = [p.strip() for p in re.split(r"[&/\\]| at ", address, flags=re.I) if p.strip()]
    for part in parts:
        street = re.sub(r"^(\d+[\d-]*\s*)?(-?\s*(blk|block)\b\.?(\s+of)?)?\s*", "", part, flags=re.I).strip(" ,")
        street = re.sub(r"\s*,\s*[A-Z]{2,4}$", "", street)  # trailing city code, e.g. ",PHX"
        if len(street) >= 3 and not street.isdigit():
            return street
    return ""


class Dispatch:
    def __init__(self, session: aiohttp.ClientSession, feed: str, lat: float, lon: float,
                 radius_km: float = 6.0) -> None:
        self._session, self.key, self.feed = session, feed, FEEDS[feed]
        self.lat, self.lon, self.radius = lat, lon, radius_km
        self._places: dict[str, float | None] = {}

    async def incidents(self) -> list[dict]:
        timeout = aiohttp.ClientTimeout(total=20)
        async with self._session.get(self.feed["url"], timeout=timeout, headers=HEADERS) as resp:
            resp.raise_for_status()
            body = await (resp.text() if self.feed.get("text") else resp.json(content_type=None))
        return [i for i in self.feed["parse"](body, self.feed["tz"]) if i]

    async def nearby(self, start: datetime, window_min: int = 12) -> list[dict[str, Any]]:
        """Incidents within a few minutes of `start` and within the radius, nearest first."""
        out, lookups = [], 0
        for inc in await self.incidents():
            if abs(inc["when"] - start) > timedelta(minutes=window_min):
                continue
            if inc["lat"] and inc["lon"]:
                km, exact = geo_offset(self.lat, self.lon, inc["lat"], inc["lon"])[0] / 1000, True
            else:
                exact = False
                query = street_of(inc["address"]) or inc["zip"]
                if not query:
                    continue
                if query not in self._places:
                    if lookups >= 6:
                        continue
                    lookups += 1
                    try:
                        self._places[query] = await self._locate(query, is_zip=not street_of(inc["address"]))
                    except Exception as err:  # noqa: BLE001 - try again next time
                        _LOGGER.debug("Soundscape: geocoding %s failed (%s)", query, err)
                        continue
                    await asyncio.sleep(1.1)  # the geocoder asks for one request a second
                km = self._places[query]
            if km is not None and km <= self.radius:
                out.append({"type": inc["type"], "address": inc["address"] or inc["zip"], "cross": inc["cross"],
                            "units": inc["units"], "time": inc["when"].isoformat(), "km": round(km, 1),
                            "exact": exact, "agency": self.feed["name"]})
        out.sort(key=lambda i: i["km"])
        return out[:4]

    async def _locate(self, query: str, is_zip: bool) -> float | None:
        d = self.radius / 111.0 * 1.3
        params = {"format": "jsonv2", "limit": "5", "bounded": "1",
                  "viewbox": f"{self.lon - d},{self.lat + d},{self.lon + d},{self.lat - d}"}
        if is_zip:
            params.update({"postalcode": query, "countrycodes": "us"})
        else:
            params["q"] = f"{query}, {self.feed['place']}"
        async with self._session.get(NOMINATIM_URL, params=params, headers=HEADERS,
                                     timeout=aiohttp.ClientTimeout(total=12)) as resp:
            resp.raise_for_status()
            hits = await resp.json(content_type=None)
        best = None
        for h in hits:
            km = geo_offset(self.lat, self.lon, float(h["lat"]), float(h["lon"]))[0] / 1000
            best = km if best is None else min(best, km)
        return best
