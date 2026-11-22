"""End to end inside a real Home Assistant core: setup flow, ffmpeg capture of
two sound files standing in for cameras, entities, bus event and websocket feed.
Needs: pip install pytest-homeassistant-custom-component, and ffmpeg on the PATH.
"""
import asyncio
import base64
import pathlib
import sys
import wave

import numpy as np
import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import synth  # noqa: E402
import custom_components.soundscape  # noqa: E402,F401  (before the harness adds its own)

DOMAIN = "soundscape"


@pytest.fixture(autouse=True)
def _custom(enable_custom_integrations):
    yield


def _wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(synth.SR)
        w.writeframes(synth.pcm(x))


async def test_flow_capture_and_feed(hass, hass_ws_client, tmp_path, socket_enabled):
    bed, sec = 13, 14
    for n, (name, gain) in enumerate((("front", 0), ("backyard", -18))):
        x = synth.pink(bed + sec, -55, n)
        x[bed * synth.SR:] += synth.wail(sec) * 10 ** (gain / 20)
        _wav(tmp_path / f"{name}.wav", x)

    # Frigate's audio sensors as they exist in a real install; "front_door" must not be read as "front".
    hass.states.async_set("binary_sensor.front_bark_sound", "on")
    hass.states.async_set("binary_sensor.front_door_shatter_sound", "on")
    hass.states.async_set("sensor.backyard_dog_count", "1")

    # A US household: setup asks in miles and feet and stores kilometres and metres.
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
    hass.config.units = US_CUSTOMARY_SYSTEM

    # --- setup flow, with no Frigate, BirdNET-Go or ADS-B
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"adsb_provider": "off", "adsb_radius_km": 9, "dispatch": "off", "units": "auto"})  # 9 miles
    assert result["step_id"] == "cameras", result
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "cameras": [], "stream_template": "rtsp://{host}:8554/{camera}", "ignore": [],
        "stream_overrides": f"front={tmp_path}/front.wav\nbackyard={tmp_path}/backyard.wav"})
    assert result["step_id"] == "geometry", result
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "front bearing": 180, "front distance": 26, "backyard bearing": 0, "backyard distance": 40})  # feet
    assert result["type"] == "create_entry"
    entry = result["result"]
    await hass.async_block_till_done()
    assert entry.options["geometry"] == {"front": [180, 7.92], "backyard": [0, 12.19]}  # stored in metres
    assert entry.options["adsb_radius_km"] == 14.5
    assert hass.states.get("binary_sensor.soundscape_siren").state == "off"
    assert hass.states.get("sensor.soundscape_now_hearing").state == "Quiet"

    fired = []
    hass.bus.async_listen("soundscape_event", lambda e: fired.append(e.data))
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 5, "type": "soundscape/subscribe"})
    assert (await ws.receive_json())["success"]
    init = (await ws.receive_json())["event"]
    assert init["type"] == "init" and init["meta"]["bands"] == 96
    assert init["meta"]["units"] == "mi" and init["meta"]["rate"] == 24000

    # live audio: nothing flows until asked for, then 16-bit PCM for that microphone
    await ws.send_json({"id": 6, "type": "soundscape/listen", "mic": "front"})
    pcm = 0
    assert {m["id"] for m in init["mics"]} == {"front", "backyard"}

    cols, states = {"front": 0, "backyard": 0}, []
    try:
        async with asyncio.timeout(bed + sec + 8):
            while "siren" not in [f["cls"] for f in fired]:
                msg = await ws.receive_json()
                if msg["type"] == "result":
                    continue
                ev = msg["event"]
                if ev["type"] == "pcm":
                    assert msg["id"] == 6 and ev["mic"] == "front"
                    pcm += len(base64.b64decode(ev["data"]))
                    if pcm > 24000 * 2 * 3:
                        await ws.send_json({"id": 7, "type": "unsubscribe_events", "subscription": 6})
                elif ev["type"] == "spec":
                    assert len(base64.b64decode(ev["data"])) == ev["n"] * 96
                    cols[ev["mic"]] += ev["n"]
                else:
                    states.append(ev)
    except TimeoutError:
        pass
    starts = {f["cls"]: f for f in fired if f["phase"] == "start"}
    assert set(starts) == {"dog", "siren"}, [s["active"] for s in states[-3:]]
    assert starts["dog"]["mic"] == "front"
    assert starts["siren"]["mic"] == "front" and 150 <= starts["siren"]["bearing"] <= 210
    assert min(cols.values()) > 11 * (bed + 3)
    assert 24000 * 2 * 3 < pcm < 24000 * 2 * 6      # about three seconds arrived, then it stopped
    assert hass.data["soundscape"].captures["front"].on_pcm is None
    assert hass.states.get("binary_sensor.soundscape_siren").state == "on"
    assert hass.states.get("sensor.soundscape_now_hearing").state == "Siren"
    assert all(m["ok"] for m in states[-1]["mics"])

    # the house can be moved from the card's map; it is kept and told to every open card
    hub = hass.data["soundscape"]
    await ws.send_json({"id": 9, "type": "soundscape/set_home", "lat": 32.7301, "lon": -117.1502})
    seen = {}
    async with asyncio.timeout(5):
        while len(seen) < 2:
            msg = await ws.receive_json()
            if msg["id"] == 9:
                seen["result"] = msg["success"]
            elif msg.get("event", {}).get("type") == "meta":
                seen["meta"] = msg["event"]["meta"]
    assert seen["result"] and seen["meta"]["lat"] == 32.7301
    assert (hub.lat, hub.fusion.lon) == (32.7301, -117.1502)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
