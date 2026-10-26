"""Data model for Wave Studio.

Pure Python, no Qt/audio imports so it can be cloned, saved and unit tested
independently of the UI or the audio engine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

STEPS_PER_BAR = 16          # 16 sixteenth-notes per bar (4/4)
NUM_PATTERNS = 16           # FL-style numbered pattern slots
PLAYLIST_TRACKS = 5
PLAYLIST_BARS = 64

# ---------------------------------------------------------------------------
# Available sound generators (instruments)
# ---------------------------------------------------------------------------
GENERATORS = {
    # drums  ---------------------------------------------------------------
    "kick":    {"name": "Kick",          "kind": "drum",   "color": "#ef6b6b"},
    "kick808": {"name": "808 Kick",      "kind": "drum",   "color": "#fb7185"},
    "snare":   {"name": "Snare",         "kind": "drum",   "color": "#f5b97d"},
    "clap":    {"name": "Clap",          "kind": "drum",   "color": "#f39c7a"},
    "chat":    {"name": "HiHat Closed",  "kind": "drum",   "color": "#7dd3fc"},
    "ohat":    {"name": "HiHat Open",    "kind": "drum",   "color": "#38bdf8"},
    "crash":   {"name": "Crash",         "kind": "drum",   "color": "#fde68a"},
    "tom":     {"name": "Tom",           "kind": "drum",   "color": "#c4b5fd"},
    "rim":     {"name": "Rimshot",       "kind": "drum",   "color": "#d6a87f"},
    "shaker":  {"name": "Shaker",        "kind": "drum",   "color": "#cbd5e1"},
    "cowbell": {"name": "Cowbell",       "kind": "drum",   "color": "#fcd34d"},
    "riser":   {"name": "Noise Riser",   "kind": "drum",   "color": "#fda4af"},
    # sampler ---------------------------------------------------------------
    "sampler": {"name": "Sampler",       "kind": "sample", "color": "#94a3b8"},
    # melodic synths ----------------------------------------------------------
    "bass":    {"name": "Bass Synth",    "kind": "synth",  "color": "#86efac"},
    "acid":    {"name": "Acid Bass",     "kind": "synth",  "color": "#bef264"},
    "pluck":   {"name": "Pluck Synth",   "kind": "synth",  "color": "#93c5fd"},
    "keys":    {"name": "E-Piano",       "kind": "synth",  "color": "#c4b5fd"},
    "lead":    {"name": "Lead Synth",    "kind": "synth",  "color": "#f0abfc"},
    "fmbell":  {"name": "FM Bell",       "kind": "synth",  "color": "#a5f3fc"},
    "supersaw": {"name": "Supersaw",     "kind": "synth",  "color": "#a78bfa"},
}
DRUM_GENERATORS = [g for g in GENERATORS if GENERATORS[g]["kind"] == "drum"]
SAMPLE_GENERATORS = [g for g in GENERATORS if GENERATORS[g]["kind"] == "sample"]
SYNTH_GENERATORS = [g for g in GENERATORS if GENERATORS[g]["kind"] == "synth"]


# ---------------------------------------------------------------------------
# Basic data structures
# ---------------------------------------------------------------------------
@dataclass
class Note:
    start: int              # position in steps (16th notes)
    length: int             # duration in steps
    pitch: int              # MIDI note number
    velocity: float = 0.8

    def to_dict(self):
        return dict(start=self.start, length=self.length,
                    pitch=self.pitch, velocity=self.velocity)

    @staticmethod
    def from_dict(d):
        return Note(int(d["start"]), int(d["length"]),
                    int(d["pitch"]), float(d.get("velocity", 0.8)))


@dataclass
class Channel:
    id: int
    generator: str
    name: str = ""
    volume: float = 0.8
    pan: float = 0.0        # -1 (left) .. 1 (right)
    mute: bool = False
    solo: bool = False
    fx: list = field(default_factory=list)    # [{type, enabled, params}]
    extra: dict = field(default_factory=dict)  # e.g. {"sample": "/abs/x.wav"}

    @property
    def kind(self):
        return GENERATORS[self.generator]["kind"]

    @property
    def color(self):
        return GENERATORS[self.generator]["color"]

    def to_dict(self):
        return dict(id=self.id, generator=self.generator, name=self.name,
                    volume=self.volume, pan=self.pan,
                    mute=self.mute, solo=self.solo,
                    fx=[dict(f, params=dict(f.get("params", {}))) for f in self.fx],
                    extra=dict(self.extra))

    @staticmethod
    def from_dict(d):
        return Channel(int(d["id"]), d["generator"], d.get("name", ""),
                       float(d.get("volume", 0.8)), float(d.get("pan", 0.0)),
                       bool(d.get("mute", False)), bool(d.get("solo", False)),
                       list(d.get("fx", [])), dict(d.get("extra", {})))


@dataclass
class Pattern:
    name: str = "Pattern"
    length: int = STEPS_PER_BAR
    steps: dict = field(default_factory=dict)   # channel_id -> [bool] * length
    notes: dict = field(default_factory=dict)   # channel_id -> [Note]

    def set_length(self, n: int):
        n = max(4, min(64, int(n)))
        self.length = n
        for cid, lst in self.steps.items():
            if len(lst) < n:
                lst.extend([False] * (n - len(lst)))
            elif len(lst) > n:
                del lst[n:]

    def step_list(self, channel_id: int):
        lst = self.steps.get(channel_id)
        if lst is None or len(lst) != self.length:
            lst = [False] * self.length
            self.steps[channel_id] = lst
        return lst

    def toggle_step(self, channel_id: int, index: int) -> bool:
        lst = self.step_list(channel_id)
        if 0 <= index < self.length:
            lst[index] = not lst[index]
            return lst[index]
        return False

    def note_list(self, channel_id: int):
        return self.notes.setdefault(channel_id, [])

    def add_note(self, channel_id: int, note: Note):
        self.note_list(channel_id).append(note)

    def remove_note(self, channel_id: int, note: Note):
        lst = self.notes.get(channel_id, [])
        if note in lst:
            lst.remove(note)

    def clear(self):
        self.steps.clear()
        self.notes.clear()

    def to_dict(self):
        return dict(
            name=self.name, length=self.length,
            steps={str(k): [bool(b) for b in v] for k, v in self.steps.items()},
            notes={str(k): [n.to_dict() for n in v]
                   for k, v in self.notes.items()},
        )

    @staticmethod
    def from_dict(d):
        p = Pattern(d.get("name", "Pattern"), int(d.get("length", STEPS_PER_BAR)))
        p.steps = {int(k): [bool(b) for b in v]
                   for k, v in d.get("steps", {}).items()}
        p.notes = {int(k): [Note.from_dict(x) for x in v]
                   for k, v in d.get("notes", {}).items()}
        return p


@dataclass
class Clip:
    pattern: int = 0        # index into Project.patterns
    track: int = 0
    start: int = 0          # absolute step on the song timeline
    length: int = STEPS_PER_BAR

    def to_dict(self):
        return dict(pattern=self.pattern, track=self.track,
                    start=self.start, length=self.length)

    @staticmethod
    def from_dict(d):
        return Clip(int(d["pattern"]), int(d["track"]),
                    int(d["start"]), int(d["length"]))


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class Project:
    FILE_EXT = ".wsp"       # Wave Studio Project (JSON inside)

    def __init__(self):
        self.name = "Untitled"
        self.bpm = 126.0
        self.swing = 0.0            # 0 .. 0.6
        self.master_volume = 0.85
        self.current_pattern = 0
        self.channels: list[Channel] = []
        self.patterns = [Pattern(name=f"Pattern {i + 1}")
                         for i in range(NUM_PATTERNS)]
        self.clips: list[Clip] = []
        self.track_muted: list[bool] = [False] * PLAYLIST_TRACKS
        self.master_fx: list[dict] = [
            {"type": "compressor", "enabled": True,
             "params": {"threshold": -14.0, "ratio": 2.5, "makeup": 3.0}},
            {"type": "width", "enabled": True, "params": {"width": 1.05}},
            {"type": "limiter", "enabled": True, "params": {"ceiling": -1.5}},
        ]
        self._next_channel_id = 1

    # ---- channels ---------------------------------------------------------
    def add_channel(self, generator: str) -> Channel:
        ch = Channel(id=self._next_channel_id, generator=generator,
                     name=GENERATORS[generator]["name"])
        self._next_channel_id += 1
        self.channels.append(ch)
        return ch

    def remove_channel(self, channel_id: int):
        self.channels = [c for c in self.channels if c.id != channel_id]
        for pat in self.patterns:
            pat.steps.pop(channel_id, None)
            pat.notes.pop(channel_id, None)

    def channel(self, channel_id: int):
        for c in self.channels:
            if c.id == channel_id:
                return c
        return None

    def pattern(self) -> Pattern:
        return self.patterns[self.current_pattern]

    # ---- serialization ----------------------------------------------------
    def to_dict(self):
        return dict(
            name=self.name, bpm=self.bpm, swing=self.swing,
            master_volume=self.master_volume,
            current_pattern=self.current_pattern,
            next_channel_id=self._next_channel_id,
            channels=[c.to_dict() for c in self.channels],
            patterns=[p.to_dict() for p in self.patterns],
            clips=[c.to_dict() for c in self.clips],
            track_muted=[bool(b) for b in self.track_muted],
            master_fx=[dict(f, params=dict(f.get("params", {})))
                       for f in self.master_fx],
        )

    @staticmethod
    def from_dict(d):
        pr = Project()
        pr.name = d.get("name", "Untitled")
        pr.bpm = float(d.get("bpm", 126.0))
        pr.swing = float(d.get("swing", 0.0))
        pr.master_volume = float(d.get("master_volume", 0.85))
        pr.current_pattern = int(d.get("current_pattern", 0))
        pr.channels = [Channel.from_dict(x) for x in d.get("channels", [])]
        pats = [Pattern.from_dict(x) for x in d.get("patterns", [])]
        if len(pats) < NUM_PATTERNS:
            pats += [Pattern(name=f"Pattern {i + 1}")
                     for i in range(len(pats), NUM_PATTERNS)]
        pr.patterns = pats[:NUM_PATTERNS]
        pr.clips = [Clip.from_dict(x) for x in d.get("clips", [])]
        tm = [bool(b) for b in d.get("track_muted", [])][:PLAYLIST_TRACKS]
        tm += [False] * (PLAYLIST_TRACKS - len(tm))
        pr.track_muted = tm
        if "master_fx" in d:
            pr.master_fx = list(d["master_fx"])
        pr._next_channel_id = int(d.get(
            "next_channel_id",
            (max((c.id for c in pr.channels), default=0) + 1)))
        return pr

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1)

    @staticmethod
    def load(path: str) -> "Project":
        with open(path, "r", encoding="utf-8") as fh:
            return Project.from_dict(json.load(fh))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def template_empty() -> Project:
    """Minimal drum rack."""
    pr = Project()
    pr.name = "New project"
    for gen in ("kick", "snare", "clap", "chat", "ohat"):
        pr.add_channel(gen)
    pr.bpm = 120.0
    return pr


def template_house() -> Project:
    """Four-on-the-floor groove with a rolling bassline — the welcome song."""
    pr = Project()
    pr.name = "House"
    pr.bpm = 126.0

    kick = pr.add_channel("kick")
    snare = pr.add_channel("snare")
    clap = pr.add_channel("clap")
    chat = pr.add_channel("chat")
    ohat = pr.add_channel("ohat")
    crash = pr.add_channel("crash")
    bass = pr.add_channel("bass")
    keys = pr.add_channel("keys")

    p1 = pr.patterns[0]
    p1.name = "Main groove"
    for s in (0, 4, 8, 12):
        p1.toggle_step(kick.id, s)
    for s in (4, 12):
        p1.toggle_step(snare.id, s)
    p1.toggle_step(clap.id, 12)
    for s in (2, 6, 10, 14):
        p1.toggle_step(chat.id, s)
    p1.toggle_step(ohat.id, 14)
    p1.toggle_step(crash.id, 0)
    for start, pitch in ((0, 33), (2, 33), (4, 36), (6, 33),
                         (8, 33), (10, 36), (12, 31), (14, 33)):
        p1.add_note(bass.id, Note(start, 2, pitch, 0.9))
    for pitch in (57, 60, 64):
        p1.add_note(keys.id, Note(0, 8, pitch, 0.55))
    for pitch in (55, 59, 62):
        p1.add_note(keys.id, Note(8, 8, pitch, 0.55))

    p2 = pr.patterns[1]
    p2.name = "Variation"
    for s in (0, 7, 8, 12):
        p2.toggle_step(kick.id, s)
    for s in (4, 12):
        p2.toggle_step(snare.id, s)
    for s in (0, 2, 4, 6, 8, 10, 12, 14):
        p2.toggle_step(chat.id, s)
    p2.toggle_step(ohat.id, 10)
    for start, pitch in ((0, 33), (3, 33), (6, 36), (8, 38),
                         (11, 36), (14, 31)):
        p2.add_note(bass.id, Note(start, 2, pitch, 0.95))
    for pitch in (57, 60, 64):
        p2.add_note(keys.id, Note(0, 16, pitch, 0.5))

    pr.clips = [
        Clip(pattern=0, track=0, start=0,  length=16),
        Clip(pattern=0, track=0, start=16, length=16),
        Clip(pattern=1, track=1, start=16, length=16),
        Clip(pattern=0, track=0, start=32, length=16),
        Clip(pattern=1, track=1, start=48, length=16),
    ]
    return pr


def template_trap() -> Project:
    """Half-time trap: 808s, snappy hats with rolls, sparse keys."""
    pr = Project()
    pr.name = "Trap"
    pr.bpm = 145.0
    kick = pr.add_channel("kick808")
    clap = pr.add_channel("clap")
    chat = pr.add_channel("chat")
    ohat = pr.add_channel("ohat")
    keys = pr.add_channel("fmbell")
    lead = pr.add_channel("lead")

    p1 = pr.patterns[0]
    p1.name = "Trap A"
    p1.set_length(32)                     # two bars
    for s in (0, 11, 16, 27):
        p1.toggle_step(kick.id, s)
    for s in (8, 24):
        p1.toggle_step(clap.id, s)
    for s in range(0, 32, 2):
        p1.toggle_step(chat.id, s)
    for s in (14, 15, 30, 31):            # rolls
        p1.toggle_step(chat.id, s)
    p1.toggle_step(ohat.id, 26)
    for pitch in (48, 51, 55):
        p1.add_note(keys.id, Note(0, 30, pitch, 0.4))
    for start, pitch in ((4, 60), (6, 63), (12, 62), (20, 60), (28, 58)):
        p1.add_note(lead.id, Note(start, 1, pitch, 0.5))

    p2 = pr.patterns[1]
    p2.name = "Trap B"
    p2.set_length(32)
    for s in (0, 6, 11, 16, 22, 27):
        p2.toggle_step(kick.id, s)
    for s in (8, 24):
        p2.toggle_step(clap.id, s)
    for s in range(0, 32, 2):
        p2.toggle_step(chat.id, s)
    for s in (7, 15, 23, 29, 30, 31):
        p2.toggle_step(chat.id, s)
    for pitch in (46, 49, 53):
        p2.add_note(keys.id, Note(0, 30, pitch, 0.42))

    pr.clips = [
        Clip(pattern=0, track=0, start=0,  length=32),
        Clip(pattern=0, track=0, start=32, length=32),
        Clip(pattern=1, track=1, start=32, length=32),
    ]
    return pr


def template_techno() -> Project:
    """Driving techno: rumble kick, offbeat hats, acid line."""
    pr = Project()
    pr.name = "Techno"
    pr.bpm = 132.0
    kick = pr.add_channel("kick")
    chat = pr.add_channel("chat")
    ohat = pr.add_channel("ohat")
    clap = pr.add_channel("clap")
    rim = pr.add_channel("rim")
    acid = pr.add_channel("acid")
    riser = pr.add_channel("riser")

    p1 = pr.patterns[0]
    p1.name = "Drive"
    for s in (0, 4, 8, 12):
        p1.toggle_step(kick.id, s)
    for s in (2, 6, 10, 14):
        p1.toggle_step(chat.id, s)
    p1.toggle_step(ohat.id, 14)
    for s in (8,):
        p1.toggle_step(clap.id, s)
    for s in (3, 7, 11, 15):
        p1.toggle_step(rim.id, s)
    seq = (33, 33, 45, 33, 36, 33, 45, 48)
    for i, pitch in enumerate(seq):
        p1.add_note(acid.id, Note(i * 2, 1, pitch, 0.85))

    p2 = pr.patterns[1]
    p2.name = "Lift"
    for s in (0, 4, 8, 12):
        p2.toggle_step(kick.id, s)
    for s in range(0, 16, 2):
        p2.toggle_step(chat.id, s)
    p2.toggle_step(riser.id, 0)
    seq = (33, 33, 45, 33, 38, 33, 45, 50)
    for i, pitch in enumerate(seq):
        p2.add_note(acid.id, Note(i * 2, 1, pitch, 0.9))

    pr.clips = [
        Clip(pattern=0, track=0, start=0,  length=16),
        Clip(pattern=0, track=0, start=16, length=16),
        Clip(pattern=0, track=0, start=32, length=16),
        Clip(pattern=1, track=1, start=48, length=16),
    ]
    return pr


TEMPLATES = {
    "Empty": template_empty,
    "House": template_house,
    "Trap": template_trap,
    "Techno": template_techno,
}

# default project on startup
new_project = template_house
demo_project = template_house          # backwards compat for tools/tests
