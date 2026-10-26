"""Transport bar: icon transport buttons (hover/glow animation), segmented
PAT-SONG control, tempo chip + tap, swing, metronome, master, position LCD."""
from __future__ import annotations

import time

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QLabel,
                               QPushButton, QWidget)

from .icons import _pixmap
from .knob import Knob
from .style import ACCENT, ACCENT_DEEP, ACCENT_HI, BORDER, SURFACE_2, \
    SURFACE_3, TEXT, WELL


class IconButton(QPushButton):
    """Flat rounded button with a painted vector icon and animated hover."""

    def __init__(self, kind: str, tooltip: str = "", size: int = 42,
                 icon_px: int = 15, accent_when_checked=False,
                 checkable=True, accent_color=ACCENT, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._hover = 0.0
        self._icon_px = icon_px
        self._accent_checked = accent_when_checked
        self._accent_color = accent_color
        self.setFixedSize(size, size)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet("background:transparent; border:none;")
        self._anim = None

    def set_kind(self, kind: str):
        self.kind = kind
        self.update()

    def _run_hover(self, target: float, msec=110):
        anim = QVariantAnimation(self)
        anim.setStartValue(self._hover)
        anim.setEndValue(target)
        anim.setDuration(msec)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: (setattr(self, "_hover", v),
                                             self.update()))
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

    def enterEvent(self, _e):
        self._run_hover(1.0)

    def leaveEvent(self, _e):
        self._run_hover(0.0, 170)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        checked = self.isChecked()
        use_accent = checked and self._accent_checked

        if use_accent:
            # soft glow halo
            glow = QColor(self._accent_color)
            glow.setAlpha(int(46 + 24 * self._hover))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 14, 14)
            bg = QColor(self._accent_color).darker(115)
        elif checked:
            bg = QColor(self._accent_color).darker(115)
        else:
            c0 = QColor(SURFACE_2)
            c1 = QColor(SURFACE_3)
            f = self._hover
            bg = QColor(int(c0.red() + (c1.red() - c0.red()) * f),
                        int(c0.green() + (c1.green() - c0.green()) * f),
                        int(c0.blue() + (c1.blue() - c0.blue()) * f))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, 12, 12)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor("#3a66c9" if use_accent else
                        ("#5a2f2f" if self._accent_color != ACCENT and checked
                         else "#2e3442")))
        p.drawRoundedRect(rect, 12, 12)

        icon_col = QColor("#ffffff") if checked else QColor("#d6dae2")
        ts = self._icon_px
        pm = _pixmap(self.kind, ts * 3, icon_col)
        p.drawPixmap(int((self.width() - ts) / 2),
                     int((self.height() - ts) / 2), ts, ts,
                     pm.scaled(ts, ts, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))
        p.end()


class SegmentedMode(QWidget):
    """iOS-style PAT / SONG segmented control."""
    modeChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(128, 36)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.btn_pat = QPushButton("PAT")
        self.btn_song = QPushButton("SONG")
        for b in (self.btn_pat, self.btn_song):
            b.setCheckable(True)
            b.setStyleSheet("""
                QPushButton{background:transparent; border:none; color:#8b93a5;
                            font-weight:600; padding:4px 0; border-radius:7px;}
                QPushButton:checked{background:#2f66e0; color:white;}
                QPushButton:hover:!checked{color:#e3e7f0;}
            """)
        self.btn_pat.setChecked(True)
        self.btn_pat.clicked.connect(lambda: self._set("pattern"))
        self.btn_song.clicked.connect(lambda: self._set("song"))
        lay.addWidget(self.btn_pat, 1)
        lay.addWidget(self.btn_song, 1)
        self.setStyleSheet(
            f"SegmentedMode{{background:{SURFACE_2}; border:1px solid {BORDER};"
            f"border-radius:10px;}}")
        self._mode = "pattern"

    def _set(self, mode, emit=True):
        self._mode = mode
        self.btn_pat.blockSignals(True)
        self.btn_song.blockSignals(True)
        self.btn_pat.setChecked(mode == "pattern")
        self.btn_song.setChecked(mode == "song")
        self.btn_pat.blockSignals(False)
        self.btn_song.blockSignals(False)
        if emit:
            self.modeChanged.emit(mode)

    def set_mode(self, mode):
        self._set(mode, emit=False)

    def mode(self):
        return self._mode


