"""Built-in plugin effects for Wave Studio.

Every plugin subclasses :class:`Effect`, declares a PARAMS spec (which the UI
turns into knobs/combos automatically) and implements ``process(x, sr)`` on a
mono or stereo float block. Instances keep their own state and can be
live-tweaked while audio is running.

Block sizes are small, so a few Python loops (compressor envelopes, reverb
combs) are perfectly affordable here.
"""
from __future__ import annotations

import numpy as np

SR = 44100


# ---------------------------------------------------------------------------
# framework
# ---------------------------------------------------------------------------
class Effect:
    type_id = "base"
    name = "Effect"
    # (key, label, min, max, default, kind[, extra])
    # kind: float | int | log | choice ; extra = choices list for 'choice'
    PARAMS: list[tuple] = []

    def __init__(self, params: dict | None = None, enabled: bool = True):
        self.enabled = enabled
        self.params = {spec[0]: spec[4] for spec in self.PARAMS}
        if params:
            for k, v in params.items():
                if k in self.params:
                    self.params[k] = v
        self.bpm = 126.0              # injected by the engine every block
        self.reset()

    def reset(self):
        pass

    def get(self, key, default=None):
        return self.params.get(key, default)

    def process(self, x: np.ndarray, sr: int) -> np.ndarray:
        return x

    def to_dict(self):
        return {"type": self.type_id, "enabled": self.enabled,
                "params": dict(self.params)}


def effect_from_dict(d: dict) -> Effect:
    return EFFECTS[d["type"]](d.get("params"), d.get("enabled", True))


# ---------------------------------------------------------------------------
# biquad helper (RBJ cookbook)
# ---------------------------------------------------------------------------
class Biquad:
    def __init__(self, mode="lp", f0=1000.0, q=0.707, gain_db=0.0, sr=SR):
        self.configure(mode, f0, q, gain_db, sr)

    def configure(self, mode, f0, q, gain_db, sr):
        w0 = 2 * np.pi * min(f0, sr * 0.45) / sr
        cw, sw = np.cos(w0), np.sin(w0)
        alpha = sw / (2 * q)
        A = 10 ** (gain_db / 40.0)
        if mode == "lp":
            b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
            a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
        elif mode == "hp":
            b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
            a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
        elif mode == "peak":
            b0, b1, b2 = 1 + alpha * A, -2 * cw, 1 - alpha * A
            a0, a1, a2 = 1 + alpha / A, -2 * cw, 1 - alpha / A
        elif mode == "lowshelf":
            sq = 2 * np.sqrt(A) * alpha
            b0 = A * ((A + 1) - (A - 1) * cw + sq)
            b1 = 2 * A * ((A - 1) - (A + 1) * cw)
            b2 = A * ((A + 1) - (A - 1) * cw - sq)
            a0 = (A + 1) + (A - 1) * cw + sq
            a1 = -2 * ((A - 1) + (A + 1) * cw)
            a2 = (A + 1) + (A - 1) * cw - sq
        elif mode == "highshelf":
            sq = 2 * np.sqrt(A) * alpha
            b0 = A * ((A + 1) + (A - 1) * cw + sq)
            b1 = -2 * A * ((A - 1) + (A + 1) * cw)
            b2 = A * ((A + 1) + (A - 1) * cw - sq)
            a0 = (A + 1) - (A - 1) * cw + sq
            a1 = 2 * ((A - 1) - (A + 1) * cw)
            a2 = (A + 1) - (A - 1) * cw - sq
        else:
            raise ValueError(mode)
        self.b0, self.b1, self.b2 = b0 / a0, b1 / a0, b2 / a0
        self.a1, self.a2 = a1 / a0, a2 / a0
        self.z1 = None
        self.z2 = None

    def process(self, x: np.ndarray) -> np.ndarray:
        squeeze = x.ndim == 1
        if squeeze:
            x = x[:, None]
        ch = x.shape[1]
        if self.z1 is None or self.z1.shape[0] != ch:
            self.z1 = np.zeros(ch)
            self.z2 = np.zeros(ch)
        y = np.empty_like(x)
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        z1, z2 = self.z1, self.z2
        for i in range(x.shape[0]):
            xi = x[i]
            yi = b0 * xi + z1
            z1 = b1 * xi - a1 * yi + z2
            z2 = b2 * xi - a2 * yi
            y[i] = yi
        self.z1, self.z2 = z1, z2
        return y[:, 0] if squeeze else y


