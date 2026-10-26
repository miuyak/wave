"""Main window: transport + tabs (Playlist / Channel Rack / Mixer), browser
dock, undo/redo, keyboard piano with live recording, templates."""
from __future__ import annotations

import os

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit,
                               QSpinBox, QTabWidget, QTextEdit, QWidget)

from .icons import _pixmap
from .style import ACCENT_HI, TEXT

from .. import APP_NAME, __version__
from ..engine import Engine, export_wav
from ..model import (Note, Project, STEPS_PER_BAR, new_project)
from ..model import TEMPLATES
from .anim import fade_in, window_fade_in
from .browser import BrowserDock
from .channel_rack import ChannelRack
from .fx_rack import FXRackDialog
from .mixer import MixerPanel
from .piano_roll import PianoRollDialog
from .playlist import PlaylistPanel
from .transport import TransportBar

PIANO_KEYS = {
    "z": 0, "s": 1, "x": 2, "d": 3, "c": 4, "v": 5, "g": 6, "b": 7,
    "h": 8, "n": 9, "j": 10, "m": 11, ",": 12,
    "q": 12, "2": 13, "w": 14, "3": 15, "e": 16, "r": 17, "5": 18,
    "t": 19, "6": 20, "y": 21, "7": 22, "u": 23, "i": 24,
}
BASE_OCTAVE = 60                         # C4


