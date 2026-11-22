"""Dispatch feeds: each parser against a sample shaped like the live feed, then matching.
Samples follow the fields each feed returned on 22 November 2026."""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("homeassistant")
from custom_components.soundscape import dispatch as d  # noqa: E402

NOW = datetime(2026, 11, 22, 20, 0, tzinfo=UTC)

SAMPLES = {
    "sdfd": [{"ResponseDate": "2026-11-22T12:00:00-08:00", "CallType": "Medical", "Address": "UNIVERSITY AVE ",
              "CrossStreet": "FAIRMOUNT AVE/44TH ST", "UnitName": "M31, E17", "ResponseDateString": "x"}],
    "seattle": [{"address": "Nb I5 At Mercer", "type": "MVI Freeway", "datetime": "2026-11-22T12:00:00.000",
                 "latitude": "47.620184", "longitude": "-122.328213", "incident_number": "F260168047"}],
    "sf": [{"received_datetime": "2026-11-22T12:00:00.000", "call_type_final_desc": "ASSAULT / BATTERY",
            "agency": "Police", "intersection_name": "MISSION ST \\ 16TH ST"},
           {"received_datetime": "2026-11-22T12:00:00.000", "call_type_final_desc": "X", "intersection_name": "Not Available"}],
    "ventura": [{"address": "DEVONSHIRE DR / N M ST", "block": "", "city": "Oxnard", "incidentType": "Medical",
                 "latitude": "34.211000", "longitude": "-119.192000", "responseDate": "11/22/26 12:00",
                 "status": "En Route", "units": "MED662, E84"}],
    "phoenix": {"features": [{"attributes": {"Incident": "F26535084", "NatureDesc": "CHECK FIRE OUT",
                                              "Units": "FI29: Responding;&#160;FI43: On Scene", "Date": 1795377600000,
                                              "GenLocInfo": "12800 N CAVE CREEK RD ,PHX"},
                              "geometry": {"x": -112.0369, "y": 33.6028}}]},
    "austin": [{"published_date": "2026-11-22T20:00:00.000Z", "issue_reported": "Traffic Injury Pri 2",
                "latitude": "30.272533", "longitude": "-97.727761", "address": "E 12th St / Navasota St", "agency": "FIRE"}],
    "dallas": [{"incident_number": "26-2088551", "nature_of_call": "**PD Requested by Fire",
                "date": "2026-11-22T00:00:00.000", "time": "14:00:00", "unit_number": "D424", "block": "3100",
                "location": "Rutz St", "status": "At Scene"}],
    "houston": """<html><table><tr><td>logo</td></tr></table>
        <table id="g"><tr><th>Agency</th><th>Address</th><th>Cross Street</th><th>Key Map</th>
        <th>Call Time(Opened)</th><th>Incident Type</th><th>Combined Response</th></tr>
        <tr><td>FD</td><td>PERSHING ST</td><td>BLK SOUTHBANK ST</td><td>534S</td><td>11/22/2026 14:00</td>
        <td>EMS&nbsp;EVENT</td><td>N</td></tr></table></html>""",
    "tulsa": {"Incidents": {"Incident": [
        {"IncidentNumber": "TFD1", "Problem": "Residential Alarm", "Address": "5900 E 127th St S",
         "ResponseDate": "11/22/2026 2:00:00 PM", "Latitude": "35.979610", "Longitude": "-95.911601",
         "Vehicles": {"Vehicle": {"Division": "District 5", "Station": "9", "VehicleID": "ENG9"}}},
        {"IncidentNumber": "TFD2", "Problem": "Fire", "Address": "1 Main", "ResponseDate": "11/22/2026 2:00:00 PM",
         "Latitude": "36.1", "Longitude": "-95.9", "Vehicles": {"Vehicle": [{"VehicleID": "E1"}, {"VehicleID": "L2"}]}}]}},
    "nashville": {"features": [{"attributes": {"event_number": "FFD1", "Unit_ID": "REACH01", "incident_type_id": "PSYCH",
                                                "DispatchDateTime": 1795377600000, "PostalCode": "37203"}}]},
    "orlando": """<?xml version="1.0"?><CALLS xmlns:xsd="http://www.w3.org/2001/XMLSchema">
        <CALL incident="2026-00422363"><DATE>11/22/2026 15:00</DATE><DESC>General investigation</DESC>
        <LOCATION>6600 BLOCK EAGLE WATCH DR</LOCATION><DISTRICT>K4</DISTRICT></CALL></CALLS>""",
    "richmond": """<table><thead><tr><th>Time Received</th><th>Agency</th><th>Dispatch Area</th><th>Unit</th>
        <th>Call Type</th><th>Location</th><th>Status</th></tr></thead><tbody>
        <tr><td>11/22/2026 15:00</td><td>RPD</td><td>Precinct 3</td><td>411B1</td><td>MENTAL SUBJECT</td>
        <td>7100-BLK JAHNKE RD</td><td>Arrived</td></tr></tbody></table>""",
}


