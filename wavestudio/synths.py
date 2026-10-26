"""Sound synthesis for Wave Studio.

Every instrument is a small NumPy routine that renders a mono float32 buffer.
Drum one-shots are rendered once and cached; melodic notes are rendered per
trigger (they cost well under a millisecond and are cached as well).
"""
from __future__ import annotations

import numpy as np

SR = 44100


def midi_to_freq(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def _norm(x: np.ndarray, target: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak > 1e-9:
        x = x * (target / peak)
    return x.astype(np.float32)


def _smooth(x: np.ndarray, k: float) -> np.ndarray:
    """Cheap exponential one-pole-ish lowpass via causal convolution."""
    if k <= 1:
        return x
    kern = np.exp(-np.arange(int(8 * k)) / k)
    kern /= kern.sum()
    return np.convolve(x, kern, mode="full")[: len(x)]


def _t(dur: float, sr: int) -> np.ndarray:
    return np.arange(int(dur * sr), dtype=np.float64) / sr


def _noise(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


def _adsr(n: int, a: float, d: float, s: float, r: float, sr: int) -> np.ndarray:
    na, nd, nr = int(a * sr), int(d * sr), int(r * sr)
    na = min(na, n)
    nd = min(nd, n - na)
    nr = min(nr, n - na - nd)
    ns = n - na - nd - nr
    parts = []
    if na:
        parts.append(np.linspace(0.0, 1.0, na, endpoint=False))
    if nd:
        parts.append(np.linspace(1.0, s, nd, endpoint=False))
    if ns:
        parts.append(np.full(ns, s))
    if nr:
        parts.append(np.linspace(s, 0.0, nr))
    env = np.concatenate(parts) if parts else np.zeros(0)
    if env.size < n:                       # round-off safety
        env = np.pad(env, (0, n - env.size))
    return env[:n]


def _shifted_exp(t: np.ndarray, t0: float, rate: float, amp: float) -> np.ndarray:
    env = np.zeros_like(t)
    m = t >= t0
    env[m] = amp * np.exp(-(t[m] - t0) * rate)
    return env


# ---------------------------------------------------------------------------
# Drum one-shots
# ---------------------------------------------------------------------------
def synth_kick(sr: int = SR) -> np.ndarray:
    t = _t(0.45, sr)
    freq = 48.0 + 150.0 * np.exp(-t * 28.0)              # pitch drop
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    body = np.sin(phase) * np.exp(-t * 11.0)
    click = _noise(t.size, 1) * np.exp(-t * 400.0) * 0.55
    snap = np.sin(2 * np.pi * 900 * t) * np.exp(-t * 200.0) * 0.22
    return _norm(body + 0.3 * click + snap)


def synth_snare(sr: int = SR) -> np.ndarray:
    t = _t(0.26, sr)
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t * 40.0) * 0.5
    noise = _noise(t.size, 2) * np.exp(-t * 21.0) * 0.95
    return _norm(tone + noise)


def synth_clap(sr: int = SR) -> np.ndarray:
    t = _t(0.32, sr)
    noise = _noise(t.size, 3)
    noise = noise - _smooth(noise, 40.0)                  # highpass-ish
    env = (_shifted_exp(t, 0.000, 45.0, 1.0)
           + _shifted_exp(t, 0.012, 40.0, 0.85)
           + _shifted_exp(t, 0.025, 35.0, 0.7)
           + _shifted_exp(t, 0.040, 10.0, 0.9))           # reverb-y tail
    return _norm(noise * env)


def _metallic(sr: int, dur: float, decay: float, seed: int) -> np.ndarray:
    t = _t(dur, sr)
    noise = _noise(t.size, seed)
    noise = noise - _smooth(noise, 60.0)                  # keep the top end
    ring = np.zeros_like(t)
    for f in (5210.0, 6760.0, 8340.0, 10460.0):           # inharmonic sines
        ring += np.sin(2 * np.pi * f * t) * 0.18
    return (noise * 0.8 + ring) * np.exp(-t * decay)


def synth_chat(sr: int = SR) -> np.ndarray:
    return _norm(_metallic(sr, 0.07, 110.0, 4))


def synth_ohat(sr: int = SR) -> np.ndarray:
    return _norm(_metallic(sr, 0.42, 11.0, 5))


def synth_crash(sr: int = SR) -> np.ndarray:
    sig = _metallic(sr, 1.4, 3.4, 6)
    ramp = np.minimum(1.0, _t(1.4, sr) / 0.02)
    return _norm(sig * ramp)


def synth_tom(sr: int = SR) -> np.ndarray:
    t = _t(0.38, sr)
    freq = 92.0 + 90.0 * np.exp(-t * 22.0)
    body = np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-t * 13.0)
    attack = _noise(t.size, 7) * np.exp(-t * 200.0) * 0.3
    return _norm(body + attack)


def synth_rim(sr: int = SR) -> np.ndarray:
    t = _t(0.09, sr)
    tone = (np.sin(2 * np.pi * 1720 * t) * 0.6
            + np.sin(2 * np.pi * 815 * t) * 0.4)
    click = _noise(t.size, 8) * 0.5
    return _norm((tone + click) * np.exp(-t * 60.0))


def synth_shaker(sr: int = SR) -> np.ndarray:
    t = _t(0.15, sr)
    noise = _noise(t.size, 9)
    noise = noise - _smooth(noise, 50.0)
    env = np.minimum(1.0, t / 0.03) * _shifted_exp(t, 0.03, 24.0, 1.0)
    return _norm(noise * env)


def synth_click(accent: bool = False, sr: int = SR) -> np.ndarray:
    """Metronome click."""
    t = _t(0.045, sr)
    f = 2000.0 if accent else 1250.0
    return _norm(np.sin(2 * np.pi * f * t) * np.exp(-t * 90.0))


def synth_kick808(sr: int = SR) -> np.ndarray:
    """Long subby 808."""
    t = _t(0.9, sr)
    freq = 38.0 + 90.0 * np.exp(-t * 45.0)
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    body = np.sin(phase) * np.exp(-t * 4.6)
    click = _noise(t.size, 10) * np.exp(-t * 700.0) * 0.25
    return _norm(body + click)


def synth_cowbell(sr: int = SR) -> np.ndarray:
    t = _t(0.30, sr)
    osc = (np.square(np.sin(2 * np.pi * 562 * t))
           + np.square(np.sin(2 * np.pi * 845 * t)))
    osc = _smooth(osc, 3.0) - _smooth(osc, 60.0)     # band shape
    snap = _noise(t.size, 11) * np.exp(-t * 150.0) * 0.15
    return _norm(osc * np.exp(-t * 16.0) + snap)


def synth_riser(sr: int = SR) -> np.ndarray:
    """Two-second noise + sweep build-up."""
    t = _t(2.0, sr)
    noise = _noise(t.size, 12)
    noise = noise - _smooth(noise, 30.0)
    ramp = np.clip(t / 2.0, 0, 1) ** 1.6
    sweep = np.sin(2 * np.pi * np.cumsum(180 + 900 * (t / 2.0) ** 1.5) / sr)
    sig = (noise * 0.75 + sweep * 0.25) * ramp
    sig *= np.exp(-np.maximum(0.0, t - 1.9) * 30.0)  # tiny stop at the end
    return _norm(sig, 0.8)


DRUM_RENDERERS = {
    "kick": synth_kick,
    "kick808": synth_kick808,
    "snare": synth_snare,
    "clap": synth_clap,
    "chat": synth_chat,
    "ohat": synth_ohat,
    "crash": synth_crash,
    "tom": synth_tom,
    "rim": synth_rim,
    "shaker": synth_shaker,
    "cowbell": synth_cowbell,
    "riser": synth_riser,
}


def render_drum(generator: str, sr: int = SR) -> np.ndarray:
    return DRUM_RENDERERS[generator](sr)


# ---------------------------------------------------------------------------
# Melodic instruments
# ---------------------------------------------------------------------------
def render_melodic(generator: str, pitch: int, dur: float,
                   sr: int = SR, velocity: float = 0.8) -> np.ndarray:
    f = midi_to_freq(pitch)
    dur = max(0.08, dur)
    n = int(dur * sr)
    t = np.arange(n, dtype=np.float64) / sr

    if generator == "bass":
        ph = (np.cumsum(np.full(n, f)) / sr) % 1.0
        square = np.where(ph < 0.5, 1.0, -1.0)
        saw = 2.0 * ph - 1.0
        sub = np.sin(2 * np.pi * np.cumsum(np.full(n, f / 2)) / sr)
        sig = _smooth(0.9 * square + 0.45 * saw + 0.7 * sub, 18.0)
        env = _adsr(n, 0.004, 0.12, 0.55, 0.06, sr)

    elif generator == "pluck":
        ph1 = (np.cumsum(np.full(n, f)) / sr) % 1.0
        ph2 = (np.cumsum(np.full(n, f * 1.007)) / sr) % 1.0
        sig = (2.0 * ph1 - 1.0) + (2.0 * ph2 - 1.0) \
            + 0.35 * np.sin(2 * np.pi * 2 * f * t)
        sig = _smooth(sig, 9.0)
        env = _adsr(n, 0.002, min(0.28, dur * 0.55), 0.14, 0.08, sr)

    elif generator == "keys":
        sig = (np.sin(2 * np.pi * f * t)
               + 0.45 * np.sin(2 * np.pi * 2.0 * f * t)
               + 0.18 * np.sin(2 * np.pi * 3.02 * f * t)
               + 0.07 * np.sin(2 * np.pi * 4.18 * f * t))
        sig = _smooth(sig, 4.0)
        env = _adsr(n, 0.003, min(0.7, dur * 0.6), 0.28, 0.14, sr)

    elif generator == "lead":
        vib = 1.0 + 0.007 * np.sin(2 * np.pi * 6.0 * t) * np.minimum(1.0, t / 0.15)
        saw1 = 2.0 * ((np.cumsum(f * 0.996 * vib) / sr) % 1.0) - 1.0
        saw2 = 2.0 * ((np.cumsum(f * 1.005 * vib) / sr) % 1.0) - 1.0
        sig = _smooth(saw1 + saw2 + 0.4 * np.sin(2 * np.pi * f * t), 7.0)
        env = _adsr(n, 0.02, 0.08, 0.8, 0.12, sr)

    elif generator == "fmbell":
        idx = 7.0 * np.exp(-t * 2.6)                 # decaying FM index
        mod = np.sin(2 * np.pi * 3.5 * f * t)
        sig = np.sin(2 * np.pi * f * t + idx * mod)
        env = np.exp(-t * max(2.0, 3.0 - dur))
        env *= _adsr(n, 0.003, 0.0, 1.0, 0.1, sr)

    elif generator == "supersaw":
        cents = (-12, -6, 0, 6, 12)
        stack = np.zeros(n)
        for c in cents:
            fd = f * 2.0 ** (c / 1200.0)
            stack += 2.0 * ((np.cumsum(np.full(n, fd)) / sr) % 1.0) - 1.0
        sig = _smooth(stack / len(cents), 10.0)
        env = _adsr(n, 0.03, 0.15, 0.75, 0.15, sr)

    elif generator == "acid":
        ph = (np.cumsum(np.full(n, f)) / sr) % 1.0
        saw = 2.0 * ph - 1.0
        body = _smooth(np.tanh(saw * 1.8), 9.0)
        squelch = (saw - _smooth(saw, 16.0))          # "wow" top layer
        sig = body + squelch * np.exp(-t * 9.0) * 1.2
        env = _adsr(n, 0.003, 0.18, 0.5, 0.05, sr)

    else:                                                # fallback: soft sine
        sig = np.sin(2 * np.pi * f * t)
        env = _adsr(n, 0.01, 0.1, 0.7, 0.1, sr)

    out = _norm(sig * env) * (0.35 + 0.65 * float(velocity))
    return out.astype(np.float32)


# short aliases used by the piano-roll preview
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


# ---------------------------------------------------------------------------
# Sampler
# ---------------------------------------------------------------------------
def load_sample(path: str) -> np.ndarray:
    """Load a WAV (PCM 8/16/24/32-bit or float), mixed down to mono, peak
    normalised to 0.9."""
    import contextlib
    import wave

    with contextlib.closing(wave.open(path, "rb")) as wf:
        n = wf.getnframes()
        ch = wf.getnchannels()
        width = wf.getsampwidth()
        raw = wf.readframes(n)

    if width == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        a32 = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
               | (b[:, 2].astype(np.int32) << 16))
        a32 = np.where(a32 & 0x800000, a32 - (1 << 24), a32)
        a = a32.astype(np.float32) / 8388608.0
    elif width == 4:
        a = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {width}")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return _norm(a)


def repitch(buf: np.ndarray, semitones: float) -> np.ndarray:
    """Simple varispeed resampling: change pitch & length together."""
    rate = 2.0 ** (semitones / 12.0)
    n_out = max(2, int(len(buf) / rate))
    src = np.arange(len(buf), dtype=np.float64)
    dst = np.linspace(0.0, len(buf) - 1.0, n_out)
    return np.interp(dst, src, buf).astype(np.float32)
