"""Real-time audio engine for Wave Studio.

Qt-free. The engine owns the transport (play head), triggers notes at step
boundaries, mixes active voices through per-channel **plugin chains** and a
master chain, and renders stereo float32 blocks. Output drivers:

* sounddevice callback (preferred, low latency)
* a silent clock thread (fallback when no audio device is present, so the UI
  still animates; WAV export always works either way)
"""
from __future__ import annotations

import threading
import time
import wave

import numpy as np

from .effects import effect_from_dict
from .model import Project
from .synths import SR, load_sample, render_drum, render_melodic, repitch, \
    synth_click

BLOCK = 512
_TAIL_SECONDS = 3.0


class _SilentDriver(threading.Thread):
    """Fallback clock used when no audio hardware is available."""

    def __init__(self, engine: "Engine"):
        super().__init__(daemon=True, name="WaveStudioSilentClock")
        self.engine = engine

    def run(self):
        block, sr = 512, self.engine.sr
        interval = block / sr
        next_t = time.perf_counter()
        while True:
            self.engine.process(block)
            next_t += interval
            dt = next_t - time.perf_counter()
            if dt > 0:
                time.sleep(dt)
            else:
                next_t = time.perf_counter()


class Engine:
    def __init__(self, project: Project, sr: int = SR, wrap: bool = True):
        self.sr = sr
        self.wrap = wrap                      # loop transport at end of pattern/song
        self.lock = threading.RLock()
        self.project = project

        self.playing = False
        self.mode = "pattern"                 # 'pattern' | 'song'
        self.metronome = False
        self.master_volume = project.master_volume

        # transport
        self.abs_step = 0                     # steps since transport start
        self.samples_into_step = 0.0
        self.play_samples = 0                 # total samples since play

        # mixing
        self.voices: list[dict] = []
        self.drum_cache: dict[str, np.ndarray] = {}
        self.sample_cache: dict[str, np.ndarray | None] = {}
        self.note_cache: dict = {}
        self.channel_peaks: dict[int, float] = {}
        self.master_peak = 0.0
        self._click_acc = synth_click(True, sr)
        self._click = synth_click(False, sr)

        # plugin chains
        self.fx_map: dict[int, list] = {}     # channel id -> [Effect]
        self.master_chain: list = []
        self.sync_fx()

        self._driver = None
        self.audio_backend = "not started"

    # ------------------------------------------------------------------
    # transport helpers
    # ------------------------------------------------------------------
    def samples_per_step(self) -> float:
        return self.sr * 60.0 / max(20.0, float(self.project.bpm)) / 4.0

    def _step_len(self, step_index: int) -> float:
        base = self.samples_per_step()
        swing = float(self.project.swing)
        return base * (1.0 + swing) if step_index % 2 == 0 else base * (1.0 - swing)

    def loop_steps(self) -> int:
        if self.mode == "song" and self.project.clips:
            return max(c.start + c.length for c in self.project.clips)
        return self.project.patterns[self.project.current_pattern].length

    def play(self):
        with self.lock:
            self.abs_step = 0
            self.samples_into_step = 0.0
            self.play_samples = 0
            self.voices.clear()
            self.playing = True
            self._trigger_current_step()      # fire step 0 immediately
        self.start_audio()

    def toggle_pause(self):
        """Spacebar behaviour: pause if playing, otherwise start/resume."""
        with self.lock:
            if self.playing:
                self.playing = False
                return
            fresh = self.abs_step == 0 and self.samples_into_step == 0
            self.playing = True
            if fresh:
                self.voices.clear()
                self.play_samples = 0
                self._trigger_current_step()
        self.start_audio()

    def stop(self):
        with self.lock:
            self.playing = False
            self.abs_step = 0
            self.samples_into_step = 0.0
            self.voices.clear()

    def seek(self, step: int):
        """Jump the transport to an absolute step (playlist ruler click)."""
        with self.lock:
            loop = max(1, self.loop_steps())
            self.abs_step = max(0, int(step)) % loop
            self.samples_into_step = 0.0
            if self.playing:
                self._trigger_current_step()

    def set_project(self, project: Project):
        with self.lock:
            self.project = project
            self.master_volume = project.master_volume
            self.voices.clear()
            self.note_cache.clear()
            self.sample_cache.clear()
            self.channel_peaks.clear()
            self.abs_step = 0
            self.samples_into_step = 0.0
            self.play_samples = 0
            self.sync_fx()

    # ------------------------------------------------------------------
    # plugin chains
    # ------------------------------------------------------------------
    def sync_fx(self):
        """(Re)build effect instances from the project. Called on structural
        edits (add/remove/reorder/toggle), project load and undo/redo."""
        with self.lock:
            self.fx_map = {}
            for ch in self.project.channels:
                self.fx_map[ch.id] = [effect_from_dict(f) for f in ch.fx]
            self.master_chain = [effect_from_dict(f)
                                 for f in self.project.master_fx]

    def update_fx_param(self, target, index: int, key: str, value):
        """Live-update one knob without resetting plugin state."""
        with self.lock:
            chain = self.master_chain if target is None \
                else self.fx_map.get(target, [])
            if 0 <= index < len(chain):
                chain[index].params[key] = value

    def set_fx_enabled(self, target, index: int, enabled: bool):
        with self.lock:
            chain = self.master_chain if target is None \
                else self.fx_map.get(target, [])
            if 0 <= index < len(chain):
                chain[index].enabled = enabled

    # ------------------------------------------------------------------
    # audio device
    # ------------------------------------------------------------------
    def start_audio(self):
        if self._driver is not None:
            return
        try:
            import sounddevice as sd

            def callback(outdata, frames, time_info, status):  # noqa: ARG001
                outdata[:] = self.process(frames)

            stream = sd.OutputStream(samplerate=self.sr, channels=2,
                                     dtype="float32", blocksize=BLOCK,
                                     callback=callback, latency="low")
            stream.start()
            self._driver = stream
            self.audio_backend = "sounddevice"
        except Exception as exc:               # no device / no portaudio
            clock = _SilentDriver(self)
            clock.start()
            self._driver = clock
            self.audio_backend = f"silent clock ({type(exc).__name__})"

    # ------------------------------------------------------------------
    # sound triggering
    # ------------------------------------------------------------------
    def _drum_buffer(self, generator: str) -> np.ndarray:
        buf = self.drum_cache.get(generator)
        if buf is None:
            buf = render_drum(generator, self.sr)
            self.drum_cache[generator] = buf
        return buf

    def _sample_buffer(self, path: str) -> np.ndarray:
        buf = self.sample_cache.get(path)
        if buf is None:
            try:
                buf = load_sample(path)
            except Exception:
                buf = synth_click(True, self.sr)        # audible placeholder
            self.sample_cache[path] = buf
        return buf

    def _melodic_buffer(self, generator: str, pitch: int,
                        dur: float, vel: float) -> np.ndarray:
        key = (generator, pitch, round(dur, 3), round(vel, 2))
        buf = self.note_cache.get(key)
        if buf is None:
            if len(self.note_cache) > 512:    # keep the cache bounded
                self.note_cache.clear()
            buf = render_melodic(generator, pitch, dur, self.sr, vel)
            self.note_cache[key] = buf
        return buf

    def _add_voice(self, buf: np.ndarray, channel_id, vel: float = 1.0):
        self.voices.append({"buf": buf, "pos": 0, "ch": channel_id,
                            "vel": float(vel)})

    def preview(self, channel, pitch: int = 60):
        """Audition a sound immediately (piano roll, browser, keyboard)."""
        with self.lock:
            kind = channel.kind
            if kind == "drum":
                self._add_voice(self._drum_buffer(channel.generator), channel.id)
            elif kind == "sample":
                path = channel.extra.get("sample")
                buf = self._sample_buffer(path) if path else synth_click(True, self.sr)
                if pitch != 60:
                    buf = repitch(buf, pitch - 60)
                self._add_voice(buf, channel.id)
            else:
                buf = self._melodic_buffer(channel.generator, pitch, 0.5, 0.85)
                self._add_voice(buf, channel.id)
        self.start_audio()

    def _trigger_pattern_step(self, pat, s: int, any_solo: bool, step_sec: float):
        for ch in self.project.channels:
            if any_solo and not ch.solo:
                continue
            if not any_solo and ch.mute:
                continue
            steps = pat.steps.get(ch.id)
            if steps is not None and s < len(steps) and steps[s]:
                if ch.kind == "drum":
                    self._add_voice(self._drum_buffer(ch.generator), ch.id)
                elif ch.kind == "sample":
                    path = ch.extra.get("sample")
                    if path:
                        self._add_voice(self._sample_buffer(path), ch.id)
                else:
                    buf = self._melodic_buffer(ch.generator, 60, step_sec, 0.85)
                    self._add_voice(buf, ch.id, 0.85)
            for note in pat.notes.get(ch.id, ()):
                if note.start == s:
                    if ch.kind == "drum":
                        self._add_voice(self._drum_buffer(ch.generator),
                                        ch.id, note.velocity)
                    elif ch.kind == "sample":
                        path = ch.extra.get("sample")
                        if path:
                            base = self._sample_buffer(path)
                            buf = repitch(base, note.pitch - 60) \
                                if note.pitch != 60 else base
                            self._add_voice(buf, ch.id, note.velocity)
                    else:
                        buf = self._melodic_buffer(ch.generator, note.pitch,
                                                   note.length * step_sec,
                                                   note.velocity)
                        self._add_voice(buf, ch.id, note.velocity)

    def _trigger_current_step(self):
        proj = self.project
        loop = self.loop_steps()
        if loop <= 0:
            return
        pos = self.abs_step % loop
        step_sec = float(self.samples_per_step()) / self.sr
        any_solo = any(c.solo for c in proj.channels)

        if self.mode == "song" and proj.clips:
            muted = proj.track_muted
            for clip in proj.clips:
                if 0 <= clip.track < len(muted) and muted[clip.track]:
                    continue                        # playlist track muted
                if clip.start <= pos < clip.start + clip.length:
                    pat = proj.patterns[clip.pattern]
                    local = pos - clip.start
                    if local < pat.length:
                        self._trigger_pattern_step(pat, local, any_solo, step_sec)
        else:
            pat = proj.patterns[proj.current_pattern]
            if pos < pat.length:
                self._trigger_pattern_step(pat, pos, any_solo, step_sec)

        if self.metronome and pos % 4 == 0:
            accent = (pos % 16 == 0)
            self._add_voice(self._click_acc if accent else self._click,
                            None, 0.9 if accent else 0.6)

    # ------------------------------------------------------------------
    # mixing
    # ------------------------------------------------------------------
    def _mix_voices(self, out: np.ndarray, start: int, seg: int):
        ch_bufs: dict[int, np.ndarray] = {}
        any_solo = any(c.solo for c in self.project.channels)
        done = []
        for v in self.voices:
            buf, pos = v["buf"], v["pos"]
            remaining = buf.size - pos
            if remaining <= 0:
                done.append(v)
                continue
            n = min(seg, remaining)
            ch_id = v["ch"]
            if ch_id is None:                          # metronome: no chain
                sig = buf[pos:pos + n].astype(np.float64) * v["vel"] * 0.5
                out[start:start + n, 0] += sig
                out[start:start + n, 1] += sig
            else:
                ch = self.project.channel(ch_id)
                if ch is None or (any_solo and not ch.solo) \
                        or (not any_solo and ch.mute):
                    pass                             # swallow silently
                else:
                    cb = ch_bufs.get(ch_id)
                    if cb is None:
                        cb = np.zeros(seg, dtype=np.float64)
                        ch_bufs[ch_id] = cb
                    cb[:n] += buf[pos:pos + n].astype(np.float64) * v["vel"]
            v["pos"] = pos + n
            if v["pos"] >= buf.size:
                done.append(v)
        if done:
            done_ids = {id(v) for v in done}
            self.voices = [v for v in self.voices if id(v) not in done_ids]

        # channel inserts, gain/pan into master
        for ch_id, cb in ch_bufs.items():
            chain = self.fx_map.get(ch_id)
            if chain:
                bpm = self.project.bpm
                for fx in chain:
                    if fx.enabled:
                        fx.bpm = bpm
                        cb = fx.process(cb, self.sr)
            ch = self.project.channel(ch_id)
            angle = (ch.pan + 1.0) * np.pi / 4.0       # constant power
            gl, gr = np.cos(angle) * ch.volume, np.sin(angle) * ch.volume
            out[start:start + seg, 0] += cb * gl
            out[start:start + seg, 1] += cb * gr
            peak = float(np.max(np.abs(cb))) * max(gl, gr) if seg else 0.0
            if peak > self.channel_peaks.get(ch_id, 0.0):
                self.channel_peaks[ch_id] = peak

    def process(self, frames: int, trigger: bool = True) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)
        with self.lock:
            idx = 0
            frac = 0.0
            while idx < frames:
                if self.playing:
                    cur_len = self._step_len(self.abs_step)
                    seg = min(frames - idx,
                              max(1, int(cur_len - self.samples_into_step)))
                else:
                    seg = frames - idx
                self._mix_voices(out, idx, seg)
                idx += seg
                if self.playing:
                    self.samples_into_step += seg
                    self.play_samples += seg
                    frac = self.samples_into_step / max(1.0, cur_len)
                    if self.samples_into_step >= cur_len:
                        self.samples_into_step = 0.0
                        self.abs_step += 1
                        loop = self.loop_steps()
                        if not self.wrap and self.abs_step >= loop:
                            self.playing = False        # offline render done
                        elif trigger:
                            self._trigger_current_step()
            self._pos_frac = min(1.0, max(0.0, frac))

            # master chain
            if self.master_chain:
                bpm = self.project.bpm
                for fx in self.master_chain:
                    if fx.enabled:
                        fx.bpm = bpm
                        out[:, :] = fx.process(out, self.sr)

            # final safety / glue
            np.multiply(out, 0.9 * float(self.master_volume), out=out)
            np.tanh(out, out)
            mpeak = float(np.max(np.abs(out))) if frames else 0.0
            if mpeak > self.master_peak:
                self.master_peak = mpeak
            for k in list(self.channel_peaks):
                self.channel_peaks[k] *= 0.94
            self.master_peak *= 0.94
        return out

    # ------------------------------------------------------------------
    # state for the UI
    # ------------------------------------------------------------------
    _pos_frac = 0.0

    def get_state(self) -> dict:
        with self.lock:
            loop = max(1, self.loop_steps())
            pos = self.abs_step % loop
            return dict(
                playing=self.playing,
                loop_pos=pos,
                loop_pos_float=pos + (self._pos_frac if self.playing else 0.0),
                loop_steps=loop,
                bar=pos // 16 + 1,
                beat=(pos % 16) // 4 + 1,
                tick=pos % 4,
                seconds=self.play_samples / self.sr,
                peaks=dict(self.channel_peaks),
                master_peak=self.master_peak,
                backend=self.audio_backend,
            )


# ---------------------------------------------------------------------------
# Offline rendering / WAV export
# ---------------------------------------------------------------------------
def _clone_project(project: Project) -> Project:
    return Project.from_dict(project.to_dict())


def render_offline(project: Project, mode: str = "song",
                   sr: int = SR) -> np.ndarray:
    """Render the pattern or the whole song to a stereo float32 array."""
    eng = Engine(_clone_project(project), sr=sr, wrap=False)
    eng.mode = mode
    with eng.lock:
        eng.playing = True
        eng._trigger_current_step()          # fire step 0
    chunks = []
    total = eng.loop_steps()
    while eng.playing and eng.abs_step < total:
        chunks.append(eng.process(512))
    eng.playing = False
    tail_blocks = int(_TAIL_SECONDS * sr / 512)
    for _ in range(tail_blocks):
        if not eng.voices:
            break
        chunks.append(eng.process(512, trigger=False))
    return np.concatenate(chunks) if chunks else np.zeros((0, 2), np.float32)


def export_wav(path: str, project: Project, mode: str = "song", sr: int = SR):
    data = render_offline(project, mode, sr)
    pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return len(pcm) / sr
