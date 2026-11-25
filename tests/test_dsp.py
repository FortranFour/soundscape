"""Signature tests on synthetic audio. Run: python -m pytest tests/test_dsp.py"""
import importlib.util
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import synth  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "dsp", pathlib.Path(__file__).parents[1] / "custom_components/soundscape/dsp.py"
)
dsp = importlib.util.module_from_spec(_spec)
sys.modules["dsp"] = dsp
_spec.loader.exec_module(dsp)

BED = 14  # seconds of background before the sound, so the floors settle


def run(sound, sec=14, bed_db=-55):
    """Background, then the sound over background. Returns per-second features."""
    a = dsp.Analyzer(synth.SR)
    x = np.concatenate((synth.pink(BED, bed_db, 11), synth.pink(sec, bed_db, 12) + sound(sec)))
    data = synth.pcm(x)
    out, cols = [], 0
    chunk = 8192 * 2
    for i in range(0, len(data), chunk):
        c, n, f = a.process(data[i:i + chunk])
        assert len(c) == n * dsp.N_BANDS
        cols += n
        if f:
            out.append(f)
    assert abs(cols - (BED + sec) * a.cols_per_s) < 3
    return out[BED + 2:]


def peak(feats, key):
    return max(getattr(f, key) for f in feats)


def test_wail():
    f = run(synth.wail)
    assert peak(f, "siren") > 0.6
    assert peak(f, "rotor") < 0.3 and peak(f, "prop") < 0.3


def test_yelp():
    assert peak(run(synth.yelp), "siren") > 0.6


def test_hilo():
    assert peak(run(synth.hilo), "siren") > 0.5


def test_howl_is_not_siren():
    f = run(synth.howl)
    assert peak(f, "howl") > 0.25
    assert np.median([x.siren for x in f]) < 0.5


def test_propeller():
    f = run(synth.propeller)
    assert peak(f, "prop") > 0.6
    best = max(f, key=lambda x: x.prop)
    assert abs(best.prop_hz - 84) < 1.5 or abs(best.prop_hz * 2 - 84) < 1.5
    assert peak(f, "siren") < 0.3


def test_rotor():
    f = run(synth.rotor)
    assert peak(f, "rotor") > 0.6
    best = max(f, key=lambda x: x.rotor)
    assert abs(best.rotor_hz - 17.2) < 0.5


def test_osprey_rate_resolved():
    f = run(lambda s: synth.rotor(s, bpf=19.9))
    best = max(f, key=lambda x: x.rotor)
    assert best.rotor > 0.6 and abs(best.rotor_hz - 19.9) < 0.5


def test_quiet_things_stay_quiet():
    for sound in (lambda s: synth.noise(s, -60), synth.birds, synth.passby,
                  lambda s: synth.pink(s, -40, 99)):
        f = run(sound)
        for key in ("siren", "rotor", "prop"):
            assert peak(f, key) < 0.35, (sound, key, peak(f, key))


def test_constant_hum_fades():
    a = dsp.Analyzer(synth.SR)
    x = synth.pink(60, -55, 3) + synth.hum(60)
    data = synth.pcm(x)
    feats = []
    for i in range(0, len(data), 16384):
        f = a.process(data[i:i + 16384])[2]
        if f:
            feats.append(f)
    assert max(f.prop for f in feats[15:]) < 0.3


def test_passby_raises_mid_band():
    f = run(synth.passby, sec=9)
    assert max(x.excess["mid"] for x in f) > 8


def test_passby_is_a_smooth_swell_of_toneless_noise():
    assert peak(run(synth.passby), "passby") > 0.8
    assert peak(run(lambda s: synth.passby(s, db=-44)), "passby") > 0.6
    short = lambda s: np.concatenate((synth.passby(5), np.zeros(synth.SR * (s - 5))))  # noqa: E731
    assert peak(run(short), "passby") > 0.8


def test_passby_rejects_bursts_pitch_and_noise_that_stays():
    swell = lambda s: np.exp(-(((synth._t(s) - s / 2) / (s / 6)) ** 2))  # noqa: E731
    for sound in (synth.speech, synth.howl, synth.birds, synth.hum,
                  lambda s: synth.wail(s) * swell(s),          # a siren going past
                  lambda s: synth.burst(s, 2, 9),              # switched on, then off
                  lambda s: synth.burst(s, 2, 99)):            # switched on and left on
        assert peak(run(sound, sec=20), "passby") < 0.25


def test_passby_ignores_swells_where_the_background_is_restless():
    """Gusts in the leaves all the time: one more swell means nothing."""
    def gusty(sec):
        t = synth._t(sec)
        env = sum(np.exp(-(((t - c) / 1.5) ** 2)) for c in range(4, int(sec), 7))
        x = np.diff(synth.pink(sec + 0.01, 0, 9))[: len(t)]
        return x / x.std() * env * 10 ** (-36 / 20)
    feats = run(gusty, sec=110)
    assert peak(feats[35:], "passby") < 0.25
