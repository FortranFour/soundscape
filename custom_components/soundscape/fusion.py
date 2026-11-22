"""Evidence fusion and localization for Soundscape. No Home Assistant imports.

Evidence comes from five places:

  the analyzers (dsp.py)   siren, howl, rotor, propeller, broadband level per mic
  Frigate audio labels     YAMNet classes Frigate is listening for, per camera
  Frigate objects          a car, truck or motorcycle moving on a camera; a dog
  BirdNET-Go               species per microphone, plus its non-bird classes
  ADS-B                    aircraft nearby, with type, position and altitude

Each tick the evidence for a class is combined (noisy-OR), held against
start/stop thresholds, and turned into events with a location estimate.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

CLASSES: dict[str, tuple[str, str]] = {
    "bird": ("Bird", "mdi:bird"),
    "coyote": ("Coyote", "mdi:dog-side"),
    "dog": ("Dog", "mdi:dog"),
    "cat": ("Cat", "mdi:cat"),
    "vehicle": ("Vehicle", "mdi:car-side"),
    "horn": ("Horn", "mdi:bugle"),
    "car_alarm": ("Car alarm", "mdi:car-emergency"),
    "siren": ("Siren", "mdi:alarm-light"),
    "glass": ("Breaking glass", "mdi:glass-fragile"),
    "bang": ("Bang", "mdi:flash-alert"),
    "alarm": ("Alarm", "mdi:bell-alert"),
    "voice": ("Voice", "mdi:account-voice"),
    "machinery": ("Machinery", "mdi:saw-blade"),
    "weather": ("Weather", "mdi:weather-lightning-rainy"),
    "jet": ("Jet", "mdi:airplane"),
    "propeller": ("Propeller aircraft", "mdi:airplane-takeoff"),
    "helicopter": ("Helicopter", "mdi:helicopter"),
    "tiltrotor": ("Osprey", "mdi:quadcopter"),
    "aircraft": ("Aircraft", "mdi:airplane-search"),
}
AIR = ("jet", "propeller", "helicopter", "tiltrotor", "aircraft")

# Frigate audio label (YAMNet) -> class
FRIGATE_AUDIO = {
    **dict.fromkeys(("siren", "civil_defense_siren", "emergency_vehicle", "police_car",
                     "ambulance", "fire_engine"), "siren"),
    **dict.fromkeys(("bark", "dog", "bow-wow", "yip", "growling", "whimper_dog", "dogs"), "dog"),
    "howl": "coyote",
    **dict.fromkeys(("cat", "meow", "caterwaul", "hiss", "purr"), "cat"),
    **dict.fromkeys(("vehicle", "motor_vehicle", "car", "car_passing_by", "race_car", "truck",
                     "bus", "motorcycle", "skidding", "tire_squeal", "engine", "light_engine",
                     "medium_engine", "heavy_engine", "accelerating", "idling"), "vehicle"),
    **dict.fromkeys(("honk", "air_horn", "vehicle_horn"), "horn"),
    "car_alarm": "car_alarm",
    **dict.fromkeys(("glass", "shatter", "smash", "breaking"), "glass"),
    **dict.fromkeys(("gunshot", "explosion", "fireworks", "firecracker", "burst", "bang",
                     "machine_gun", "artillery_fire", "cap_gun"), "bang"),
    **dict.fromkeys(("fire_alarm", "smoke_detector", "alarm", "buzzer"), "alarm"),
    **dict.fromkeys(("speech", "yell", "scream", "shout", "screaming", "crying", "whistling",
                     "child_speech"), "voice"),
    **dict.fromkeys(("lawn_mower", "chainsaw", "power_tool", "drill", "sawing", "jackhammer",
                     "leaf_blower"), "machinery"),
    **dict.fromkeys(("thunder", "thunderstorm", "rain", "wind"), "weather"),
    **dict.fromkeys(("bird", "crow", "owl", "chirp", "squawk", "caw", "hoot", "coo", "pigeon",
                     "gull", "duck", "goose", "fowl", "bird_vocalization"), "bird"),
    "jet_engine": "jet",
    **dict.fromkeys(("propeller", "fixed-wing_aircraft"), "propeller"),
    "helicopter": "helicopter",
    **dict.fromkeys(("aircraft", "aircraft_engine"), "aircraft"),
}
# Entity ids spell these with underscores.
FRIGATE_AUDIO.update({k.replace("-", "_"): v for k, v in list(FRIGATE_AUDIO.items()) if "-" in k})
FRIGATE_MOVING = ("car", "truck", "motorcycle", "bus")

# BirdNET's non-bird labels, matched on the common or scientific name
BIRDNET_OTHER = (
    ("canis latrans", "coyote"), ("coyote", "coyote"), ("canis lupus", "coyote"),
    ("dog", "dog"), ("siren", "siren"), ("engine", "vehicle"), ("gun", "bang"),
    ("fireworks", "bang"), ("human", "voice"), ("power tools", "machinery"),
)

# Blade-pass rates of the V-22: 3 blades at 333 rpm (cruise) and 397 rpm (hover).
# A UH-60 sits at 17.2 Hz, inside the first band, so this alone never decides.
TILTROTOR_HZ = ((16.0, 17.4), (19.3, 20.6))

START, STOP = 0.5, 0.3
# class: (seconds of evidence before an event starts, seconds of silence before it ends)
TIMING = {"siren": (4, 6), "coyote": (3, 8), "vehicle": (2, 3), "jet": (6, 8),
          "propeller": (4, 8), "helicopter": (4, 8), "tiltrotor": (4, 8), "aircraft": (4, 8),
          "bird": (1, 6)}
LOC_BAND = {"bird": "high", "glass": "high", "siren": "mid", "coyote": "mid", "dog": "mid",
            "vehicle": "mid", "jet": "low", "propeller": "low", "helicopter": "low",
            "tiltrotor": "low", "aircraft": "low"}
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
SOUND_MPS = 343.0


def compass(bearing: float) -> str:
    return COMPASS[int((bearing % 360) / 45 + 0.5) % 8]


def noisy_or(scores) -> float:
    p = 1.0
    for s in scores:
        p *= 1.0 - max(0.0, min(1.0, s))
    return 1.0 - p


def _c01(x: float) -> float:
    return max(0.0, min(1.0, x))


def geo_offset(lat0, lon0, lat, lon) -> tuple[float, float]:
    """(distance m, bearing deg) from point 0 to the other point."""
    r = 6371000.0
    p0, p1 = math.radians(lat0), math.radians(lat)
    dl = math.radians(lon - lon0)
    a = math.sin((p1 - p0) / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2
    d = 2 * r * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dl) * math.cos(p1)
    x = math.cos(p0) * math.sin(p1) - math.sin(p0) * math.cos(p1) * math.cos(dl)
    return d, (math.degrees(math.atan2(y, x)) + 360) % 360


def aircraft_class(ac: dict, types: dict) -> str:
    t = (ac.get("t") or "").upper()
    code = (types.get(t) or [None, ""])[1] or ""
    if t in ("V22", "B609", "AW609") or code[:1] in ("R", "T"):
        return "tiltrotor"
    if code[:1] in ("H", "G"):
        return "helicopter"
    if code[2:3] == "J":
        return "jet"
    if code[2:3] in ("P", "T", "E"):
        return "propeller"
    cat = ac.get("category") or ""
    if cat == "A7":
        return "helicopter"
    if cat == "A1":
        return "propeller"
    if cat in ("A2", "A3", "A4", "A5", "A6"):
        return "jet"
    return "aircraft"


# How far each kind carries, as the slant range (km) at which it is half likely heard.
REACH_KM = {"jet": 4.0, "propeller": 2.5, "helicopter": 4.0, "tiltrotor": 5.0, "aircraft": 2.5}


def prepare_aircraft(raw: list[dict], lat0: float, lon0: float, types: dict) -> list[dict]:
    """Reduce a readsb-style 'ac' list to what the card and the fusion need."""
    out = []
    for ac in raw:
        lat, lon = ac.get("lat"), ac.get("lon")
        alt = ac.get("alt_baro", ac.get("alt_geom"))
        if lat is None or lon is None or alt in (None, "ground"):
            continue
        try:
            alt_m = float(alt) * 0.3048
        except (TypeError, ValueError):
            continue
        gs = float(ac.get("gs") or 0) * 0.5144
        track = float(ac.get("track") or 0)
        ground, bearing = geo_offset(lat0, lon0, lat, lon)
        slant = math.hypot(ground, alt_m)
        # What is heard now left the aircraft slant/343 s ago: step back along the track.
        back = gs * slant / SOUND_MPS
        e = ground * math.sin(math.radians(bearing)) - back * math.sin(math.radians(track))
        n = ground * math.cos(math.radians(bearing)) - back * math.cos(math.radians(track))
        heard_ground = math.hypot(e, n)
        heard_slant = math.hypot(heard_ground, alt_m)
        cls = aircraft_class(ac, types)
        mil = bool(int(ac.get("dbFlags") or 0) & 1)
        reach = REACH_KM[cls] * (1.6 if mil and cls == "jet" else 1.0)
        audible = _c01(0.5 - math.log10(max(0.05, heard_slant / 1000) / reach) * 1.6)
        t = (ac.get("t") or "").upper()
        out.append({
            "hex": ac.get("hex"), "flight": (ac.get("flight") or "").strip(),
            "reg": ac.get("r") or "", "type": t,
            "desc": ac.get("desc") or (types.get(t) or [""])[0], "cls": cls, "mil": mil,
            "lat": lat, "lon": lon, "alt_ft": round(float(alt)), "gs_kt": round(gs / 0.5144),
            "track": round(track), "km": round(ground / 1000, 2), "bearing": round(bearing),
            "heard_bearing": round((math.degrees(math.atan2(e, n)) + 360) % 360),
            "heard_km": round(heard_slant / 1000, 2),
            "elevation": round(math.degrees(math.atan2(alt_m, max(1.0, heard_ground)))),
            "audible": round(audible, 2),
        })
    out.sort(key=lambda a: -a["audible"])
    return out


@dataclass
class Mic:
    id: str
    name: str
    bearing: float = 0.0   # degrees from north, seen from the middle of the house
    distance: float = 10.0  # metres from the middle of the house
    feats: Any = None
    feats_at: float = 0.0


@dataclass
class Evidence:
    cls: str
    mic: str | None
    score: float
    text: str
    expires: float
    label: str | None = None    # species, for birds
    extra: dict = field(default_factory=dict)


@dataclass
class Event:
    id: int
    cls: str
    key: str
    label: str
    start: float
    last: float
    conf: float = 0.0
    end: float | None = None
    detail: str = ""
    mic: str | None = None
    bearing: float | None = None
    distance_m: float | None = None
    far: bool = False
    method: str = "levels"
    levels: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "cls": self.cls, "label": self.label, "icon": CLASSES[self.cls][1],
            "detail": self.detail, "conf": round(self.conf, 2), "start": self.start,
            "end": self.end, "active": self.end is None, "mic": self.mic,
            "bearing": None if self.bearing is None else round(self.bearing),
            "compass": None if self.bearing is None else compass(self.bearing),
            "distance_m": self.distance_m, "far": self.far, "method": self.method,
            "levels": self.levels, "evidence": self.evidence, "extra": self.extra,
        }


class Fusion:
    def __init__(self, mics: list[Mic], lat: float, lon: float, *, ignore=(),
                 adsb: bool = True, night=lambda: False) -> None:
        self.mics = {m.id: m for m in mics}
        self.lat, self.lon = lat, lon
        self.ignore = set(ignore)
        self.adsb = adsb
        self.night = night
        self.aircraft: list[dict] = []
        self.aircraft_at = 0.0
        self._ext: dict[tuple, Evidence] = {}
        self._cand: dict[str, dict] = {}
        self.active: dict[str, Event] = {}
        self.history: deque[Event] = deque(maxlen=300)
        self._next_id = int(time.time()) % 100000 * 1000

    # ---------------------------------------------------------------- inputs
    def on_features(self, mic: str, feats, now: float) -> None:
        if m := self.mics.get(mic):
            m.feats, m.feats_at = feats, now

    def on_frigate_audio(self, mic: str, label: str, on: bool, now: float) -> None:
        cls = FRIGATE_AUDIO.get(label)
        if not cls:
            return
        key = ("fa", mic, label)
        if on:
            name = self.mics[mic].name if mic in self.mics else mic
            self._ext[key] = Evidence(cls, mic, 0.6, f"Frigate heard {label.replace('_', ' ')} at {name}",
                                      now + 90)
        elif key in self._ext:
            # Frigate holds its sensor on for a while already; let ours lapse quickly.
            self._ext[key].expires = min(self._ext[key].expires, now + 2)

    def on_frigate_object(self, mic: str, obj: str, moving: int, now: float) -> None:
        key = ("fo", mic, obj)
        if moving <= 0:
            if key in self._ext:
                self._ext[key].expires = min(self._ext[key].expires, now + 2)
            return
        name = self.mics[mic].name if mic in self.mics else mic
        if obj in FRIGATE_MOVING:
            self._ext[key] = Evidence("vehicle", mic, 0.35, f"Frigate sees a moving {obj} at {name}", now + 60)
        elif obj == "dog" and self.night():
            self._ext[key] = Evidence("coyote", mic, 0.3, f"Frigate sees a dog at {name} at night", now + 60)

    def on_birdnet(self, mic: str | None, common: str, sci: str, conf: float, now: float,
                   ttl: float = 12.0) -> None:
        low = f"{common} {sci}".lower()
        cls, label = "bird", common
        for needle, c in BIRDNET_OTHER:
            if needle in low:
                cls, label = c, None
                break
        where = self.mics[mic].name if mic in self.mics else "an unmapped microphone"
        pct = f" ({round(conf * 100)}%)" if conf else ""
        self._ext[("bn", mic, common)] = Evidence(
            cls, mic, max(0.55, min(0.97, conf or 0.55)),
            f"BirdNET-Go: {common}{pct} at {where}", now + ttl, label, {"scientific": sci})

    def set_aircraft(self, aircraft: list[dict], now: float) -> None:
        self.aircraft, self.aircraft_at = aircraft, now

    # ------------------------------------------------------------------ tick
    def _fresh(self, now: float) -> dict[str, Mic]:
        return {k: m for k, m in self.mics.items()
                if m.feats is not None and now - m.feats_at < 4 and m.feats.ready}

    def tick(self, now: float) -> tuple[list[Event], list[Event]]:
        for k in [k for k, e in self._ext.items() if e.expires < now]:
            del self._ext[k]
        mics = self._fresh(now)
        cands: dict[str, dict] = {}

        def add(key, cls, score, text, mic=None, label=None, extra=None):
            c = cands.setdefault(key, {"cls": cls, "scores": {}, "texts": [], "mics": set(),
                                       "label": label, "extra": {}})
            src = text.split(":")[0].split(" ")[0]
            c["scores"][src] = max(c["scores"].get(src, 0), score)
            if text not in c["texts"]:
                c["texts"].append(text)
            if mic:
                c["mics"].add(mic)
            if extra:
                c["extra"].update(extra)

        # --- what the microphones themselves show
        loud = {k: max(m.feats.excess["low"], m.feats.excess["mid"]) for k, m in mics.items()}
        both = sorted(min(m.feats.excess["low"], m.feats.excess["mid"]) for m in mics.values())
        n = len(mics)
        everywhere = n >= 2 and sum(v > 4 for v in loud.values()) >= math.ceil(n * 0.6)
        spread = (max(loud.values()) - min(loud.values())) if n >= 2 else 99.0
        overall = both[len(both) // 2] if both else 0.0

        best = {}
        for sig in ("siren", "howl", "rotor", "prop"):
            if mics:
                k = max(mics, key=lambda i: getattr(mics[i].feats, sig))
                best[sig] = (k, getattr(mics[k].feats, sig))
        if best.get("siren", (0, 0))[1] > 0.3:
            k, s = best["siren"]
            add("siren", "siren", s, f"Sound: swept tone near {round(mics[k].feats.ridge_hz)} Hz")
        if best.get("howl", (0, 0))[1] > 0.2:
            k, s = best["howl"]
            add("coyote", "coyote", s * (0.75 if self.night() else 0.55),
                f"Sound: wavering howl near {round(mics[k].feats.ridge_hz)} Hz")

        air: dict[str, tuple[float, str, dict]] = {}
        if best.get("rotor", (0, 0))[1] > 0.3:
            k, s = best["rotor"]
            hz = mics[k].feats.rotor_hz
            air["helicopter"] = (s * (1.0 if everywhere or n < 2 else 0.6),
                                 f"Sound: rotor beat at {hz:.1f} Hz", {"blade_pass_hz": round(hz, 1)})
        if best.get("prop", (0, 0))[1] > 0.3:
            k, s = best["prop"]
            hz = mics[k].feats.prop_hz
            air["propeller"] = (s * (1.0 if everywhere or n < 2 else 0.5),
                                f"Sound: propeller harmonics on {hz:.0f} Hz", {"prop_hz": round(hz, 1)})
        if everywhere and spread < 10 and not air:
            # A roar on every microphone at once with no tone in it. Wind and rain do
            # that too, so on its own this stays below the start threshold unless
            # it is very loud; an aircraft on ADS-B lifts it over.
            s = _c01((overall - 3) / 8) * 0.45
            if overall > 15:
                s = 0.6
            if s > 0.15:
                air["jet"] = (s, f"Sound: broadband roar on {sum(v > 4 for v in loud.values())} of {n} microphones", {})

        # --- aircraft on ADS-B that should be audible
        heard = [a for a in self.aircraft if a["audible"] >= 0.25] if now - self.aircraft_at < 90 else []
        for ev in [e for e in self._ext.values() if e.cls in AIR]:
            air.setdefault(ev.cls, (0.0, "", {}))
        compatible = {"helicopter": ("helicopter", "tiltrotor"), "propeller": ("propeller", "tiltrotor"),
                      "jet": ("jet",), "aircraft": AIR, "tiltrotor": ("tiltrotor",)}
        used = set()
        for cls, (s, text, extra) in sorted(air.items(), key=lambda kv: -kv[1][0]):
            match = next((a for a in heard if a["cls"] in compatible[cls] and a["hex"] not in used), None)
            if match:
                used.add(match["hex"])
                out_cls = match["cls"] if match["cls"] != "aircraft" else cls
                key = f"air:{match['hex']}"
                if text:
                    add(key, out_cls, s, text)
                who = " ".join(x for x in (match["desc"] or match["type"], match["flight"] or match["reg"]) if x)
                add(key, out_cls, 0.25 + 0.5 * match["audible"],
                    f"ADS-B: {who} {match['heard_km']} km {compass(match['heard_bearing'])}, {match['alt_ft']:,} ft",
                    extra={**extra, "aircraft": match})
                for ev in [e for e in self._ext.values() if e.cls in AIR and e.cls in (cls, "aircraft")]:
                    add(key, out_cls, ev.score, ev.text, ev.mic)
            elif text:
                hz = extra.get("blade_pass_hz")
                maybe = cls == "helicopter" and hz and any(a <= hz <= b for a, b in TILTROTOR_HZ)
                add(cls, cls, s, text, extra={**extra, "tiltrotor_possible": bool(maybe), "no_transponder": self.adsb})
                if not self.adsb and cls == "jet":
                    add(cls, cls, 0.2, "ADS-B: off, so unconfirmed")

        # --- a vehicle going by: loud at some microphones, not at all of them
        air_now = max((v[0] for v in air.values()), default=0.0)
        if mics and air_now < 0.4 and best.get("siren", (0, 0))[1] < 0.4:
            k = max(mics, key=lambda i: mics[i].feats.excess["mid"])
            mid = mics[k].feats.excess["mid"]
            local = n < 2 or spread >= 4 or not everywhere
            if mid > 6 and local and mics[k].feats.howl < 0.3:
                add("vehicle", "vehicle", _c01((mid - 6) / 10) * 0.45,
                    f"Sound: pass-by, {mid:.0f} dB over background at {mics[k].name}", k)

        # --- everything the other systems reported
        for ev in self._ext.values():
            if ev.cls in AIR:
                if not any(c["cls"] in AIR for c in cands.values()):
                    add(ev.cls, ev.cls, ev.score, ev.text, ev.mic)
                continue
            key = f"bird:{ev.label}" if ev.cls == "bird" and ev.label else ev.cls
            add(key, ev.cls, ev.score, ev.text, ev.mic, ev.label, ev.extra)

        # --- thresholds, events
        started, ended = [], []
        for key, c in cands.items():
            if c["cls"] in self.ignore:
                continue
            score = noisy_or(c["scores"].values())
            st = self._cand.setdefault(key, {"n": 0})
            st["n"] = st["n"] + 1 if score >= START else 0
            ev = self.active.get(key)
            external = any(not t.startswith("Sound") for t in c["texts"])
            need = 1 if external and c["cls"] not in AIR else TIMING.get(c["cls"], (1, 5))[0]
            if ev is None and st["n"] >= need:
                self._next_id += 1
                ev = Event(self._next_id, c["cls"], key, c["label"] or CLASSES[c["cls"]][0], now, now)
                self.active[key] = ev
                started.append(ev)
            if ev and score >= STOP:
                self._update(ev, c, score, mics, now)
        for key in [k for k in self._cand if k not in cands]:
            del self._cand[key]
        for key, ev in list(self.active.items()):
            if now - ev.last > TIMING.get(ev.cls, (1, 5))[1]:
                ev.end = ev.last
                del self.active[key]
                self.history.appendleft(ev)
                ended.append(ev)
        return started, ended

    def _update(self, ev: Event, c: dict, score: float, mics: dict[str, Mic], now: float) -> None:
        ev.last = now
        ev.conf = max(ev.conf, score)
        ev.cls = c["cls"]
        if ev.cls != "bird":
            ev.label = CLASSES[ev.cls][0]
        for t in c["texts"]:
            src = t.split(":")[0].split(" at ")[0]
            ev.evidence = [x for x in ev.evidence if not (x.startswith(src) and src in ("Sound", "ADS-B"))]
            if t not in ev.evidence:
                ev.evidence.append(t)
        ev.evidence = ev.evidence[-8:]
        ev.extra.update(c["extra"])
        ac = ev.extra.get("aircraft")
        if ev.extra.get("tiltrotor_possible") and not ac:
            ev.label = "Helicopter or Osprey"
        band = LOC_BAND.get(ev.cls)
        ex = {k: (m.feats.excess[band] if band else max(m.feats.excess["low"], m.feats.excess["mid"],
                                                        m.feats.excess["high"]))
              for k, m in mics.items()}
        ev.levels = {k: round(v, 1) for k, v in ex.items()}
        if ac:
            ev.method, ev.far = "adsb", True
            ev.bearing, ev.distance_m, ev.mic = ac["heard_bearing"], ac["heard_km"] * 1000, None
            ev.detail = (f"{ac['desc'] or ac['type'] or 'Unknown type'}"
                         f"{' ' + (ac['flight'] or ac['reg']) if ac['flight'] or ac['reg'] else ''}"
                         f" · {ac['heard_km']} km {compass(ac['heard_bearing'])} · {ac['alt_ft']:,} ft")
            if ac["type"] == "V22":
                ev.label = "Osprey"
            return
        pool = {k: v for k, v in ex.items() if not c["mics"] or k in c["mics"]} or ex
        power = {k: max(0.0, 10 ** (v / 10) - 1) for k, v in pool.items()}
        total = sum(power.values())
        if not total:
            named = [k for k in c["mics"] if k in self.mics]
            if named:
                power, total = {k: 1.0 for k in named}, float(len(named))
        if total:
            e = sum(p * self.mics[k].distance * math.sin(math.radians(self.mics[k].bearing)) for k, p in power.items())
            nn = sum(p * self.mics[k].distance * math.cos(math.radians(self.mics[k].bearing)) for k, p in power.items())
            top = max(power, key=power.get)
            vals = list(pool.values())
            far = len(vals) >= 3 and max(vals) - min(vals) < 3 and ev.cls in AIR
            ev.far, ev.mic = far, None if far else top
            ev.bearing = None if far else (math.degrees(math.atan2(e, nn)) + 360) % 360
            ev.method = "camera" if not any(pool.values()) or all(v <= 0 for v in pool.values()) else "levels"
            if far:
                ev.detail = "Overhead or distant: equally loud at every microphone"
            else:
                ev.detail = f"Loudest at {self.mics[top].name}"
        scientific = ev.extra.get("scientific")
        if ev.cls == "bird" and scientific:
            ev.detail = f"{scientific} · {ev.detail}" if ev.detail else scientific

    # ---------------------------------------------------------------- output
    def snapshot(self, now: float) -> dict:
        mics = []
        for m in self.mics.values():
            ok = m.feats is not None and now - m.feats_at < 6
            mics.append({
                "id": m.id, "name": m.name, "bearing": m.bearing, "distance": m.distance, "ok": ok,
                "level": round(float(m.feats.level), 1) if ok else None,
                "excess": round(max(m.feats.excess.values()), 1) if ok and m.feats.excess else 0,
            })
        return {
            "now": now, "mics": mics,
            "active": [e.as_dict() for e in sorted(self.active.values(), key=lambda e: -e.conf)],
            "recent": [e.as_dict() for e in list(self.history)[:40]],
            "aircraft": self.aircraft[:25] if now - self.aircraft_at < 90 else [],
        }
