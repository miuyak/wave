"""Piano roll editor for melodic channels."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSlider, QVBoxLayout,
                               QWidget)

from ..model import Note
from ..synths import NOTE_NAMES, note_name

TOP_MIDI = 96            # C7
BOTTOM_MIDI = 24         # C1
ROW_H = 16
STEP_W = 22
KEY_W = 56
BLACK_KEYS = {1, 3, 6, 8, 10}


class PianoCanvas(QWidget):
    notesChanged = Signal()
    aboutToEdit = Signal()

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel          # PianoRollPanel (holds project, channel, engine)
        self.selected: Note | None = None
        self.playhead_step = None
        self._drag = None           # ('move'|'resize', note, grab_offset)
        self._lit_keys: dict[int, int] = {}
        self.setMouseTracking(False)

    # ------------------------------------------------------------------
    @property
    def pattern(self):
        return self.panel.project.pattern()

    def notes(self):
        if self.panel.channel is None:
            return []
        return self.pattern.note_list(self.panel.channel.id)

    # -- key-strip preview flash -----------------------------------------
    def flash_key(self, pitch: int):
        self._lit_keys[pitch] = 5
        QTimer.singleShot(70, lambda: self._decay_key(pitch))

    def _decay_key(self, pitch: int):
        n = self._lit_keys.get(pitch, 0) - 1
        if n <= 0:
            self._lit_keys.pop(pitch, None)
        else:
            self._lit_keys[pitch] = n
            QTimer.singleShot(55, lambda: self._decay_key(pitch))
        self.update()

    def content_size(self):
        rows = TOP_MIDI - BOTTOM_MIDI + 1
        w = KEY_W + max(32, self.pattern.length) * STEP_W + 40
        return w, rows * ROW_H

    # ------------------------------------------------------------------
    def paintEvent(self, _e):
        channel = self.panel.channel
        p = QPainter(self)
        w, h = self.width(), self.height()
        x0 = KEY_W

        # key strip background
        p.fillRect(0, 0, x0, h, QColor("#101216"))

        row = 0
        for pitch in range(TOP_MIDI, BOTTOM_MIDI - 1, -1):
            y = row * ROW_H
            black = (pitch % 12) in BLACK_KEYS
            # grid row background
            p.fillRect(x0, y, w - x0, ROW_H,
                       QColor("#16181d") if black else QColor("#1a1d23"))
            # piano key
            lit = self._lit_keys.get(pitch, 0)
            key_color = QColor("#20232b") if black else QColor("#e5e7eb")
            kw = x0 - (16 if black else 4)
            p.fillRect(2, y + 1, kw, ROW_H - 2, key_color)
            if lit:                                # pressed-key highlight
                glow = QColor("#4d8dff")
                glow.setAlpha(min(255, 70 + 36 * lit))
                p.fillRect(2, y + 1, kw, ROW_H - 2, glow)
            if pitch % 12 == 0:
                p.setPen(QColor("#8a90a0"))
                p.drawText(x0 - 38, y, 34, ROW_H,
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           note_name(pitch))
            row += 1

        n_steps = self.pattern.length
        # vertical grid
        for s in range(n_steps + 1):
            x = x0 + s * STEP_W
            if s % 16 == 0:
                p.setPen(QPen(QColor("#2e3340"), 1))
            elif s % 4 == 0:
                p.setPen(QPen(QColor("#262a33"), 1))
            else:
                p.setPen(QPen(QColor("#20242c"), 1))
            p.drawLine(x, 0, x, h)

        # bar numbers
        p.setPen(QColor("#8a90a0"))
        for s in range(0, n_steps, 16):
            p.drawText(x0 + s * STEP_W + 4, 12, str(s // 16 + 1))

        # notes
        if channel is not None:
            base = QColor(channel.color)
            for note in list(self.notes()):
                self._draw_note(p, note, base, note is self.selected)

        # playhead (smooth: accepts a fractional step position)
        if self.playhead_step is not None:
            x = x0 + self.playhead_step * STEP_W
            p.setPen(QPen(QColor("#7db1ff"), 2))
            p.drawLine(int(x), 0, int(x), h)
        p.end()

    def _draw_note(self, p: QPainter, note: Note, base: QColor, selected: bool):
        row = TOP_MIDI - note.pitch
        if row < 0 or row > TOP_MIDI - BOTTOM_MIDI:
            return
        x = KEY_W + note.start * STEP_W
        y = row * ROW_H + 1
        w = max(8, note.length * STEP_W - 2)
        hh = ROW_H - 3
        c = QColor(base)
        c.setAlpha(120 + int(135 * note.velocity))
        p.setBrush(c)
        p.setPen(QPen(QColor("#dbeafe") if selected else base.darker(160),
                      2 if selected else 1))
        p.drawRoundedRect(x, y, w, hh, 4, 4)
        # velocity tint strip at bottom
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawRoundedRect(x + 1, y + hh - 3, w - 2, 2, 1, 1)

    # ------------------------------------------------------------------
    def _to_cell(self, x, y):
        step = int((x - KEY_W) // STEP_W)
        row = int(y // ROW_H)
        pitch = TOP_MIDI - row
        return step, pitch

    def _snap(self, step):
        s = max(1, self.panel.snap_steps())
        return max(0, (int(round(step / s))) * s)

    def _hit(self, step, pitch):
        for note in reversed(self.notes()):
            if note.pitch == pitch and note.start <= step < note.start + note.length:
                return note
        return None

    def mousePressEvent(self, e):
        if self.panel.channel is None:
            return
        # key strip -> audition that pitch
        if e.position().x() < KEY_W:
            if e.button() == Qt.MouseButton.LeftButton:
                pitch = TOP_MIDI - int(e.position().y() // ROW_H)
                if BOTTOM_MIDI <= pitch <= TOP_MIDI:
                    self.panel.engine.preview(self.panel.channel, pitch)
                    self.flash_key(pitch)
            return
        step, pitch = self._to_cell(e.position().x(), e.position().y())
        if not (BOTTOM_MIDI <= pitch <= TOP_MIDI):
            return
        pattern_len = self.pattern.length
        with self.panel.engine.lock:
            hit = self._hit(step, pitch)
            if e.button() == Qt.MouseButton.RightButton:
                if hit is not None:
                    self.pattern.remove_note(self.panel.channel.id, hit)
                    if self.selected is hit:
                        self.selected = None
                    self.notesChanged.emit()
                self.update()
                return
            if e.button() != Qt.MouseButton.LeftButton:
                return
            self.aboutToEdit.emit()
            if hit is not None:
                self.selected = hit
                edge = (hit.start + hit.length) * STEP_W + KEY_W
                if abs(e.position().x() - edge) <= 7:
                    self._drag = ("resize", hit, 0)
                else:
                    self._drag = ("move", hit, step - hit.start)
                ch = self.panel.channel
                self.panel.engine.preview(ch, pitch)
                self.flash_key(pitch)
            else:
                if step >= pattern_len:
                    return
                start = min(self._snap(step), pattern_len - 1)
                note = Note(start, self.panel.note_length_steps(), pitch,
                            self.panel.velocity())
                if note.start + note.length > pattern_len:
                    note.length = max(1, pattern_len - note.start)
                self.pattern.add_note(self.panel.channel.id, note)
                self.selected = note
                self._drag = ("resize", note, 0)
                self.panel.engine.preview(self.panel.channel, pitch)
                self.flash_key(pitch)
                self.notesChanged.emit()
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag is None or self.selected is None:
            return
        mode, note, grab = self._drag
        step, pitch = self._to_cell(e.position().x(), e.position().y())
        pattern_len = self.pattern.length
        with self.panel.engine.lock:
            if mode == "move":
                new_start = self._snap(step - grab)
                note.start = max(0, min(new_start, pattern_len - note.length))
                note.pitch = min(max(BOTTOM_MIDI, pitch), TOP_MIDI)
            else:
                end = self._snap(step + 1)
                note.length = max(1, min(end - note.start, pattern_len - note.start))
        self.update()

    def mouseReleaseEvent(self, _e):
        self._drag = None

    def wheelEvent(self, e):
        """Alt + wheel over a note (or on selection) adjusts its velocity."""
        if e.modifiers() & Qt.KeyboardModifier.AltModifier:
            step, pitch = self._to_cell(e.position().x(), e.position().y())
            note = self._hit(step, pitch)
            if note is None:
                note = self.selected
            if note is not None:
                self.aboutToEdit.emit()
                delta = 0.06 if e.angleDelta().y() > 0 else -0.06
                note.velocity = max(0.05, min(1.0, note.velocity + delta))
                self.notesChanged.emit()
                self.update()
                e.accept()
                return
        e.ignore()

    def delete_selected(self):
        if self.selected is not None and self.panel.channel is not None:
            with self.panel.engine.lock:
                self.pattern.remove_note(self.panel.channel.id, self.selected)
            self.selected = None
            self.notesChanged.emit()
            self.update()

    def set_playhead(self, step):
        if step != self.playhead_step:
            self.playhead_step = step
            self.update()


class PianoRollPanel(QWidget):
    """Toolbar + scrollable piano canvas for one channel."""
    notesChanged = Signal()
    aboutToEdit = Signal()
    requestPlayPause = Signal()

    def __init__(self, project, engine, parent=None):
        super().__init__(parent)
        self.project = project
        self.engine = engine
        self.channel = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("background:#101216; border-bottom:1px solid #1e222a;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(10)
        self.title = QLabel("Piano roll")
        self.title.setStyleSheet("font-weight:bold;")
        h.addWidget(self.title)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setProperty("accent", True)
        self.btn_play.setFixedHeight(28)
        self.btn_play.setToolTip("Play / pause this pattern (Space)")
        self.btn_play.clicked.connect(self.requestPlayPause)
        h.addWidget(self.btn_play)

        lbl = QLabel("Snap"); lbl.setObjectName("dim"); h.addWidget(lbl)
        self.snap_combo = QComboBox()
        for label, steps in (("1/4 beat", 1), ("1/2 beat", 2), ("1 beat", 4)):
            self.snap_combo.addItem(label, steps)
        h.addWidget(self.snap_combo)

        lbl = QLabel("Note length"); lbl.setObjectName("dim"); h.addWidget(lbl)
        self.len_combo = QComboBox()
        for label, steps in (("1/16", 1), ("1/8", 2), ("1/4", 4), ("1/2", 8),
                             ("bar", 16)):
            self.len_combo.addItem(label, steps)
        self.len_combo.setCurrentIndex(1)
        h.addWidget(self.len_combo)

        lbl = QLabel("Velocity"); lbl.setObjectName("dim"); h.addWidget(lbl)
        self.vel = QSlider(Qt.Orientation.Horizontal)
        self.vel.setRange(5, 100)
        self.vel.setValue(80)
        self.vel.setFixedWidth(90)
        self.vel.setToolTip("Velocity of new notes")
        h.addWidget(self.vel)

        hint = QLabel("LMB add · move · resize (right edge) — RMB delete — "
                      "Alt+wheel: velocity — Del removes selection")
        hint.setObjectName("dim")
        h.addStretch(1)
        h.addWidget(hint)
        lay.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.canvas = PianoCanvas(self)
        self.canvas.notesChanged.connect(self.notesChanged)
        self.canvas.aboutToEdit.connect(self.aboutToEdit)
        self.scroll.setWidget(self.canvas)
        lay.addWidget(self.scroll, 1)

    # ------------------------------------------------------------------
    def set_playhead(self, step):
        self.canvas.set_playhead(step)
        if step is not None and self.width() > 0:      # follow the playhead
            x = KEY_W + step * STEP_W
            sb = self.scroll.horizontalScrollBar()
            vw = self.scroll.viewport().width()
            if x < sb.value() + 10 or x > sb.value() + vw - 80:
                sb.setValue(max(0, int(x - 80)))

    def snap_steps(self):
        return int(self.snap_combo.currentData())

    def note_length_steps(self):
        return int(self.len_combo.currentData())

    def velocity(self):
        return self.vel.value() / 100.0

    # ------------------------------------------------------------------
    def set_channel(self, channel):
        self.channel = channel
        self.refresh()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.scroll_to_content)

    def scroll_to_content(self):
        """Center the view on the lowest note in the pattern (or middle C)."""
        if self.channel is not None:
            notes = self.project.pattern().notes.get(self.channel.id, [])
            if notes:
                target = min(n.pitch for n in notes)
            else:
                target = 60
            row = TOP_MIDI - target
            y = max(0, row * ROW_H - 3 * ROW_H)
            self.scroll.verticalScrollBar().setValue(y)

    def refresh(self):
        w, h = self.canvas.content_size()
        vw = self.scroll.viewport().width()
        vh = self.scroll.viewport().height()
        if vw > 1:
            w = max(w, vw)
        if vh > 1:
            h = max(h, vh)
        self.canvas.setFixedSize(w, h)
        if self.channel is None:
            self.canvas.selected = None
            self.title.setText("Piano roll — select a synth channel")
        else:
            self.title.setText(f"Piano roll — {self.channel.name}"
                               f"    [{self.project.pattern().name}]")
            self.title.setStyleSheet(
                f"font-weight:bold; color:{self.channel.color};")
        self.canvas.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.canvas.delete_selected()
            return
        super().keyPressEvent(e)


class PianoRollDialog(QDialog):
    """Floating piano-roll window, FL style."""
    notesChanged = Signal()
    aboutToEdit = Signal()
    requestPlayPause = Signal()

    def __init__(self, project, engine, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Piano roll")
        self.resize(980, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = PianoRollPanel(project, engine, self)
        self.panel.notesChanged.connect(self.notesChanged)
        self.panel.aboutToEdit.connect(self.aboutToEdit)
        self.panel.requestPlayPause.connect(self.requestPlayPause)
        lay.addWidget(self.panel)

    def set_channel(self, channel):
        self.panel.set_channel(channel)
