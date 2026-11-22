"""Audio analysis for Soundscape. Pure numpy, no Home Assistant imports.

One Analyzer per microphone. Feed it 16-bit mono PCM; it returns

* spectrogram columns for display (log-spaced bands, one byte per band), and
* once a second, a Features record: levels per band, how far each band sits
  above that microphone's own noise floor, and scores for four signatures that
  can be told apart from the signal itself:

  siren      a strong tone sweeping (wail, yelp) or stepping (hi-lo)
             between roughly 400 and 1800 Hz
  howl       a wandering, unsteady tone in the same range (coyote, dog)
  rotor      broadband noise beating at a blade-pass rate of 9-32 Hz
             (helicopter, tiltrotor)
  propeller  a stack of harmonics on a 55-150 Hz fundamental

Everything else (barks, glass, car alarms, bird species) is left to the
classifiers that are trained for it; see fusion.py.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

N_FFT = 1024
HOP = 256
HOPS_PER_COL = 8
N_BANDS = 96
F_LO = 60.0
DB_MIN, DB_MAX = -110.0, -10.0  # wide on purpose: the card stretches contrast per microphone

BANDS = {
    "sub": (40, 150),
    "low": (150, 500),
    "mid": (500, 2000),
    "high": (2000, 5000),
    "top": (5000, 11000),
}
RIDGE = (350, 2500)
ENVELOPE = (150, 1200)
ROTOR_HZ = (9.0, 32.0)
PROP_HZ = (55.0, 150.0)
PROP_HARMONICS = 6


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


@dataclass
class Features:
    """One second of one microphone."""

    t: float = 0.0
    level: float = -120.0
    bands: dict[str, float] = field(default_factory=dict)
    excess: dict[str, float] = field(default_factory=dict)
    siren: float = 0.0
    howl: float = 0.0
    rotor: float = 0.0
    prop: float = 0.0
    ridge_hz: float = 0.0
    rotor_hz: float = 0.0
    prop_hz: float = 0.0
    ready: bool = False


class Analyzer:
    def __init__(self, sr: int = 24000) -> None:
        self.sr = sr
        self.fps = sr / HOP
        self.cols_per_s = self.fps / HOPS_PER_COL
        self.f_hi = min(11000.0, sr / 2 * 0.92)
        win = np.hanning(N_FFT).astype(np.float32)
        self._win = win
        self._scale = 2.0 / float(win.sum())
        freqs = np.fft.rfftfreq(N_FFT, 1 / sr)
        self._freqs = freqs
        edges = np.geomspace(F_LO, self.f_hi, N_BANDS + 1)
        lo = np.searchsorted(freqs, edges[:-1])
        hi = np.maximum(lo + 1, np.searchsorted(freqs, edges[1:]))
        self._b_lo, self._b_hi = lo, np.minimum(hi, len(freqs))
        self.band_edges = edges
        self._slices = {
            k: slice(*np.searchsorted(freqs, v)) for k, v in BANDS.items()
        }
        self._ridge = slice(*np.searchsorted(freqs, RIDGE))
        self._env = slice(*np.searchsorted(freqs, ENVELOPE))

        self._pending = np.zeros(0, np.float32)
        self._col_acc = np.zeros(len(freqs), np.float64)
        self._col_n = 0
        self._audio = np.zeros(int(sr * 6), np.float32)
        n8 = int(self.fps * 8)
        self._r_hz: deque[float] = deque(maxlen=n8)
        self._r_prom: deque[float] = deque(maxlen=n8)
        self._envelope: deque[float] = deque(maxlen=int(self.fps * 6))
        self._sec_pow = {k: 0.0 for k in BANDS}
        self._sec_sq = 0.0
        self._sec_n = 0
        self._sec_frames = 0
        self._floor: dict[str, deque[float]] = {k: deque(maxlen=120) for k in BANDS}
        self._bg: np.ndarray | None = None
        self._ticks = 0
        self._frames_total = 0

    # ------------------------------------------------------------------ feed
    def process(self, pcm: bytes) -> tuple[bytes, int, Features | None]:
        """Take PCM s16le mono. Return (columns, n_columns, features or None)."""
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if not len(x):
            return b"", 0, None
        n = len(x)
        if n >= len(self._audio):
            self._audio[:] = x[-len(self._audio):]
        else:
            self._audio[:-n] = self._audio[n:]
            self._audio[-n:] = x
        self._sec_sq += float(np.dot(x, x))
        self._sec_n += n

        buf = np.concatenate((self._pending, x))
        if len(buf) < N_FFT:
            self._pending = buf
            return b"", 0, None
        frames = sliding_window_view(buf, N_FFT)[::HOP]
        self._pending = buf[len(frames) * HOP:]
        spec = np.fft.rfft(frames * self._win, axis=1)
        power = (np.abs(spec) * self._scale) ** 2 + 1e-14

        ridge = power[:, self._ridge]
        pk = ridge.argmax(axis=1)
        prom = 10 * np.log10(ridge.max(axis=1) / np.median(ridge, axis=1))
        self._r_hz.extend((self._freqs[self._ridge][pk]).tolist())
        self._r_prom.extend(prom.tolist())
        # Median across the band: follows broadband noise, ignores single tones.
        self._envelope.extend(np.sqrt(np.median(power[:, self._env], axis=1)).tolist())
        for k, sl in self._slices.items():
            self._sec_pow[k] += float(power[:, sl].sum())
        self._sec_frames += len(power)
        self._frames_total += len(power)

        cols = []
        for row in power:
            self._col_acc += row
            self._col_n += 1
            if self._col_n == HOPS_PER_COL:
                cols.append(self._column(self._col_acc / HOPS_PER_COL))
                self._col_acc[:] = 0
                self._col_n = 0

        feats = None
        if self._sec_frames >= self.fps:
            feats = self._tick()
        return b"".join(cols), len(cols), feats

    def _column(self, p: np.ndarray) -> bytes:
        cs = np.concatenate(([0.0], np.cumsum(p)))
        band = (cs[self._b_hi] - cs[self._b_lo]) / (self._b_hi - self._b_lo)
        db = 10 * np.log10(band)
        return np.clip((db - DB_MIN) / (DB_MAX - DB_MIN) * 255, 0, 255).astype(np.uint8).tobytes()

    # ------------------------------------------------------------- features
    def _tick(self) -> Features:
        self._ticks += 1
        f = Features(t=self._frames_total / self.fps)
        f.level = 10 * np.log10(self._sec_sq / max(1, self._sec_n) + 1e-12)
        for k in BANDS:
            db = 10 * np.log10(self._sec_pow[k] / self._sec_frames + 1e-14)
            f.bands[k] = float(db)
            hist = self._floor[k]
            floor = float(np.percentile(hist, 20)) if len(hist) >= 8 else db
            f.excess[k] = float(db - floor)
            hist.append(db)
            self._sec_pow[k] = 0.0
        self._sec_sq, self._sec_n, self._sec_frames = 0.0, 0, 0
        f.ready = self._ticks >= 10

        self._tone(f)
        self._propeller(f)
        self._rotor(f)
        if not f.ready:
            f.siren = f.howl = f.rotor = f.prop = 0.0
        return f

    def _tone(self, f: Features) -> None:
        """Siren and howl: the loudest tone between 350 and 2500 Hz, tracked."""
        n4 = int(self.fps * 4)
        if len(self._r_hz) < n4:
            return
        hz = np.asarray(self._r_hz, dtype=np.float64)
        tonal = np.asarray(self._r_prom) > 14.0
        recent = tonal[-n4:]
        frac = float(recent.mean())
        if recent.sum() < n4 * 0.2:
            return
        h4 = hz[-n4:][recent]
        f.ridge_hz = float(np.median(h4))
        lo, hi = np.percentile(h4, [10, 90])
        span = float(hi - lo)
        step = float(np.median(np.abs(np.diff(h4)))) if len(h4) > 2 else 1e9
        bin_hz = self.sr / N_FFT
        # A real tone moves at most a few bins per frame; noise jumps anywhere.
        smooth = _clip01(1.5 - step / (3 * bin_hz))
        in_band = 1.0 if 380 <= lo and hi <= 2000 else 0.4

        # How regularly the pitch repeats, over the 8 s kept.
        period = 0.0
        if tonal.sum() > len(hz) * 0.4 and len(hz) >= n4 * 2 - 4:
            idx = np.arange(len(hz))
            track = np.interp(idx, idx[tonal], hz[tonal])
            track = track - track.mean()
            denom = float(np.dot(track, track))
            if denom > 0:
                ac = np.correlate(track, track, "full")[len(track) - 1:] / denom
                lag0 = int(self.fps * 0.2)
                neg = np.nonzero(ac < 0)[0]
                start = max(lag0, int(neg[0]) if len(neg) else lag0)
                stop = int(self.fps * 4)
                if start < stop:
                    # Unbiased: fewer overlapping samples at longer lags.
                    seg = ac[start:stop] * len(track) / (len(track) - np.arange(start, stop))
                    period = _clip01(float(seg.max()))

        # Breaks: the pitch leaping to somewhere new. A wail or yelp has none,
        # a hi-lo has them on a strict beat, a pack of coyotes has them at random.
        d = np.abs(np.diff(h4))
        breaks = float((d > 150).sum()) / 4.0
        regular = max(period, 1.0 - breaks / 0.5)
        sweep = _clip01((span - 120) / 200)
        if period > 0.6 and span > 100:
            sweep = max(sweep, 0.8 * period)  # two fixed tones, alternating
        f.siren = (
            _clip01((frac - 0.7) / 0.25) * sweep * smooth * in_band
            * (0.25 + 0.75 * _clip01(regular))
        )
        f.howl = (
            _clip01((frac - 0.2) / 0.3) * _clip01((span - 60) / 150) * smooth
            * (1 - 0.8 * period) * (1 - f.siren) * 0.7
        )

    def _rotor(self, f: Features) -> None:
        """Blade-pass beating in the broadband envelope."""
        e = np.asarray(self._envelope, dtype=np.float64)
        if len(e) < self._envelope.maxlen:
            return
        k = int(self.fps)
        trend = np.convolve(e, np.ones(k) / k, "same") + 1e-12
        m = (e / trend - 1.0) * np.hanning(len(e))
        spec = np.abs(np.fft.rfft(m)) ** 2
        fr = np.fft.rfftfreq(len(e), 1 / self.fps)
        band = (fr >= ROTOR_HZ[0]) & (fr <= ROTOR_HZ[1])
        ref = np.median(spec[(fr >= 5) & (fr <= 45)]) + 1e-18
        i = int(np.argmax(np.where(band, spec, 0)))
        strength = 10 * np.log10(spec[i] / ref)
        f.rotor_hz = float(fr[i])
        loud = _clip01((max(f.excess["low"], f.excess["mid"]) - 2) / 4)
        f.rotor = _clip01((strength - 15) / 8) * loud * (1 - max(f.siren, f.howl))
        if f.prop > 0.3:
            # A propeller's harmonics leak between analysis frames and show up
            # here at an alias of their spacing. That is not a rotor.
            alias = abs((f.prop_hz + self.fps / 2) % self.fps - self.fps / 2)
            if min(abs(f.rotor_hz - alias), abs(f.rotor_hz - 2 * alias)) < 0.8:
                f.rotor = 0.0

    def _propeller(self, f: Features) -> None:
        """Harmonic stack on a 55-150 Hz fundamental, above the usual hum."""
        seg = int(self.sr * 2)
        step = self.sr
        acc = None
        win = np.hanning(seg)
        for s in range(0, len(self._audio) - seg + 1, step):
            p = np.abs(np.fft.rfft(self._audio[s:s + seg] * win)[:2001]) ** 2
            acc = p if acc is None else acc + p
        db = 10 * np.log10(acc + 1e-16)  # 0.5 Hz per bin, 0-1000 Hz
        if self._bg is None:
            self._bg = db.copy()
            return
        e = db - self._bg
        self._bg += (db - self._bg) / 90.0  # mains hum and fans fade into it
        f0 = np.arange(PROP_HZ[0], PROP_HZ[1], 0.5)
        total = np.zeros(len(f0))
        present = np.zeros(len(f0))
        low = np.zeros(len(f0))
        for h in range(1, PROP_HARMONICS + 1):
            width = 2 * (1 + h // 2) + 1
            pad = width // 2
            mx = sliding_window_view(np.pad(e, pad, mode="edge"), width).max(axis=1)
            # Each harmonic against the gap just below it, so a rise across
            # the whole band (wind, a passing car) counts for nothing.
            v = mx[np.round(f0 * h / 0.5).astype(int)] - mx[np.round(f0 * (h - 0.5) / 0.5).astype(int)]
            total += v
            present += v > 6
            if h <= 3:
                low += v > 6
        total /= PROP_HARMONICS
        i = int(np.argmax(total))
        f.prop_hz = float(f0[i])
        # The stack has to start at the bottom: a siren's energy sits far above.
        if present[i] >= 4 and low[i] >= 2:
            f.prop = _clip01((total[i] - 8) / 8) * (1 - f.siren)