class UndoStack:
    """Two-stack undo. ``snapshot`` is called *before* each mutation and stores
    the pre-edit state; undo/redo swap the current state across the stacks."""

    def __init__(self, limit=200):
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._limit = limit

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def push(self, data: dict):
        self._undo.append(data)
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self, current: dict):
        if self._undo:
            self._redo.append(current)
            return self._undo.pop()
        return None

    def redo(self, current: dict):
        if self._redo:
            self._undo.append(current)
            return self._redo.pop()
        return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.project = new_project()
        self.engine = Engine(self.project)
        self._file_path = None
        self._piano_roll: PianoRollDialog | None = None
        self._fx_dialogs: dict = {}
        self.undo_stack = UndoStack()
        self.recording = False
        self._rec_snapshot_done = False
        self.octave = 0

        # ---- central layout -------------------------------------------------
        self.transport = TransportBar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar_wrap())

        self.tabs = QTabWidget()
        self.playlist = PlaylistPanel(self.project, self.engine)
        self.rack = ChannelRack(self.project, self.engine)
        self.mixer = MixerPanel(self.project, self.engine)
        self.tabs.addTab(self.playlist, "Playlist")
        self.tabs.addTab(self.rack, "Channel Rack")
        self.tabs.addTab(self.mixer, "Mixer")
        self.setCentralWidget(self.tabs)
        self.tabs.setCurrentIndex(1)          # start on the channel rack
        self.tabs.currentChanged.connect(self._tab_faded)

        # ---- browser dock ----------------------------------------------------
        self.browser = BrowserDock(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.browser)
        self.browser.addChannel.connect(self._browser_add_channel)

        self._wire_transport()
        self._wire_rack()
        self.playlist.clipsChanged.connect(self.refresh_ui)
        self.playlist.canvas.aboutToEdit.connect(self.snapshot)
        self.playlist.seekRequested.connect(self._playlist_seek)
        self.playlist.openPattern.connect(self._open_pattern)
        self.mixer.requestFx.connect(self.open_fx_rack)
        self._build_menus()
        self._build_shortcuts()
        self._build_status_facts()

        # ---- UI poll timer ---------------------------------------------------
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

        self.statusBar().showMessage(
            "Space — play · Z X C V B — keys · REC arms recording", 8000)

    # ----------------------------------------------------------------------
    # startup animation
    # ----------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_greeted", False):
            self._greeted = True
            window_fade_in(self)
            fade_in(self.tabs, 350, 0.0, 1.0)

    def _tab_faded(self, idx):
        fade_in(self.tabs.widget(idx), 180, 0.35, 1.0)
        hints = ("Click empty space to place the current pattern · click the "
                 "ruler to seek · drag a clip's right edge to resize · "
                 "right-click a clip for its menu · SONG mode plays this",
                 "Click steps to toggle · click a channel name for Piano Roll · "
                 "right-click for plugins/rename/delete",
                 "FX opens the plugin rack · master bus is on the right")
        self.statusBar().showMessage(hints[idx], 6000)

    # ----------------------------------------------------------------------
    def _toolbar_wrap(self):
        from PySide6.QtWidgets import QToolBar
        tb = QToolBar("Transport", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.addWidget(self.transport)
        return tb

    def _wire_transport(self):
        t = self.transport
        t.playClicked.connect(self.toggle_play)
        t.stopClicked.connect(self.stop)
        t.recordToggled.connect(self._record_toggled)
        t.modeChanged.connect(lambda m: setattr(self.engine, "mode", m))
        t.bpmChanged.connect(lambda v: setattr(self.project, "bpm", v))
        t.swingChanged.connect(lambda v: setattr(self.project, "swing", v))
        t.masterChanged.connect(self._master_changed)
        t.metronomeToggled.connect(lambda on: setattr(self.engine, "metronome", on))

    def _wire_rack(self):
        self.rack.requestPianoRoll.connect(self.open_piano_roll)
        self.rack.requestFx.connect(self.open_fx_rack)
        self.rack.structureChanged.connect(self.refresh_ui)
        self.rack.patternSwitched.connect(self.refresh_ui)
        self.rack.editMade.connect(self.snapshot)

    def _master_changed(self, v):
        self.engine.master_volume = v
        self.project.master_volume = v

    # ----------------------------------------------------------------------
    # undo / redo
    # ----------------------------------------------------------------------
    def snapshot(self):
        self.undo_stack.push(self.project.to_dict())
        self.act_undo.setEnabled(True)
        self.act_redo.setEnabled(self.undo_stack.can_redo())

    def do_undo(self):
        data = self.undo_stack.undo(self.project.to_dict())
        if data is not None:
            self._restore(data)
            self.statusBar().showMessage("Undo", 1500)
        self._sync_undo_actions()

    def do_redo(self):
        data = self.undo_stack.redo(self.project.to_dict())
        if data is not None:
            self._restore(data)
            self.statusBar().showMessage("Redo", 1500)
        self._sync_undo_actions()

    def _sync_undo_actions(self):
        self.act_undo.setEnabled(self.undo_stack.can_undo())
        self.act_redo.setEnabled(self.undo_stack.can_redo())

    def _restore(self, data: dict):
        self.project = Project.from_dict(data)
        self.engine.set_project(self.project)
        self._reload_panels()

    # ----------------------------------------------------------------------
    # transport controls
    # ----------------------------------------------------------------------
    def toggle_play(self):
        self.engine.toggle_pause()
        state = self.engine.get_state()
        if self.engine.audio_backend.startswith("silent") and not getattr(
                self, "_warned_silent", False):
            self._warned_silent = True
            self.statusBar().showMessage(
                f"No audio device found — running on a silent clock "
                f"({state['backend']}). WAV export still works.", 10000)
        elif self.engine.audio_backend == "sounddevice":
            self.statusBar().showMessage("Audio: sounddevice", 3000)

    def stop(self):
        self.engine.stop()
        self._rec_snapshot_done = False

    def _record_toggled(self, on: bool):
        self.recording = on
        self._rec_snapshot_done = False
        if on:
            self.statusBar().showMessage(
                "Recording armed — play, then tap Z X C V B … to capture notes",
                6000)

    # ----------------------------------------------------------------------
    # piano roll / fx dialogs
    # ----------------------------------------------------------------------
    def open_piano_roll(self, channel_id: int):
        ch = self.project.channel(channel_id)
        if ch is None:
            return
        if self._piano_roll is None:
            self._piano_roll = PianoRollDialog(self.project, self.engine, self)
            self._piano_roll.notesChanged.connect(self.refresh_ui)
            self._piano_roll.aboutToEdit.connect(self.snapshot)
            self._piano_roll.requestPlayPause.connect(self.toggle_play)
            self._piano_roll.finished.connect(self._piano_roll_closed)
        self._piano_roll.set_channel(ch)
        self._piano_roll.show()
        fade_in(self._piano_roll.panel.canvas, 160, 0.4, 1.0)
        self._piano_roll.raise_()
        self._piano_roll.activateWindow()

    def _piano_roll_closed(self, _res):
        self._piano_roll = None

    def open_fx_rack(self, target):
        """target: channel id (int) or None for the master bus."""
        if target is not None and self.project.channel(target) is None:
            return
        key = target if target is not None else "master"
        dlg = self._fx_dialogs.get(key)
        if dlg is None:
            if target is None:
                title = "Master plugins"
            else:
                title = f"Plugins — {self.project.channel(target).name}"
            dlg = FXRackDialog(self.project, self.engine, target, title, self)
            dlg.structureChanged.connect(self.snapshot)
            dlg.structureChanged.connect(self.refresh_ui)
            dlg.finished.connect(lambda _r, k=key: self._fx_dialogs.pop(k, None))
            self._fx_dialogs[key] = dlg
            dlg.show()
        else:
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    # ----------------------------------------------------------------------
    # menus & shortcuts
    # ----------------------------------------------------------------------
    def _build_menus(self):
        m = self.menuBar().addMenu("&File")

        new_menu = m.addMenu("&New project")
        for name, fn in TEMPLATES.items():
            act = QAction(name, self)
            act.triggered.connect(lambda _=False, f=fn: self.new_from(f, name))
            new_menu.addAction(act)

        act = QAction("&Open…", self, shortcut="Ctrl+O")
        act.triggered.connect(self.open_project)
        m.addAction(act)
        act = QAction("&Save", self, shortcut="Ctrl+S")
        act.triggered.connect(self.save_project)
        m.addAction(act)
        act = QAction("Save &as…", self, shortcut="Ctrl+Shift+S")
        act.triggered.connect(lambda: self.save_project(force_dialog=True))
        m.addAction(act)
        m.addSeparator()
        act = QAction("Export pattern as &WAV…", self, shortcut="Ctrl+E")
        act.triggered.connect(lambda: self.export("pattern"))
        m.addAction(act)
        act = QAction("Export song as WAV…", self, shortcut="Ctrl+Shift+E")
        act.triggered.connect(lambda: self.export("song"))
        m.addAction(act)
        m.addSeparator()
        act = QAction("&Quit", self, shortcut="Ctrl+Q")
        act.triggered.connect(self.close)
        m.addAction(act)

        e = self.menuBar().addMenu("&Edit")
        self.act_undo = QAction("&Undo", self, shortcut="Ctrl+Z")
        self.act_undo.triggered.connect(self.do_undo)
        e.addAction(self.act_undo)
        self.act_redo = QAction("&Redo", self, shortcut="Ctrl+Shift+Z")
        self.act_redo.triggered.connect(self.do_redo)
        e.addAction(self.act_redo)
        e.addSeparator()
        act = QAction("Master plugins…", self, shortcut="Ctrl+M")
        act.triggered.connect(lambda: self.open_fx_rack(None))
        e.addAction(act)

        v = self.menuBar().addMenu("&View")
        for i, name in enumerate(("Playlist", "Channel Rack", "Mixer")):
            act = QAction(name, self, shortcut=f"Ctrl+{i + 1}")
            act.triggered.connect(lambda _=False, idx=i:
                                  self.tabs.setCurrentIndex(idx))
            v.addAction(act)
        v.addSeparator()
        act = QAction("Browser", self, shortcut="Ctrl+B")
        act.setCheckable(True)
        act.setChecked(True)
        act.toggled.connect(self.browser.setVisible)
        v.addAction(act)
        act = QAction("Fullscreen", self, shortcut="F11")
        act.triggered.connect(self.toggle_fullscreen)
        v.addAction(act)

        # top-left corner logo, next to the menus
        logo = QWidget(self)
        logo.setStyleSheet("background:transparent;")
        lh = QHBoxLayout(logo)
        lh.setContentsMargins(10, 0, 14, 0)
        lh.setSpacing(7)
        pm_label = QLabel()
        pm = _pixmap("note", 36, QColor(ACCENT_HI))
        pm_label.setPixmap(pm.scaled(18, 18,
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        pm_label.setStyleSheet("background:transparent;")
        name = QLabel(f"<span style='color:{TEXT}; font-weight:800;'>Wave</span>"
                      f" <span style='color:{ACCENT_HI}; font-weight:800;'>"
                      "Studio</span>")
        name.setStyleSheet("background:transparent; font-size:13px;")
        lh.addWidget(pm_label)
        lh.addWidget(name)
        self.menuBar().setCornerWidget(logo, Qt.Corner.TopLeftCorner)

        helpm = self.menuBar().addMenu("&Help")
        act = QAction("&About Wave Studio", self)
        act.triggered.connect(self.about)
        helpm.addAction(act)

    def _build_shortcuts(self):
        # Global Space handling: an application-level event filter so Space
        # toggles play even while a piano-roll / FX dialog has focus, where a
        # WindowShortcut would be dead. Skip when typing in text fields or
        # while a modal dialog (save box, message box) is up.
        QApplication.instance().installEventFilter(self)
        sc2 = QShortcut(QKeySequence("Ctrl+Y"), self)
        sc2.activated.connect(self.do_redo)
        self.sc_full = QShortcut(QKeySequence(Qt.Key.Key_F11), self)
        self.sc_full.setContext(Qt.ShortcutContext.WindowShortcut)
        self.sc_full.activated.connect(self.toggle_fullscreen)

    def eventFilter(self, obj, event):       # noqa: N802
        if event.type() == QEvent.Type.KeyPress and \
                event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            fw = QApplication.focusWidget()
            if isinstance(fw, (QLineEdit, QSpinBox, QDoubleSpinBox,
                               QComboBox, QTextEdit, QPlainTextEdit)) or \
                    QApplication.activeModalWidget() is not None:
                return super().eventFilter(obj, event)
            self.toggle_play()
            return True
        return super().eventFilter(obj, event)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------------
    # playlists hooks
    # ------------------------------------------------------------------
    def _playlist_seek(self, step: int):
        self.engine.seek(step)
        state = self.engine.get_state()
        self.transport.set_position(state["bar"], state["beat"],
                                    state["tick"], state["seconds"])
        self.statusBar().showMessage(f"Seeked to bar {state['bar']}", 1200)

    def _open_pattern(self, pattern_idx: int):
        with self.engine.lock:
            self.project.current_pattern = pattern_idx
        self.tabs.setCurrentIndex(1)          # channel rack
        self.rack.refresh_rows()
        self.refresh_ui()
        self.statusBar().showMessage(
            f"Editing P{pattern_idx + 1} · "
            f"{self.project.patterns[pattern_idx].name}", 2500)

    def _build_status_facts(self):
        self.status_facts = QLabel("")
        self.status_facts.setStyleSheet(
            "color:#5c6373; font-family:'SF Mono','Consolas',monospace;"
            " padding-right:10px;")
        self.statusBar().addPermanentWidget(self.status_facts)
        self._update_status_facts(self.engine.get_state())

    def _update_status_facts(self, state):
        mode = "SONG" if self.engine.mode == "song" else "PAT"
        backend = "sounddevice" if self.engine.audio_backend == "sounddevice" \
            else ("silent clock"
                  if self.engine.audio_backend.startswith("silent")
                  else self.engine.audio_backend)
        oct_txt = f"{self.octave:+d}"
        self.status_facts.setText(f"{mode}  ·  {backend}  ·  Oct {oct_txt}")

    # ----------------------------------------------------------------------
    # file actions
    # ----------------------------------------------------------------------
    def new_from(self, factory, name: str):
        if not self._confirm_discard():
            return
        self.engine.stop()
        self.project = factory()
        self.project.name = name if name != "Empty" else "New project"
        self._file_path = None
        self.undo_stack.clear()
        self._sync_undo_actions()
        self._reload_into_ui()

    def open_project(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open project", "",
            f"Wave Studio project (*{Project.FILE_EXT} *.plp)")
        if not path:
            return
        try:
            self.engine.stop()
            self.project = Project.load(path)
            self._file_path = path
            self.undo_stack.clear()
            self._sync_undo_actions()
            self._reload_into_ui()
        except Exception as exc:  # corrupted file etc.
            QMessageBox.critical(self, APP_NAME, f"Could not open project:\n{exc}")

    def save_project(self, force_dialog=False):
        path = self._file_path
        if force_dialog or not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save project", f"{self.project.name}{Project.FILE_EXT}",
                f"Wave Studio project (*{Project.FILE_EXT})")
            if not path:
                return
            if not path.endswith(Project.FILE_EXT):
                path += Project.FILE_EXT
        try:
            self.project.save(path)
            self._file_path = path
            self.statusBar().showMessage(f"Saved {path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not save:\n{exc}")

    def export(self, mode: str):
        if mode == "song" and not self.project.clips:
            QMessageBox.information(
                self, APP_NAME,
                "The playlist is empty — place some pattern clips first "
                "(or export the pattern instead).")
            return
        default = f"{self.project.name.replace(' ', '_')}_{mode}.wav"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {mode} as WAV",
                                              default, "WAV audio (*.wav)")
        if not path:
            return
        if not path.lower().endswith(".wav"):
            path += ".wav"
        self.statusBar().showMessage("Rendering…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            seconds = export_wav(path, self.project, mode)
            self.statusBar().showMessage(
                f"Exported {path} ({seconds:.1f} s)", 8000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Export failed:\n{exc}")
        finally:
            QApplication.restoreOverrideCursor()

    def _confirm_discard(self) -> bool:
        res = QMessageBox.question(
            self, APP_NAME, "Discard unsaved changes to the current project?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return res == QMessageBox.StandardButton.Yes

    def about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3 style='color:#7db1ff'>Wave Studio {__version__}</h3>"
            "<p>A modern, minimal desktop DAW written in Python "
            "(Qt + NumPy) with a fully custom synthesizer / sequencer / "
            "plugin engine.</p>"
            "<p><b>Channel Rack</b> — step-sequenced drums & synths.<br>"
            "<b>Piano Roll</b> — draw melodies; Alt+wheel sets velocity.<br>"
            "<b>Playlist</b> — arrange patterns into a song.<br>"
            "<b>Plugins</b> — per-channel & master FX: delay, reverb, "
            "chorus, filter, EQ, distortion, bitcrusher, compressor, "
            "limiter, stereo width.<br><b>Sampler</b> — load any WAV, pitch "
            "it on the piano roll.</p>"
            "<p>Space = play/pause · Z X C V B = keys · REC = live record · "
            "Ctrl+Z = undo · File ▸ Export renders to WAV.</p>")

    # ----------------------------------------------------------------------
    def _browser_add_channel(self, gen: str):
        self.tabs.setCurrentIndex(1)
        self.rack.add_channel(gen)

    # ----------------------------------------------------------------------
    # computer-keyboard piano (preview + live recording)
    # ----------------------------------------------------------------------
    def keyPressEvent(self, e):
        if e.isAutoRepeat():
            return
        fw = QApplication.focusWidget()
        from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QLineEdit,
                                       QSpinBox)
        if isinstance(fw, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox)):
            return super().keyPressEvent(e)
        key = e.text().lower()
        if key and key in PIANO_KEYS:
            ch = self.rack.selected_channel()
            if ch is None:
                return
            pitch = BASE_OCTAVE + 12 * self.octave + PIANO_KEYS[key]
            self.engine.preview(ch, pitch)
            self._maybe_record(ch, pitch)
            return
        if key == "[":                        # octave shift
            self.octave = max(-3, self.octave - 1)
            self.statusBar().showMessage(f"Octave: {self.octave:+d}", 1200)
            return
        if key == "]":
            self.octave = min(3, self.octave + 1)
            self.statusBar().showMessage(f"Octave: {self.octave:+d}", 1200)
            return
        super().keyPressEvent(e)

    def _maybe_record(self, ch, pitch: int):
        if not (self.recording and self.engine.playing
                and self.engine.mode == "pattern"):
            return
        if ch.kind not in ("synth", "sample"):
            return
        if not self._rec_snapshot_done:
            self._rec_snapshot_done = True
            self.snapshot()
        state = self.engine.get_state()
        pat = self.project.pattern()
        qstep = int(round(state["loop_pos_float"])) % max(1, pat.length)
        with self.engine.lock:
            pat.add_note(ch.id, Note(qstep, 2, pitch, 0.85))
        self.refresh_ui()
        self.statusBar().showMessage(
            f"Recorded {pitch} @ step {qstep + 1}", 1200)

    # ----------------------------------------------------------------------
    # keep everything in sync
    # ----------------------------------------------------------------------
    def _reload_panels(self):
        # panels keep engine reference; hand them the (new) project object
        self.playlist.project = self.project
        self.playlist.canvas.project = self.project
        self.rack.project = self.project
        self.mixer.project = self.project
        if self._piano_roll is not None:
            self._piano_roll.panel.project = self.project
        for dlg in self._fx_dialogs.values():
            dlg.project = self.project
            dlg.rebuild()
        self.transport.sync(self.project, self.engine)
        self.rack.rebuild_rows()
        self.rack.refresh_rows()
        self.mixer.rebuild()
        self.playlist.refresh()
        self.setWindowTitle(f"{APP_NAME} — {self.project.name}")

    def _reload_into_ui(self):
        self.engine.set_project(self.project)
        self._reload_panels()

    def refresh_ui(self):
        self.mixer.refresh()
        self.playlist.refresh()
        if self._piano_roll is not None:
            self._piano_roll.panel.refresh()
        self._sync_undo_actions()

    # ----------------------------------------------------------------------
    def tick(self):
        state = self.engine.get_state()
        playing = state["playing"]
        paused_mid = (not playing) and (self.engine.abs_step > 0 or
                                        self.engine.samples_into_step > 0)
        self.transport.set_playing(playing or paused_mid)
        self.transport.set_position(state["bar"], state["beat"],
                                    state["tick"], state["seconds"])
        if playing and self.engine.mode == "pattern":
            self.rack.set_current_step(state["loop_pos_float"], True)
            self.playlist.set_playhead(None)
        elif playing:
            self.rack.set_current_step(-1, False)
            self.playlist.set_playhead(state["loop_pos_float"])
        elif paused_mid and self.engine.mode == "song":
            self.rack.set_current_step(-1, False)
            self.playlist.set_playhead(state["loop_pos"])   # held seek spot
        else:
            self.rack.set_current_step(-1, False)
            self.playlist.set_playhead(None)
        if self._piano_roll is not None:
            step = state["loop_pos_float"] if (playing and
                                               self.engine.mode == "pattern") \
                else None
            self._piano_roll.panel.set_playhead(step)
        self.mixer.update_meters(state["peaks"], state["master_peak"])
        self._update_status_facts(state)