# ---------------------------------------------------------------------------
# plugins
# ---------------------------------------------------------------------------
class FilterFX(Effect):
    type_id = "filter"
    name = "Filter"
    PARAMS = [
        ("mode", "Mode", 0, 1, 0, "choice", ["Lowpass", "Highpass"]),
        ("cutoff", "Cutoff", 80, 18000, 2200, "log"),
        ("reso", "Resonance", 0.5, 8.0, 0.8, "float"),
    ]

    def reset(self):
        self._bq = None

    def process(self, x, sr):
        if self._bq is None:
            self._bq = Biquad(sr=sr)
        self._bq.configure("hp" if int(self.get("mode")) else "lp",
                           self.get("cutoff"), self.get("reso"), 0.0, sr)
        return self._bq.process(x)


class ParametricEQFX(Effect):
    type_id = "eq"
    name = "Parametric EQ"
    PARAMS = [
        ("low", "Low (200 Hz)", -15, 15, 0, "float"),
        ("mid", "Mid (1 kHz)", -15, 15, 0, "float"),
        ("high", "High (8 kHz)", -15, 15, 0, "float"),
    ]

    def reset(self):
        self._stages = None

    def process(self, x, sr):
        if self._stages is None:
            self._stages = [Biquad("lowshelf", 200, 0.707, 0, sr),
                            Biquad("peak", 1000, 0.9, 0, sr),
                            Biquad("highshelf", 8000, 0.707, 0, sr)]
        self._stages[0].configure("lowshelf", 200, 0.707, self.get("low"), sr)
        self._stages[1].configure("peak", 1000, 0.9, self.get("mid"), sr)
        self._stages[2].configure("highshelf", 8000, 0.707, self.get("high"), sr)
        for st in self._stages:
            x = st.process(x)
        return x


class DelayFX(Effect):
    type_id = "delay"
    name = "Echo Delay"
    PARAMS = [
        ("time", "Time", 0, 3, 1, "choice", ["1/16", "1/8", "1/4", "1/2"]),
        ("feedback", "Feedback", 0.0, 0.9, 0.35, "float"),
        ("mix", "Mix", 0.0, 1.0, 0.35, "float"),
    ]
    BEATS = (0.25, 0.5, 1.0, 2.0)

    def reset(self):
        self._buf = None
        self._idx = 0
        self._d = 0

    def process(self, x, sr):
        delay = int(self.BEATS[int(self.get("time"))] * 60.0 /
                    max(20.0, self.bpm) * sr)
        delay = max(1, min(delay, sr * 4))
        squeeze = x.ndim == 1
        if squeeze:
            x = x[:, None]
        n, ch = x.shape
        if self._buf is None or self._buf.shape[0] < delay or \
                self._buf.shape[1] != ch:
            self._buf = np.zeros((max(delay, 8), ch))
            self._idx = 0
            self._d = 0
        if self._d != delay:                   # retune: clear to avoid junk
            self._buf[:] = 0.0
            self._d = delay
        fb = self.get("feedback")
        mix = self.get("mix")
        out = np.empty_like(x)
        buf, idx = self._buf, self._idx
        mod = delay
        for i in range(n):
            rd = (idx - delay) % mod
            echo = buf[rd]
            cur = x[i]
            buf[idx] = cur + echo * fb
            out[i] = cur * (1 - mix) + echo * mix
            idx = (idx + 1) % mod
        self._idx = idx
        return out[:, 0] if squeeze else out


