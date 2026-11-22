"""Build dev/fixture.json: 90 s of synthetic audio on five microphones run through
the real analyzers and fusion, for looking at the card without a house attached."""
import base64
import json
import pathlib
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import synth  # noqa: E402
import test_fusion  # noqa: E402,F401

dsp, fusion = sys.modules["dsp"], sys.modules["fusion"]
MICS = [("Front", 200, 9), ("Front_door", 160, 5), ("Driveway", 95, 12), ("Bedroom_windows", 290, 7), ("Backyard", 10, 11)]
SEC, SR = 96, synth.SR
T0 = time.time() - SEC
HOME = (32.73, -117.15)


def place(x, start, sound):
    x[start * SR:start * SR + len(sound)] += sound[: len(x) - start * SR]


audio = {}
for n, (name, _, _) in enumerate(MICS):
    x = synth.pink(SEC, -58, 40 + n) + synth.hum(SEC, -70)
    place(x, 0, synth.birds(SEC, -44 if name == "Backyard" else -56, seed=n))
    place(x, 44, synth.rotor(50, bpf=19.9, db=-36, seed=50 + n) * np.hanning(50 * SR) ** 0.4)
    gain = {"Front": 0, "Front_door": -5, "Driveway": -9, "Bedroom_windows": -17, "Backyard": -24}[name]
    place(x, 70, synth.wail(26, db=-27 + gain) * np.hanning(26 * SR) ** 0.25)
    place(x, 20, synth.passby(8, db=-30 + (0 if name == "Driveway" else -12), seed=n))
    audio[name] = synth.pcm(x)

fu = fusion.Fusion([fusion.Mic(n, n.replace("_", " ").capitalize(), b, d) for n, b, d in MICS], *HOME)
an = {n: dsp.Analyzer(SR) for n, _, _ in MICS}
cols = {n: bytearray() for n, _, _ in MICS}
types = {"V22": ["BELL-BOEING V-22 Osprey", "R2T", "M"], "B738": ["BOEING 737-800", "L2J", "M"],
         "C172": ["CESSNA 172 Skyhawk", "L1P", "L"], "EC35": ["AIRBUS HELICOPTERS EC-135", "H2T", "L"],
         "A321": ["AIRBUS A-321", "L2J", "M"], "SR22": ["CIRRUS SR-22", "L1P", "L"]}


def ac(hexid, t, north, east, alt, track, gs, **kw):
    return {"hex": hexid, "t": t, "lat": HOME[0] + north / 111.2, "lon": HOME[1] + east / 93.4,
            "alt_baro": alt, "track": track, "gs": gs, **kw}


for s in range(SEC):
    now = T0 + s
    for name, _, _ in MICS:
        chunk = audio[name][s * SR * 2:(s + 1) * SR * 2]
        for j in range(0, len(chunk), 16384):
            c, _, f = an[name].process(chunk[j:j + 16384])
            cols[name] += c
            if f:
                fu.on_features(name, f, now)
    k = s - 44
    fu.set_aircraft(fusion.prepare_aircraft([
        ac("ae1f2c", "V22", 2.6 - 0.06 * k, -1.4 + 0.035 * k, 1400, 150, 130, flight="VM161", dbFlags=1),
        ac("a8c1d2", "B738", 6.5, -4.0 + 0.1 * s, 9500, 95, 280, flight="SWA1482"),
        ac("a4b7e1", "C172", -3.8, 2.2, 2500, 320, 95, r="N734LM"),
        ac("a0d9f3", "EC35", -7.5, -2.0, 900, 20, 110, r="N911SD"),
        ac("ab12cd", "A321", 1.0, 8.5, 14000, 270, 320, flight="AAL612"),
        ac("a66e01", "SR22", 4.9, 6.1, 4500, 200, 140, r="N52WF"),
    ], *HOME, types), now)
    if s == 22:
        fu.on_frigate_object("Driveway", "car", 1, now)
    if s == 30:
        fu.on_frigate_object("Driveway", "car", 0, now)
    if s in (12, 13, 14, 86, 88, 90, 92, 94):
        for m in ("Backyard", "Bedroom_windows") if s < 80 else ("Backyard",):
            fu.on_birdnet(m, "Common Raven", "Corvus corax", 0.83, now)
    if s in (36, 38):
        fu.on_birdnet("Backyard", "Lesser Goldfinch", "Spinus psaltria", 0.71, now)
    if s == 16:
        fu.on_frigate_audio("Front_door", "bark", True, now)
    if s == 18:
        fu.on_frigate_audio("Front_door", "bark", False, now)
    fu.tick(now)

now = T0 + SEC - 1
for e in [*fu.active.values(), *fu.history]:
    if e.cls == "siren":
        e.extra["dispatch"] = [{"type": "Medical", "address": "EXAMPLE DR", "cross": "SAMPLE WAY", "units": "E9, M9",
                                "time": time.strftime("%Y-%m-%dT%H:%M:00-08:00", time.localtime(e.start)), "km": 1.4}]
        e.evidence.append("Dispatch: Medical, EXAMPLE DR (E9, M9), about 1.4 km")
ref = an["Front"]
snap = fu.snapshot(now)
for m in snap["mics"]:
    m["error"] = None
init = {"type": "init", "meta": {"bands": dsp.N_BANDS, "edges": [round(float(x), 1) for x in ref.band_edges],
                                  "cols_per_s": ref.cols_per_s, "db_min": dsp.DB_MIN, "db_max": dsp.DB_MAX,
                                  "backlog_s": 90, "version": "dev"},
        "backlog": {n: base64.b64encode(bytes(c[-int(90 * ref.cols_per_s) * dsp.N_BANDS:])).decode() for n, c in cols.items()},
        "status": {}, **snap}
(ROOT / "dev/fixture.json").write_text(json.dumps(init))
print("active:", [(e["label"], e["mic"], e["compass"], e["conf"]) for e in snap["active"]])
print("recent:", [(e["label"], e["mic"], round(e["end"] - e["start"])) for e in snap["recent"]])
