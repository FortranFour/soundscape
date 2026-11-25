"""End to end inside a real Home Assistant core: setup flow, ffmpeg capture of
two sound files standing in for cameras, entities, bus event and websocket feed.
Needs: pip install pytest-homeassistant-custom-component, and ffmpeg on the PATH.
"""
import asyncio
from unittest.mock import patch
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
        "cameras": [], "stream_template": "rtsp://{host}:8554/{camera}", "ignore": [], "clips": True, "min_confidence": 50,
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
    assert init["meta"]["learn"] is True and init["meta"]["classes"]["vehicle"][0] == "Vehicle"

    # live audio: nothing flows until asked for, then 16-bit PCM for that microphone
    await ws.send_json({"id": 6, "type": "soundscape/listen", "mic": "front"})
    pcm = 0
    assert {m["id"] for m in init["mics"]} == {"front", "backyard"}

    cols, states = {"front": 0, "backyard": 0}, []
    try:
        async with asyncio.timeout(bed + sec + 30):     # real time, and a CI runner can be slow
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

    # a recording is kept for each sound: here the dog, which ends when Frigate's sensor clears
    hass.states.async_set("binary_sensor.front_bark_sound", "off")
    clip_of = None
    async with asyncio.timeout(20):
        while clip_of is None:
            msg = await ws.receive_json()
            ev = msg.get("event") or {}
            if ev.get("type") == "state":
                clip_of = next((e["id"] for e in ev["recent"] if e["cls"] == "dog" and e["clip"]), None)
    dog = hass.states.get("binary_sensor.soundscape_dog")     # off again, and it remembers why it was on
    assert dog.state == "off" and dog.attributes["last_mic"].lower() == "front"
    assert any("Frigate" in t for t in dog.attributes["last_evidence"]) and dog.attributes["last_heard"]
    await ws.send_json({"id": 8, "type": "soundscape/clip", "event": clip_of})
    async with asyncio.timeout(5):
        while True:
            msg = await ws.receive_json()
            if msg["id"] == 8:
                break
    assert msg["success"], msg
    clip = msg["result"]
    seconds = len(base64.b64decode(clip["data"])) / 2 / clip["rate"]
    assert clip["mic"] == "front" and 5 < seconds <= 30.5, seconds
    await ws.send_json({"id": 10, "type": "soundscape/clip", "event": 1})
    async with asyncio.timeout(5):
        while True:
            msg = await ws.receive_json()
            if msg["id"] == 10:
                break
    assert not msg["success"] and msg["error"]["code"] == "not_found"

    # words on request: nothing to do it with at first, then an engine, and the answer is remembered
    async def ask(n):
        await ws.send_json({"id": n, "type": "soundscape/transcribe", "event": clip_of})
        async with asyncio.timeout(10):
            while True:
                m = await ws.receive_json()
                if m["id"] == n:
                    return m
    msg = await ask(20)
    assert not msg["success"] and msg["error"]["code"] == "no_engine"

    from homeassistant.components import stt
    heard = {}

    class Engine:
        name = "Test engine"
        supported_languages = ["en-US", "de-DE"]

        async def async_process_audio_stream(self, meta, stream):
            heard["meta"] = meta
            heard["bytes"] = sum([len(c) async for c in stream])
            heard["calls"] = heard.get("calls", 0) + 1
            return stt.SpeechResult("  who let the dog out ", stt.SpeechResultState.SUCCESS)

    hass.config.components.add("stt")
    with patch.object(stt, "async_default_engine", return_value="stt.test"), \
            patch.object(stt, "async_get_speech_to_text_engine", return_value=Engine()):
        msg = await ask(21)
        assert msg["success"] and msg["result"] == {"text": "who let the dog out", "engine": "Test engine"}, msg
        assert heard["meta"].language == "en-US" and heard["meta"].sample_rate == 16000
        assert abs(heard["bytes"] / 2 / 16000 - seconds) < 0.1          # the whole recording, at 16 kHz
        assert (await ask(22))["result"]["text"] == "who let the dog out" and heard["calls"] == 1
    hass.config.components.remove("stt")
    kept = next(e for e in hass.data["soundscape"].fusion.history if e.id == clip_of)
    assert kept.extra["transcript"] == "who let the dog out"

    # an answer: kept, counted for that kind of sound at that microphone, and the recording saved with it
    hub = hass.data["soundscape"]
    kept = hub.find_event(clip_of)
    await ws.send_json({"id": 23, "type": "soundscape/feedback", "event": clip_of, "verdict": "wrong", "actual": "bang"})
    async with asyncio.timeout(10):
        while (msg := await ws.receive_json())["id"] != 23 or msg["type"] != "result":
            pass
    assert msg["success"], msg
    assert msg["result"]["factor"] == 0.85 and kept.extra["feedback"] == {"verdict": "wrong", "actual": "bang"}
    mic = None if kept.cls in ("jet", "propeller", "helicopter", "tiltrotor", "aircraft") else kept.mic
    assert hub.calibration.factor(kept.cls, mic) == 0.85 and hub.calibration.factor("bang", mic) == 1.05
    labels = (hub.labeled_dir / "labels.jsonl").read_text().splitlines()
    import json as _json
    rec = _json.loads(labels[-1])
    assert rec["verdict"] == "wrong" and rec["actual"] == "bang" and rec["reported"] == kept.cls
    assert (hub.labeled_dir / rec["file"]).stat().st_size > 48000
    await ws.send_json({"id": 24, "type": "soundscape/feedback_reset"})
    async with asyncio.timeout(10):
        while (msg := await ws.receive_json())["id"] != 24 or msg["type"] != "result":
            pass
    assert msg["result"]["calibration"] == [] and "feedback" not in kept.extra
    hub.learn = False                                   # switched off: answers are refused, nothing applies
    await ws.send_json({"id": 25, "type": "soundscape/feedback", "event": clip_of, "verdict": "wrong"})
    async with asyncio.timeout(10):
        while (msg := await ws.receive_json())["id"] != 25 or msg["type"] != "result":
            pass
    assert not msg["success"] and msg["error"]["code"] == "off"
    hub.learn = True
    await hass.async_block_till_done()

    # the house can be moved from the card's map; it is kept and told to every open card
    hub = hass.data["soundscape"]
    await ws.send_json({"id": 31, "type": "soundscape/set_home", "lat": 32.7301, "lon": -117.1502})
    seen = {}
    async with asyncio.timeout(5):
        while len(seen) < 2:
            msg = await ws.receive_json()
            if msg["id"] == 31:
                seen["result"] = msg["success"]
            elif msg.get("event", {}).get("type") == "meta":
                seen["meta"] = msg["event"]["meta"]
    assert seen["result"] and seen["meta"]["lat"] == 32.7301
    assert (hub.lat, hub.fusion.lon) == (32.7301, -117.1502)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
