"""Fusion tests: synthetic audio on four microphones plus mocked outside evidence."""
import importlib.util
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import synth  # noqa: E402
import test_dsp  # noqa: E402,F401  (loads dsp)

dsp = sys.modules["dsp"]
_spec = importlib.util.spec_from_file_location(
    "fusion", pathlib.Path(__file__).parents[1] / "custom_components/soundscape/fusion.py")
fusion = importlib.util.module_from_spec(_spec)
sys.modules["fusion"] = fusion
_spec.loader.exec_module(fusion)

MICS = [("front", 180), ("driveway", 90), ("backyard", 0), ("bedroom_windows", 270)]
BED = 14
HOME = (32.73, -117.15)


def scenario(sound, gains, sec=16, hooks=None, night=False, adsb=True, aircraft=None, video=False):
    """Play `sound` at each microphone with a gain in dB. Returns all events seen."""
    fu = fusion.Fusion([fusion.Mic(i, i.replace("_", " ").title(), b, 10) for i, b in MICS],
                       *HOME, night=lambda: night, adsb=adsb, video=video)
    an = {i: dsp.Analyzer(synth.SR) for i, _ in MICS}
    data = {}
    for n, (i, _) in enumerate(MICS):
        g = gains.get(i)
        x = synth.pink(BED + sec, -55, 20 + n)
        if g is not None:
            x[BED * synth.SR:] += sound(sec) * 10 ** (g / 20)
        data[i] = synth.pcm(x)
    seen = {}
    for s in range(BED + sec):
        for i, _ in MICS:
            chunk = data[i][s * synth.SR * 2:(s + 1) * synth.SR * 2]
            for j in range(0, len(chunk), 16384):
                f = an[i].process(chunk[j:j + 16384])[2]
                if f:
                    fu.on_features(i, f, float(s))
        if aircraft is not None:
            fu.set_aircraft(aircraft, float(s))
        if hooks and s - BED in hooks:
            hooks[s - BED](fu, float(s))
        started, _ = fu.tick(float(s))
        for e in started:
            seen[e.id] = e
    return list(seen.values()), fu


def ac(t, cat, km_north, alt_ft, **kw):
    return {"hex": "ae1234", "t": t, "category": cat, "lat": HOME[0] + km_north / 111.2,
            "lon": HOME[1], "alt_baro": alt_ft, "gs": 120, "track": 180, **kw}


TYPES = {"V22": ["BELL-BOEING V-22 Osprey", "R2T", "M"], "H60": ["SIKORSKY UH-60", "H2T", "M"],
         "B738": ["BOEING 737-800", "L2J", "M"], "C172": ["CESSNA 172", "L1P", "L"]}


def test_siren_located_at_loudest_side():
    ev, _ = scenario(synth.wail, {"front": 0, "driveway": -8, "backyard": -20, "bedroom_windows": -14})
    assert [e.cls for e in ev] == ["siren"]
    e = ev[0]
    assert e.mic == "front" and 120 < e.bearing < 200, e.bearing
    assert e.conf > 0.7


def test_howl_alone_is_not_an_event_but_with_frigate_it_is():
    gains = {"backyard": 0, "bedroom_windows": -10}
    ev, _ = scenario(synth.howl, gains, night=True)
    assert not [e for e in ev if e.cls == "siren" and e.conf > 0.8]
    hooks = {3: lambda fu, now: fu.on_frigate_audio("backyard", "howl", True, now)}
    ev, _ = scenario(synth.howl, gains, night=True, hooks=hooks)
    coy = [e for e in ev if e.cls == "coyote"]
    assert coy and coy[0].mic == "backyard"


def test_osprey_from_adsb():
    planes = fusion.prepare_aircraft([ac("V22", "A7", 1.2, 1500, flight="VM161 ", dbFlags=1)], *HOME, TYPES)
    assert planes[0]["cls"] == "tiltrotor" and planes[0]["audible"] > 0.6
    ev, _ = scenario(lambda s: synth.rotor(s, bpf=19.9), dict.fromkeys(dict(MICS), 0), aircraft=planes)
    assert len(ev) == 1 and ev[0].label == "Osprey" and ev[0].method == "adsb"
    assert ev[0].extra["blade_pass_hz"] == 19.9 or abs(ev[0].extra["blade_pass_hz"] - 19.9) < 0.4


def test_rotor_without_transponder():
    ev, _ = scenario(lambda s: synth.rotor(s, bpf=19.9), dict.fromkeys(dict(MICS), 0), aircraft=[])
    assert len(ev) == 1 and ev[0].label == "Helicopter or Osprey" and ev[0].far
    ev, _ = scenario(lambda s: synth.rotor(s, bpf=26.3), dict.fromkeys(dict(MICS), 0), aircraft=[])
    assert len(ev) == 1 and ev[0].label == "Helicopter"


def test_propeller_and_jet_with_adsb():
    planes = fusion.prepare_aircraft([ac("C172", "A1", 0.8, 2000, r="N123AB")], *HOME, TYPES)
    ev, _ = scenario(synth.propeller, dict.fromkeys(dict(MICS), 0), aircraft=planes)
    assert [e.cls for e in ev] == ["propeller"] and "CESSNA" in ev[0].detail
    planes = fusion.prepare_aircraft([ac("B738", "A3", 1.5, 4000, flight="SWA12")], *HOME, TYPES)
    ev, _ = scenario(lambda s: synth.pink(s, -42, 77), dict.fromkeys(dict(MICS), 0), aircraft=planes)
    assert [e.cls for e in ev] == ["jet"]