class ReverbFX(Effect):
    type_id = "reverb"
    name = "Reverb"
    PARAMS = [
        ("room", "Room size", 0.0, 1.0, 0.45, "float"),
        ("damp", "Damping", 0.0, 1.0, 0.5, "float"),
        ("mix", "Mix", 0.0, 1.0, 0.3, "float"),
    ]
    _COMBS = (1116, 1188, 1277, 1356, 1422, 1491)
    _ALLPASS = (556, 441)

    def reset(self):
        self._state = None

    class _Comb:
        __slots__ = ("buf", "idx", "store")

        def __init__(self, n):
            self.buf = np.zeros(n)
            self.idx = 0
            self.store = 0.0

    def process(self, x, sr):
        squeeze = x.ndim == 1
        if squeeze:
            x = x[:, None]
        n, ch = x.shape
        room, damp, mix = self.get("room"), self.get("damp"), self.get("mix")
        scale = sr / 44100.0
        if self._state is None or self._state[0] != ch or self._state[1] != scale:
            combs = [[self._Comb(int(c * scale)) for c in self._COMBS]
                     for _ in range(ch)]
            aps = [[self._Comb(int(a * scale)) for a in self._ALLPASS]
                   for _ in range(ch)]
            self._state = (ch, scale, combs, aps)
        _, _, combs, aps = self._state
        fb = 0.68 + 0.3 * room
        g = 0.5
        out = np.empty_like(x)
        for i in range(n):
            for c in range(ch):
                xi = x[i, c]
                acc = 0.0
                for comb in combs[c]:
                    b = comb.buf
                    val = b[comb.idx]
                    comb.store = val * (1 - damp) + comb.store * damp
                    b[comb.idx] = xi + comb.store * fb
                    comb.idx = (comb.idx + 1) % b.shape[0]
                    acc += val
                wet = acc / len(combs[c])
                for ap in aps[c]:
                    b = ap.buf
                    val = b[ap.idx]
                    b[ap.idx] = wet + val * g
                    wet = val - g * wet
                    ap.idx = (ap.idx + 1) % b.shape[0]
                out[i, c] = xi * (1 - mix) + wet * mix * 1.6
        return out[:, 0] if squeeze else out


class DistortionFX(Effect):
    type_id = "distortion"
    name = "Distortion"
    PARAMS = [
        ("drive", "Drive", 1.0, 30.0, 5.0, "log"),
        ("tone", "Tone", 0.0, 1.0, 0.7, "float"),
        ("mix", "Mix", 0.0, 1.0, 0.6, "float"),
    ]

    def reset(self):
        self._lp = None

    def process(self, x, sr):
        drive = self.get("drive")
        tone = 0.02 + 0.4 * self.get("tone")
        mix = self.get("mix")
        y = np.tanh(x * drive) / np.tanh(drive)
        # soft one-pole tone
        squeeze = y.ndim == 1
        if squeeze:
            y = y[:, None]
        if self._lp is None or self._lp.shape[0] != y.shape[1]:
            self._lp = np.zeros(y.shape[1])
        lp = self._lp
        for i in range(y.shape[0]):            # cheap, block is small
            lp = lp + tone * (y[i] - lp)
            y[i] = lp
        self._lp = lp
        out = y[:, 0] if squeeze else y
        src = x[:, 0] if (x.ndim > 1 and squeeze) else x
        return (1 - mix) * src + mix * out


