"""Synthetic test sounds."""
import numpy as np

SR = 24000


def _t(sec):
    return np.arange(int(SR * sec)) / SR


def noise(sec, db=-50, seed=0):
    return np.random.default_rng(seed).standard_normal(int(SR * sec)) * 10 ** (db / 20)


def pink(sec, db=-45, seed=1):
    n = int(SR * sec)
    spec = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    spec /= np.maximum(1, np.arange(len(spec))) ** 0.5
    x = np.fft.irfft(spec, n)
    return x / x.std() * 10 ** (db / 20)


def chirp_from(freq, db=-25):
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return (np.sin(phase) + 0.4 * np.sin(2 * phase) + 0.2 * np.sin(3 * phase)) * 10 ** (db / 20)


def wail(sec, period=4.5, lo=650, hi=1450, db=-25):
    t = _t(sec)
    ph = (t % period) / period
    tri = np.where(ph < 0.5, ph * 2, 2 - ph * 2)
    return chirp_from(lo + (hi - lo) * tri, db)


def yelp(sec, db=-25):
    return wail(sec, period=0.33, db=db)


def hilo(sec, db=-25):
    t = _t(sec)
    return chirp_from(np.where((t % 1.1) < 0.55, 960.0, 770.0), db)


def howl(sec, db=-30, seed=3):
    """Unsteady voiced tone with gaps, loosely coyote-like."""
    rng = np.random.default_rng(seed)
    n = int(SR * sec)
    f = np.zeros(n)
    amp = np.zeros(n)
    i = 0
    while i < n:
        dur = int(SR * rng.uniform(0.6, 2.2))
        gap = int(SR * rng.uniform(0.1, 0.9))
        seg = min(dur, n - i)
        f0, f1, f2 = rng.uniform(500, 800), rng.uniform(900, 1500), rng.uniform(600, 1000)
        u = np.linspace(0, 1, seg)
        f[i:i + seg] = np.where(u < 0.25, f0 + (f1 - f0) * u / 0.25, f1 + (f2 - f1) * (u - 0.25) / 0.75)
        f[i:i + seg] += 25 * np.sin(2 * np.pi * 6 * u * seg / SR)
        amp[i:i + seg] = np.hanning(seg) ** 0.3
        i += dur + gap
    f[f == 0] = 700
    return chirp_from(f, db) * amp


def propeller(sec, f0=84.0, db=-30):
    t = _t(sec)
    x = sum(np.sin(2 * np.pi * f0 * h * t + h) / h ** 0.7 for h in range(1, 12))
    return x / np.abs(x).max() * 10 ** (db / 20)


def rotor(sec, bpf=17.2, db=-30, seed=5):
    """Broadband noise amplitude-modulated by blade-pass pulses."""
    t = _t(sec)
    x = pink(sec, 0, seed)
    pulse = np.clip(np.cos(2 * np.pi * bpf * t), 0, None) ** 4
    y = x * (0.35 + pulse)
    return y / y.std() * 10 ** (db / 20)


def hum(sec, db=-45):
    t = _t(sec)
    return sum(np.sin(2 * np.pi * 60 * h * t) / h for h in range(1, 8)) * 10 ** (db / 20)


def birds(sec, db=-35, seed=7):
    rng = np.random.default_rng(seed)
    n = int(SR * sec)
    y = np.zeros(n)
    for _ in range(int(sec * 4)):
        s = rng.integers(0, n - SR // 4)
        d = int(SR * rng.uniform(0.05, 0.2))
        f = np.linspace(rng.uniform(3000, 6000), rng.uniform(3000, 7000), d)
        y[s:s + d] += np.sin(2 * np.pi * np.cumsum(f) / SR) * np.hanning(d)
    return y * 10 ** (db / 20)


def passby(sec, db=-28, seed=9):
    """Car: broadband hiss rising and falling."""
    t = _t(sec)
    x = np.diff(pink(sec + 0.01, 0, seed))[: len(t)]
    env = np.exp(-(((t - sec / 2) / (sec / 6)) ** 2))
    return x / x.std() * env * 10 ** (db / 20)


def pcm(x):
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