class TransportBar(QWidget):
    playClicked = Signal()
    stopClicked = Signal()
    recordToggled = Signal(bool)
    modeChanged = Signal(str)          # 'pattern' | 'song'
    bpmChanged = Signal(float)
    swingChanged = Signal(float)       # 0..0.6
    masterChanged = Signal(float)
    metronomeToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(10)

        # --- transport ---------------------------------------------------
        self.btn_play = IconButton("play", "Play / Pause  (Space)",
                                   accent_when_checked=True, checkable=False)
        self.btn_play.clicked.connect(self.playClicked)
        self.btn_stop = IconButton("stop", "Stop", size=42, icon_px=13,
                                   checkable=False)
        self.btn_stop.clicked.connect(self.stopClicked)
        self.btn_rec = IconButton("rec", "Arm recording — play notes with "
                                  "Z S X D C V G B H N J M", size=42, icon_px=13,
                                  accent_when_checked=True,
                                  accent_color="#ef5350")
        self.btn_rec.toggled.connect(self.recordToggled)
        lay.addWidget(self.btn_play)
        lay.addWidget(self.btn_stop)
        lay.addWidget(self.btn_rec)

        # --- PAT / SONG ---------------------------------------------------
        self.seg = SegmentedMode()
        self.seg.setToolTip("Pattern mode / Song mode")
        self.seg.modeChanged.connect(self.modeChanged)
        lay.addWidget(self.seg)

        self.btn_metro = IconButton("metro", "Metronome", size=36, icon_px=15)
        self.btn_metro.toggled.connect(self.metronomeToggled)
        lay.addWidget(self.btn_metro)

        lay.addSpacing(4)
        self._add_divider(lay)

        # --- position LCD --------------------------------------------------
        self.lcd = QLabel("  1 : 1 : 0")
        self.lcd.setObjectName("lcd")
        self.lcd.setMinimumWidth(128)
        self.lcd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lcd.setToolTip("Bar : Beat : Tick")
        lay.addWidget(self.lcd)
        self.time_lbl = QLabel("0:00.0")
        self.time_lbl.setObjectName("dimmer")
        self.time_lbl.setStyleSheet(
            'font-family:"SF Mono","Consolas",monospace;')
        lay.addWidget(self.time_lbl)
        self._add_divider(lay)

        # --- tempo ----------------------------------------------------------
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(20.0, 300.0)
        self.bpm.setDecimals(1)
        self.bpm.setSingleStep(1.0)
        self.bpm.setValue(126.0)
        self.bpm.setPrefix("")
        self.bpm.setFixedWidth(92)
        self.bpm.valueChanged.connect(self.bpmChanged)
        tempo_chip = QWidget()
        tempo_chip.setStyleSheet(
            f"background:{SURFACE_2}; border:1px solid {BORDER};"
            "border-radius:9px;")
        tl = QHBoxLayout(tempo_chip)
        tl.setContentsMargins(10, 3, 4, 3)
        tl.setSpacing(6)
        cap = QLabel("TEMPO")
        cap.setStyleSheet("color:#8b93a5; font-size:10px; font-weight:700;")
        tl.addWidget(cap)
        self.bpm.setStyleSheet("background:transparent; border:none; "
                               "font-weight:600; padding:0;")
        tl.addWidget(self.bpm)
        lay.addWidget(tempo_chip)
        self.btn_tap = QPushButton("Tap")
        self.btn_tap.setProperty("ghost", True)
        self.btn_tap.setFixedHeight(32)
        self.btn_tap.setToolTip("Tap tempo")
        self.btn_tap.clicked.connect(self._tap)
        lay.addWidget(self.btn_tap)
        self._taps: list[float] = []

        lay.addStretch(1)

        # --- swing / master -------------------------------------------------
        self.swing = Knob(0, 60, 0, label="Swing", size=38)
        self.swing.setToolTip("Swing (shuffles every second 16th)")
        self.swing.valueChanged.connect(lambda v: self.swingChanged.emit(v / 100.0))
        lay.addWidget(self.swing)
        lay.addSpacing(4)
        self.master = Knob(0, 1.0, 0.85, label="Master", size=38, default=0.85)
        self.master.valueChanged.connect(self.masterChanged)
        lay.addWidget(self.master)

    # ------------------------------------------------------------------
    def _add_divider(self, lay):
        line = QWidget()
        line.setFixedSize(1, 26)
        line.setStyleSheet("background:#1e222a;")
        lay.addWidget(line)
        lay.addSpacing(2)

    def _tap(self):
        now = time.perf_counter()
        if self._taps and now - self._taps[-1] > 2.0:
            self._taps.clear()
        self._taps.append(now)
        self._taps = self._taps[-6:]
        if len(self._taps) >= 2:
            dt = (self._taps[-1] - self._taps[0]) / (len(self._taps) - 1)
            if 0.15 < dt < 3.0:
                self.bpm.setValue(round(60.0 / dt, 1))

    def set_playing(self, playing: bool):
        self.btn_play.blockSignals(True)
        self.btn_play.setChecked(playing)
        self.btn_play.set_kind("pause" if playing else "play")
        self.btn_play.blockSignals(False)

    def set_position(self, bar: int, beat: int, tick: int, seconds: float):
        self.lcd.setText(f"{bar:3d} : {beat} : {tick}")
        m = int(seconds // 60)
        s = seconds - 60 * m
        self.time_lbl.setText(f"{m}:{s:04.1f}")

    def set_recording(self, on: bool):
        self.btn_rec.blockSignals(True)
        self.btn_rec.setChecked(on)
        self.btn_rec.blockSignals(False)

    def sync(self, project, engine):
        self.bpm.blockSignals(True)
        self.bpm.setValue(project.bpm)
        self.bpm.blockSignals(False)
        self.swing.blockSignals(True)
        self.swing.setValue(project.swing * 100.0)
        self.swing.blockSignals(False)
        self.master.blockSignals(True)
        self.master.setValue(engine.master_volume)
        self.master.blockSignals(False)
        self.seg.set_mode(engine.mode)
        self.btn_metro.blockSignals(True)
        self.btn_metro.setChecked(engine.metronome)
        self.btn_metro.blockSignals(False)