@pytest.mark.parametrize("key", sorted(d.FEEDS))
def test_every_feed_parses_to_the_same_instant(key):
    feed = d.FEEDS[key]
    got = [i for i in feed["parse"](SAMPLES[key], feed["tz"]) if i]
    assert got, key
    first = got[0]
    assert first["when"] == NOW, (key, first["when"])       # local times land on the right instant
    assert first["type"]
    assert (first["lat"] and first["lon"]) or d.street_of(first["address"]) or first["zip"], first


def test_details():
    f = d.FEEDS
    assert len(f["sf"]["parse"](SAMPLES["sf"], f["sf"]["tz"])) == 1       # withheld locations dropped
    tulsa = f["tulsa"]["parse"](SAMPLES["tulsa"], f["tulsa"]["tz"])
    assert tulsa[0]["units"] == "ENG9" and tulsa[1]["units"] == "E1, L2"
    assert f["phoenix"]["parse"](SAMPLES["phoenix"], "")[0]["units"] == "FI29, FI43"
    assert f["houston"]["parse"](SAMPLES["houston"], f["houston"]["tz"])[0]["type"] == "EMS EVENT"
    assert f["nashville"]["parse"](SAMPLES["nashville"], "")[0]["zip"] == "37203"


@pytest.mark.parametrize(("address", "street"), [
    ("3100 Rutz St", "Rutz St"), ("7100-BLK JAHNKE RD", "JAHNKE RD"), ("E 12th St / Navasota St", "E 12th St"),
    ("8000 BLOCK & NW MIAMI CT", "NW MIAMI CT"), ("6600 BLOCK EAGLE WATCH DR", "EAGLE WATCH DR"),
    ("UNIVERSITY AVE ", "UNIVERSITY AVE"), ("12800 N CAVE CREEK RD ,PHX", "N CAVE CREEK RD"),
    ("MISSION ST \\ 16TH ST", "MISSION ST"), ("", ""),
])
def test_street_of(address, street):
    assert d.street_of(address) == street


def test_nearest_feed():
    assert d.nearest_feed(32.73, -117.15) == "sdfd"
    assert d.nearest_feed(47.65, -122.30) == "seattle"
    assert d.nearest_feed(34.05, -118.25) == "ventura"      # Los Angeles has no open feed of its own
    assert d.nearest_feed(40.71, -74.00) is None            # New York: nothing in reach
    assert d.resolve_feed("auto", 29.7, -95.4) == "houston"
    assert d.resolve_feed("off", 29.7, -95.4) is None and d.resolve_feed("tulsa", 0, 0) == "tulsa"


async def test_matching_by_time_and_distance():
    disp = d.Dispatch(None, "seattle", 47.62, -122.33)

    async def fake():
        mk = lambda mins, lat, t: {"when": NOW + timedelta(minutes=mins), "type": t, "address": "A ST",  # noqa: E731
                                   "cross": "", "units": "E1", "lat": lat, "lon": -122.33, "zip": ""}
        return [mk(2, 47.63, "near"), mk(40, 47.63, "too late"), mk(-3, 47.9, "too far"), mk(1, 47.621, "nearest")]

    disp.incidents = fake
    hits = await disp.nearby(NOW)
    assert [h["type"] for h in hits] == ["nearest", "near"]
    assert hits[0]["exact"] and hits[0]["agency"] == "Seattle Fire" and hits[0]["km"] < 0.5


async def test_street_lookup_is_cached_and_bounded():
    disp = d.Dispatch(None, "dallas", 32.78, -96.80)
    asked = []

    async def fake():
        return [{"when": NOW, "type": "x", "address": "3100 Rutz St", "cross": "", "units": "", "lat": None,
                 "lon": None, "zip": ""}] * 2

    async def locate(query, is_zip):
        asked.append((query, is_zip))
        return 2.5

    disp.incidents, disp._locate = fake, locate
    real_sleep, d.asyncio.sleep = d.asyncio.sleep, lambda s: real_sleep(0)
    try:
        hits = await disp.nearby(NOW)
    finally:
        d.asyncio.sleep = real_sleep
    assert asked == [("Rutz St", False)] and len(hits) == 2 and not hits[0]["exact"]