def test_roar_without_aircraft_is_not_a_jet():
    ev, _ = scenario(lambda s: synth.pink(s, -42, 77), dict.fromkeys(dict(MICS), 0), aircraft=[])
    assert not ev


def test_distant_aircraft_do_not_explain_a_sound():
    planes = fusion.prepare_aircraft([ac("B738", "A3", 25, 30000)], *HOME, TYPES)
    assert planes[0]["audible"] < 0.25


def test_birdnet_and_frigate_reports():
    hooks = {
        2: lambda fu, now: fu.on_birdnet("backyard", "Common Raven", "Corvus corax", 0.82, now),
        3: lambda fu, now: fu.on_frigate_audio("driveway", "shatter", True, now),
        4: lambda fu, now: fu.on_frigate_audio("front", "car_alarm", True, now),
        5: lambda fu, now: fu.on_birdnet("front", "Coyote", "Canis latrans", 0.7, now),
        6: lambda fu, now: fu.on_frigate_audio("front", "bark", True, now),
    }
    ev, fu = scenario(synth.birds, {"backyard": 0}, hooks=hooks)
    by = {e.cls: e for e in ev}
    assert set(by) == {"bird", "glass", "car_alarm", "coyote", "dog"}
    assert by["bird"].label == "Common Raven" and by["bird"].mic == "backyard"
    assert by["glass"].mic == "driveway"
    fu.tick(500.0)
    assert len(fu.snapshot(500.0)["recent"]) == 5


def test_a_passing_car_is_identified_by_sound_alone():
    ev, _ = scenario(synth.passby, {"driveway": 0, "front": -6}, sec=12)
    assert [e.cls for e in ev] == ["vehicle"] and ev[0].mic == "driveway"
    assert all(t.startswith("Sound") for t in ev[0].evidence)


def test_a_quiet_car_is_still_heard():
    quiet = lambda s: synth.passby(s, db=-44)  # noqa: E731
    ev, _ = scenario(quiet, {"driveway": 0}, sec=12)
    assert [e.cls for e in ev] == ["vehicle"]


def test_talking_and_machinery_are_not_vehicles():
    for sound in (synth.speech, lambda s: synth.burst(s, 2, 9), lambda s: synth.burst(s, 2, 99)):
        ev, _ = scenario(sound, {"driveway": 0, "front": -6}, sec=14)
        assert not [e for e in ev if e.cls == "vehicle"]


def test_the_same_swell_on_every_microphone_is_not_in_the_street():
    ev, _ = scenario(synth.passby, {i: 0 for i, _ in MICS}, sec=12)
    assert not [e for e in ev if e.cls == "vehicle"]


def test_camera_sightings_count_only_when_switched_on():
    rise = lambda s: synth.burst(s, 2, 99, db=-42)  # noqa: E731   a noise that starts and stays
    hooks = {3: lambda fu, now: fu.on_frigate_object("driveway", "car", 1, now)}
    ev, _ = scenario(rise, {"driveway": 0, "front": -6}, sec=9, hooks=hooks)
    assert not ev
    ev, _ = scenario(rise, {"driveway": 0, "front": -6}, sec=9, hooks=hooks, video=True)
    assert [e.cls for e in ev] == ["vehicle"]


def test_a_howl_alone_is_never_reported_even_at_night():
    ev, _ = scenario(lambda s: synth.howl(s, db=-15), {"backyard": 0, "bedroom_windows": -10}, night=True, sec=30)
    assert not [e for e in ev if e.cls == "coyote"]


def test_a_faint_wavering_tone_is_ignored_even_with_support():
    """A whine barely above the background, as from a fan: not a howl whatever else is going on."""
    hooks = {3: lambda fu, now: fu.on_frigate_object("backyard", "dog", 1, now)}
    ev, _ = scenario(lambda s: synth.howl(s, db=-58), {"backyard": 0}, night=True, sec=30, hooks=hooks)
    assert not [e for e in ev if e.cls == "coyote"]


def test_minimum_confidence_screens_out_the_doubtful():
    hooks = {3: lambda fu, now: fu.on_frigate_audio("backyard", "howl", True, now)}   # Frigate alone: 60 %
    quiet = lambda s: synth.noise(s, -70)  # noqa: E731
    ev, _ = scenario(quiet, {"backyard": 0}, hooks=hooks)
    assert [e.cls for e in ev] == ["coyote"] and ev[0].conf < 0.7

    def strict(sound, gains, **kw):
        real = fusion.Fusion
        fusion.Fusion = lambda *a, **k: real(*a, **{**k, "min_conf": 0.7})
        try:
            return scenario(sound, gains, **kw)
        finally:
            fusion.Fusion = real
    ev, _ = strict(quiet, {"backyard": 0}, hooks=hooks)
    assert not ev
    ev, _ = strict(synth.wail, {"front": 0})          # a clear siren is well above 70 %
    assert [e.cls for e in ev] == ["siren"]