class BitcrusherFX(Effect):
    type_id = "bitcrusher"
    name = "Bitcrusher"
    PARAMS = [
        ("bits", "Bits", 2, 16, 8, "int"),
        ("downsample", "Downsample", 1, 40, 6, "int"),
        ("mix", "Mix", 0.0, 1.0, 0.7, "float"),
    ]

    def process(self, x, sr):
        bits = int(self.get("bits"))
        div = max(1, int(self.get("downsample")))
        mix = self.get("mix")
        levels = 2.0 ** bits
        idx = (np.arange(x.shape[0]) // div) * div
        crushed = np.round(x[idx] * levels) / levels
        return x * (1 - mix) + crushed * mix


class ChorusFX(Effect):
    type_id = "chorus"
    name = "Chorus"
    PARAMS = [
        ("rate", "Rate", 0.1, 5.0, 0.8, "log"),
        ("depth", "Depth", 0.0, 1.0, 0.45, "float"),
        ("mix", "Mix", 0.0, 1.0, 0.5, "float"),
    ]

    def reset(self):
        self._buf = None
        self._idx = 0
        self._phase = 0.0

    def process(self, x, sr):
        squeeze = x.ndim == 1
        if squeeze:
            x = x[:, None]
        n, ch = x.shape
        if self._buf is None or self._buf.shape[1] != ch:
            self._buf = np.zeros((int(0.05 * sr), ch))   # 50 ms
            self._idx = 0
        buf = self._buf
        blen = buf.shape[0]
        base = 0.015 * sr
        depth = self.get("depth") * 0.012 * sr
        rate = self.get("rate")
        mix = self.get("mix")
        out = np.empty_like(x)
        ph = self._phase
        idx = self._idx
        for i in range(n):
            delay = base + depth * np.sin(ph)
            ph += 2 * np.pi * rate / sr
            rd = (idx - delay) % blen
            i0 = int(np.floor(rd))
            i1 = (i0 + 1) % blen
            frac = rd - i0
            wet = buf[i0] * (1 - frac) + buf[i1] * frac
            buf[idx] = x[i] + wet * 0.4
            out[i] = x[i] * (1 - mix) + wet * mix
            idx = (idx + 1) % blen
        self._idx = idx
        self._phase = ph
        return out[:, 0] if squeeze else out


class CompressorFX(Effect):
    type_id = "compressor"
    name = "Compressor"
    PARAMS = [
        ("threshold", "Threshold", -40.0, 0.0, -18.0, "float"),
        ("ratio", "Ratio", 1.0, 20.0, 4.0, "float"),
        ("attack", "Attack", 0.1, 100.0, 8.0, "log"),
        ("release", "Release", 10.0, 600.0, 140.0, "log"),
        ("makeup", "Makeup", 0.0, 24.0, 5.0, "float"),
    ]

    def reset(self):
        self._env = 0.0

    def process(self, x, sr):
        thr = self.get("threshold")
        ratio = self.get("ratio")
        atk = np.exp(-1.0 / (sr * self.get("attack") / 1000.0))
        rel = np.exp(-1.0 / (sr * self.get("release") / 1000.0))
        makeup = 10 ** (self.get("makeup") / 20.0)
        level = np.abs(x)
        if level.ndim > 1:
            level = level.max(axis=1)          # linked stereo
        env = self._env
        out = np.empty_like(x)
        for i in range(level.shape[0]):
            l = level[i]
            coef = atk if l > env else rel
            env = coef * env + (1 - coef) * l
            env_db = 20 * np.log10(env + 1e-8)
            if env_db > thr:
                gain_db = (thr + (env_db - thr) / ratio) - env_db
            else:
                gain_db = 0.0
            out[i] = x[i] * (10 ** (gain_db / 20.0)) * makeup
        self._env = env
        return out


class LimiterFX(Effect):
    type_id = "limiter"
    name = "Limiter"
    PARAMS = [
        ("ceiling", "Ceiling", -12.0, 0.0, -1.0, "float"),
        ("release", "Release", 10.0, 500.0, 80.0, "log"),
    ]

    def reset(self):
        self._g = 1.0

    def process(self, x, sr):
        ceil = 10 ** (self.get("ceiling") / 20.0)
        rel = np.exp(-1.0 / (sr * self.get("release") / 1000.0))
        level = np.abs(x)
        if level.ndim > 1:
            level = level.max(axis=1)
        g = self._g
        out = np.empty_like(x)
        for i in range(level.shape[0]):
            l = level[i]
            needed = ceil / l if l > ceil else 1.0
            g = needed if needed < g else rel * g + (1 - rel) * 1.0
            out[i] = x[i] * g
        self._g = g
        return out


class WidthFX(Effect):
    type_id = "width"
    name = "Stereo Width"
    PARAMS = [("width", "Width", 0.0, 2.0, 1.1, "float")]

    def process(self, x, sr):
        if x.ndim == 1:
            return x
        w = self.get("width")
        mid = (x[:, 0] + x[:, 1]) * 0.5
        side = (x[:, 0] - x[:, 1]) * 0.5 * w
        return np.stack((mid + side, mid - side), axis=1)


EFFECTS = {cls.type_id: cls for cls in (
    FilterFX, ParametricEQFX, DelayFX, ReverbFX, DistortionFX,
    BitcrusherFX, ChorusFX, CompressorFX, LimiterFX, WidthFX,
)}

EFFECT_MENU = [
    ("Delay & Space", ["delay", "reverb", "chorus"]),
    ("Tone", ["filter", "eq", "distortion", "bitcrusher", "width"]),
    ("Dynamics", ["compressor", "limiter"]),
]
