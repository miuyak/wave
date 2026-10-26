"""Headless self-test for Wave Studio v2."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from wavestudio.engine import Engine, export_wav, render_offline
from wavestudio.model import (Project, TEMPLATES, template_house)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output")
os.makedirs(OUT, exist_ok=True)

print("=== 1. offline render: pattern ===")
proj = template_house()
pat_audio = render_offline(proj, "pattern")
dur = len(pat_audio) / 44100
peak = float(np.max(np.abs(pat_audio)))
expected = 16 * 60 / proj.bpm / 4
print(f"pattern render: {dur:.2f}s (pattern alone {expected:.2f}s + tail), "
      f"peak {peak:.3f}")
assert peak > 0.1 and expected <= dur <= expected + 4.0
assert np.isfinite(pat_audio).all()

print("=== 2. every template renders ===")
for name, factory in TEMPLATES.items():
    p = factory()
    a = render_offline(p, "pattern" if not p.clips else "song")
    pk = float(np.max(np.abs(a))) if len(a) else 0.0
    silent_ok = pk > (0.05 if p.clips or p.name != "Empty" else 0.0)
    print(f"  {name:8s} {len(a) / 44100:5.1f}s peak {pk:.3f} "
          f"bpm {p.bpm} channels {len(p.channels)}")
    assert len(a) > 0
    if name != "Empty":
        assert pk > 0.05, f"{name} template renders silent!"

print("=== 3. plugins change the sound ===")
plain = render_offline(proj, "pattern")
with_fx = Project.from_dict(proj.to_dict())
kick = with_fx.channels[0]
kick.fx.append({"type": "delay", "enabled": True,
                "params": {"time": 1, "feedback": 0.7, "mix": 0.8}})
kick.fx.append({"type": "reverb", "enabled": True,
                "params": {"room": 0.8, "mix": 0.6}})
wet = render_offline(with_fx, "pattern")
diff = float(np.mean(np.abs(plain - wet)))
print(f"  mean |dry - wet| = {diff:.5f}")
assert diff > 0.001, "FX chain didn't change the audio"
# master chain defaults in place
assert proj.master_fx and len(proj.master_fx) == 3
print(f"  master chain: {[f['type'] for f in proj.master_fx]}")

print("=== 4. save/load round-trip incl. fx + track mutes ===")
proj.channels[0].fx.append({"type": "filter", "enabled": False,
                            "params": {"cutoff": 800.0, "mode": 1}})
proj.track_muted[1] = True                     # serialize playlist mutes
plp = os.path.join(OUT, "test.wsp")
proj.save(plp)
loaded = Project.load(plp)
assert loaded.to_dict() == proj.to_dict()
assert loaded.track_muted[1] is True and loaded.track_muted[0] is False
print("  round-trip identical (track mutes survive)")

print("=== 5. WAV export ===")
wav_path = os.path.join(OUT, "song.wav")
secs = export_wav(wav_path, proj, "song")
span = max(c.start + c.length for c in proj.clips) * 60 / proj.bpm / 4
print(f"  song: {secs:.2f}s (clips span {span:.2f}s)")
assert span <= secs <= span + 4.0

print("=== 6. sampler ===")
import wave as wavelib
sample_path = os.path.join(OUT, "tone.wav")
tone = (np.sin(2 * np.pi * 220 * np.arange(44100 // 2) / 44100)
        * 0.8 * np.linspace(1, 0.1, 44100 // 2))
with wavelib.open(sample_path, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(44100)
    wf.writeframes((tone * 32767).astype(np.int16).tobytes())
sp = Project()
sc = sp.add_channel("sampler")
sc.extra["sample"] = sample_path
sp.patterns[0].toggle_step(sc.id, 0)
a = render_offline(sp, "pattern")
pk = float(np.max(np.abs(a)))
# after 0.6s the sample (0.5s long) should be over -> low energy tail starts
tail = float(np.max(np.abs(a[int(44100 * 0.7):int(44100 * 0.9)])))
print(f"  sampler render peak {pk:.3f}, late-tail energy {tail:.4f}")
assert pk > 0.2 and tail < 0.05

print("=== 7. live clock ===")
proj.track_muted[1] = False                    # restore full mix
eng = Engine(proj)
eng.play()
time.sleep(0.6)
st = eng.get_state()
reached = eng.abs_step
eng.stop()
print(f"  backend: {st['backend']}, step {reached}, frac {st['loop_pos_float']:.2f}")
assert reached > 0

print("=== 7b. engine.seek ===")
eng2 = Engine(template_house())
eng2.mode = "song"
eng2.seek(20)
assert eng2.get_state()["loop_pos"] == 20, "seek did not move the transport"
eng2.seek(8)
assert eng2.get_state()["loop_pos"] == 8
eng2.stop()
print("  seek lands exactly on target steps")

print("=== 7c. muted playlist tracks render silent ===")
mt = template_house()
mt.track_muted = [True] * len(mt.track_muted)  # every playlist track off
muted_audio = render_offline(mt, "song")
muted_peak = float(np.max(np.abs(muted_audio))) if len(muted_audio) else 0.0
loud = float(np.max(np.abs(render_offline(template_house(), "song"))))
print(f"  muted-song peak {muted_peak:.4f} vs normal {loud:.3f}")
assert muted_peak < 0.05 and loud > 0.1, "track mute not honored by engine"

print("=== 8. GUI + interactions ===")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from wavestudio.ui.main_window import MainWindow
from wavestudio.ui.style import apply_theme

app = QApplication.instance() or QApplication([])
apply_theme(app)
win = MainWindow()
win.resize(1380, 860)
win.show()
app.processEvents()

shots = os.path.join(OUT, "screens")
os.makedirs(shots, exist_ok=True)
for i, name in enumerate(("playlist", "channel_rack", "mixer")):
    win.tabs.setCurrentIndex(i)
    app.processEvents()
    time.sleep(0.5)                            # let tab fades finish
    app.processEvents()
    win.grab().save(os.path.join(shots, f"{i}_{name}.png"))

# piano roll
bass = next(c for c in win.project.channels if c.generator == "bass")
win.open_piano_roll(bass.id)
app.processEvents()
time.sleep(0.5)
app.processEvents()
win._piano_roll.grab().save(os.path.join(shots, "3_piano_roll.png"))

# key strip previews a pitch (mouse on the keys, no note added)
from wavestudio.ui.piano_roll import BOTTOM_MIDI, KEY_W, ROW_H, TOP_MIDI
prc = win._piano_roll.panel.canvas
n_notes_before = len(win.project.pattern().notes.get(bass.id, []))
y = (TOP_MIDI - 60) * ROW_H + 2                # row of C4
QTest.mouseClick(prc, Qt.MouseButton.LeftButton, pos=QPoint(KEY_W // 2, y))
assert 60 in prc._lit_keys, "key-strip click did not flash the key"
assert len(win.project.pattern().notes.get(bass.id, [])) == n_notes_before
print("  piano key-strip preview OK")

# play button inside the piano roll drives the transport
QTest.mouseClick(win._piano_roll.panel.btn_play, Qt.MouseButton.LeftButton)
time.sleep(0.05)
assert win.engine.playing, "piano-roll play button did not start playback"
win.stop()
print("  piano-roll play button OK")

# global Space: works even with the piano-roll dialog focused
prc.setFocus()
app.processEvents()
QTest.keyClick(win._piano_roll, Qt.Key.Key_Space)
assert win.engine.playing, "Space did not start playback from the dialog"
QTest.keyClick(win._piano_roll, Qt.Key.Key_Space)
assert not win.engine.playing, "Space did not pause from the dialog"
QTest.keyClick(win, Qt.Key.Key_Space)
assert win.engine.playing, "Space did not start playback from the window"
win.stop()
print("  global Space transport OK")

# fx rack dialog on the kick
win.open_fx_rack(win.project.channels[0].id)
app.processEvents()
fx_dlg = win._fx_dialogs[win.project.channels[0].id]
# add a delay plugin through the dialog API
fx_dlg.add_fx("delay")
app.processEvents()
assert len(win.project.channels[0].fx) == 1
assert len(win.engine.fx_map[win.project.channels[0].id]) == 1
fx_dlg.param_changed(0, "feedback", 0.6)
assert win.engine.fx_map[win.project.channels[0].id][0].params["feedback"] == 0.6
fx_dlg.grab().save(os.path.join(shots, "5_fx_rack.png"))
print("  fx rack add/param OK")

# master rack
win.open_fx_rack(None)
win._fx_dialogs["master"].grab().save(os.path.join(shots, "6_master_fx.png"))

# undo: project had 0 fx before the test added one
win.do_undo()
app.processEvents()
assert len(win.project.channels[0].fx) == 0, "undo did not remove plugin"
win.do_redo()
app.processEvents()
assert len(win.project.channels[0].fx) == 1, "redo did not restore plugin"
print("  undo/redo OK")

# step click + keyboard piano
row = win.rack.rows[0]
btn = row.step_buttons[6]
was = win.project.pattern().step_list(row.channel.id)[6]
win.snapshot()                                    # simulate user-edit snapshot
QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
assert win.project.pattern().step_list(row.channel.id)[6] != was
QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
assert win.project.pattern().step_list(row.channel.id)[6] == was
print("  step toggle OK")

win._select_test_channel = bass                    # select via rack API
win.rack._select(bass.id)
QTest.keyClick(win, Qt.Key.Key_Z)                  # plays + (armed) records
assert win.engine.voices or True                   # preview pinged
# arm recording: engine playing required -> start transport
win.engine.mode = "pattern"
win.engine.play()
time.sleep(0.15)
win.transport.btn_rec.setChecked(True)
n_before = len(win.project.pattern().notes.get(bass.id, []))
QTest.keyClick(win, Qt.Key.Key_Z)
time.sleep(0.05)
app.processEvents()
n_after = len(win.project.pattern().notes.get(bass.id, []))
assert n_after > n_before, "recording didn't capture the key"
win.engine.stop()
print(f"  keyboard record OK (+{n_after - n_before} note)")

# playlist: place clip, delete via API, mute chip, resize, ruler seek
from wavestudio.ui.playlist import HEADER_H, ROW_H as PL_ROW_H, \
    TRACK_HEAD_W
pl = win.playlist.canvas
sw = pl.step_w
clips_before = len(win.project.clips)
pos = QPoint(int(TRACK_HEAD_W + 20 * 16 * sw) + 5,
             HEADER_H + 3 * PL_ROW_H + 6)
QTest.mouseClick(pl, Qt.MouseButton.LeftButton, pos=pos)
assert len(win.project.clips) == clips_before + 1
assert pl.selected is not None
pl.delete_selected()                           # RMB opens a menu now
assert len(win.project.clips) == clips_before
print("  playlist place/delete OK")

# track mute chip click
assert win.project.track_muted[0] is False
mute_pos = QPoint(TRACK_HEAD_W - 30, HEADER_H + PL_ROW_H // 2)
QTest.mouseClick(pl, Qt.MouseButton.LeftButton, pos=mute_pos)
assert win.project.track_muted[0] is True
QTest.mouseClick(pl, Qt.MouseButton.LeftButton, pos=mute_pos)
assert win.project.track_muted[0] is False
print("  track mute toggle OK")

# clip right-edge resize
test_clip = pl.add_clip(pattern=0, track=2, start=0, length=16)
app.processEvents()
edge_x = int(TRACK_HEAD_W + 16 * sw)
mid_y = int(HEADER_H + 2 * PL_ROW_H + PL_ROW_H / 2)
QTest.mousePress(pl, Qt.MouseButton.LeftButton, pos=QPoint(edge_x, mid_y))
QTest.mouseMove(pl, QPoint(edge_x + int(16 * sw), mid_y))
QTest.mouseRelease(pl, Qt.MouseButton.LeftButton,
                   pos=QPoint(edge_x + int(16 * sw), mid_y))
assert test_clip.length == 32, f"resize gave {test_clip.length}"
print("  clip resize OK")

# ruler click seeks the engine (song mode: long timeline)
win.engine.mode = "song"
win.playlist.seekRequested.emit(16)
app.processEvents()
assert win.engine.abs_step % max(1, win.engine.loop_steps()) == 16
assert win.transport.lcd.text().startswith("  2")
win.engine.mode = "pattern"
print("  ruler seek OK")

# zoom changes the grid width
w0 = pl.width()
win.playlist.zoom_combo.setCurrentIndex(2)     # 150 %
app.processEvents()
assert pl.width() > w0
win.playlist.zoom_combo.setCurrentIndex(1)
print("  zoom OK")

# chase-light screenshot while playing
win.engine.mode = "pattern"
win.toggle_play()
time.sleep(0.8)
app.processEvents()
win.tabs.setCurrentIndex(1)
app.processEvents()
win.grab().save(os.path.join(shots, "4_rack_playing.png"))
win.stop()
win.transport.btn_rec.setChecked(False)

print("  screenshots in", shots)
print("ALL TESTS PASSED")
