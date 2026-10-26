"""Mixer: channel strips with meter, fader, pan, mute/solo, plugins + master."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QVBoxLayout, QWidget)

from .knob import Knob


def _db_frac(peak: float) -> float:
    """0..1 peak -> meter fraction over -60..0 dB."""
    if peak <= 0.00063:
        return 0.0
    return max(0.0, min(1.0, (20 * math.log10(peak) + 60.0) / 60.0))


class Meter(QWidget):
    """Vertical dB meter with a blue→red gradient and glowing head."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.peak = 0.0
        self.setFixedSize(10, 150)

    def set_peak(self, v: float):
        v = max(0.0, min(1.0, v))
        if abs(v - self.peak) > 0.004 or (v == 0) != (self.peak == 0):
            self.peak = v
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#101216"))
        p.drawRoundedRect(rect, 4, 4)
        frac = _db_frac(self.peak)
        h = int(rect.height() * frac)
        if h > 0:
            grad = QLinearGradient(0, rect.bottom(), 0, rect.top())
            grad.setColorAt(0.0, QColor("#2563eb"))
            grad.setColorAt(0.6, QColor("#60a5fa"))
            grad.setColorAt(0.85, QColor("#93c5fd"))
            grad.setColorAt(1.0, QColor("#ef4444"))
            inner = rect.adjusted(1, rect.height() - h, -1, 0)
            p.setBrush(grad)
            p.drawRoundedRect(inner, 3, 3)
        p.end()


class ChannelStrip(QFrame):
    requestFx = Signal(int)

    def __init__(self, channel, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.setFixedWidth(84)
        self.setStyleSheet(
            "ChannelStrip{background:#17191f; border:1px solid #262a33;"
            "border-radius:10px;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        name = QLabel(channel.name)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setFixedHeight(30)
        name.setStyleSheet(f"color:{channel.color}; font-weight:600;"
                           "font-size:11px; border:none;")
        lay.addWidget(name)

        btn_fx = QPushButton("FX")
        btn_fx.setFixedHeight(22)
        btn_fx.setToolTip("Plugins for this channel")
        btn_fx.setStyleSheet("font-size:10px; padding:0; border-radius:6px;")
        btn_fx.clicked.connect(lambda: self.requestFx.emit(channel.id))
        self.btn_fx = btn_fx
        self._update_fx_badge()
        lay.addWidget(btn_fx)

        mid = QHBoxLayout()
        mid.setSpacing(8)
        mid.addStretch(1)
        self.meter = Meter()
        mid.addWidget(self.meter)
        self.fader = QSlider(Qt.Orientation.Vertical)
        self.fader.setRange(0, 125)
        self.fader.setValue(int(channel.volume * 100))
        self.fader.setFixedHeight(150)
        self.fader.setToolTip("Volume")
        self.fader.valueChanged.connect(
            lambda v: setattr(self.channel, "volume", v / 100.0))
        mid.addWidget(self.fader)
        mid.addStretch(1)
        lay.addLayout(mid)

        self.db_lbl = QLabel("-∞")
        self.db_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.db_lbl.setStyleSheet(
            "color:#5c6373; font-family:'SF Mono','Consolas',monospace;"
            "font-size:9px; border:none;")
        self.db_lbl.setToolTip("Peak level (dB)")
        lay.addWidget(self.db_lbl)

        self.pan = Knob(-1, 1, channel.pan, size=30, bipolar=True)
        self.pan.valueChanged.connect(lambda v: setattr(self.channel, "pan", v))
        self.pan.setToolTip("Pan (double-click resets)")
        pan_row = QHBoxLayout()
        pan_row.addStretch(1)
        pan_row.addWidget(self.pan)
        pan_row.addStretch(1)
        lay.addLayout(pan_row)

        ms = QHBoxLayout()
        ms.setSpacing(4)
        self.mute = QPushButton("M")
        self.mute.setCheckable(True)
        self.mute.setMinimumSize(30, 24)
        self.mute.setStyleSheet("QPushButton{padding:0;font-size:10px;"
                                "border-radius:6px;}"
                                "QPushButton:checked{background:#a83c3c;"
                                "border-color:#a83c3c;color:#ffe2e2;}")
        self.mute.setChecked(channel.mute)
        self.mute.setToolTip("Mute")
        self.mute.toggled.connect(lambda on: setattr(self.channel, "mute", on))
        self.solo = QPushButton("S")
        self.solo.setCheckable(True)
        self.solo.setMinimumSize(30, 24)
        self.solo.setStyleSheet("QPushButton{padding:0;font-size:10px;"
                                "border-radius:6px;}"
                                "QPushButton:checked{background:#b07a2a;"
                                "border-color:#b07a2a;color:#fff3dc;}")
        self.solo.setChecked(channel.solo)
        self.solo.setToolTip("Solo")
        self.solo.toggled.connect(lambda on: setattr(self.channel, "solo", on))
        ms.addWidget(self.mute)
        ms.addWidget(self.solo)
        lay.addLayout(ms)

    def _update_fx_badge(self):
        on = sum(1 for f in self.channel.fx if f.get("enabled", True))
        total = len(self.channel.fx)
        self.btn_fx.setText("FX" if not total else f"FX {on}/{total}")
        self.btn_fx.setProperty("accent", bool(total))
        self.btn_fx.style().unpolish(self.btn_fx)
        self.btn_fx.style().polish(self.btn_fx)

    def set_peak(self, v: float):
        self.meter.set_peak(v)
        if v <= 0.00063:
            txt = "-∞"
        else:
            db = 20 * math.log10(max(v, 1e-9))
            txt = f"{db:.1f}" if db < 0 else f"+{db:.1f}"
        if txt != self.db_lbl.text():
            self.db_lbl.setText(txt)
            self.db_lbl.setStyleSheet(
                f"color:{'#ef5350' if v > 0.89 else '#5c6373'};"
                "font-family:'SF Mono','Consolas',monospace;"
                "font-size:9px; border:none;")


class MixerPanel(QWidget):
    requestFx = Signal(object)         # channel id or None for master

    def __init__(self, project, engine, parent=None):
        super().__init__(parent)
        self.project = project
        self.engine = engine
        self.strips: list[ChannelStrip] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QWidget()
        bar.setStyleSheet("background:#101216; border-bottom:1px solid #1e222a;")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(10, 8, 10, 8)
        title = QLabel("Mixer")
        title.setStyleSheet("font-weight:600;")
        bh.addWidget(title)
        hint = QLabel("faders & pans are per-channel · FX opens the plugin "
                      "rack · double-click pan to center")
        hint.setObjectName("dim")
        bh.addStretch(1)
        bh.addWidget(hint)
        lay.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container.setStyleSheet("background:transparent;")
        self.hlay = QHBoxLayout(self.container)
        self.hlay.setContentsMargins(10, 10, 10, 10)
        self.hlay.setSpacing(8)
        self.hlay.addStretch(1)
        self.scroll.setWidget(self.container)
        lay.addWidget(self.scroll, 1)

        self.master_meter = Meter()
        self.rebuild()

    # ------------------------------------------------------------------
    def rebuild(self):
        while self.hlay.count():
            item = self.hlay.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.strips = []
        for ch in self.project.channels:
            strip = ChannelStrip(ch)
            strip.requestFx.connect(lambda cid: self.requestFx.emit(cid))
            self.hlay.addWidget(strip, 0, Qt.AlignmentFlag.AlignTop)
            self.strips.append(strip)

        # master strip at the right
        frame = QFrame()
        frame.setFixedWidth(94)
        frame.setStyleSheet(
            "QFrame{background:#14161c; border:1px solid #2e5dd7;"
            "border-radius:10px;}")
        v = QVBoxLayout(frame)
        v.setContentsMargins(8, 8, 8, 8)
        lbl = QLabel("MASTER")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:#7db1ff; font-weight:700; font-size:11px;"
                          "border:none;")
        v.addWidget(lbl)
        btn_mfx = QPushButton("FX")
        btn_mfx.setFixedHeight(22)
        btn_mfx.setToolTip("Master plugins")
        btn_mfx.setStyleSheet("font-size:10px; padding:0; border-radius:6px;")
        on = sum(1 for f in self.project.master_fx if f.get("enabled", True))
        total = len(self.project.master_fx)
        btn_mfx.setText("FX" if not total else f"FX {on}/{total}")
        btn_mfx.clicked.connect(lambda: self.requestFx.emit(None))
        v.addWidget(btn_mfx)
        mid = QHBoxLayout()
        self.master_meter = Meter()
        mid.addWidget(self.master_meter)
        self.master_fader = QSlider(Qt.Orientation.Vertical)
        self.master_fader.setRange(0, 100)
        self.master_fader.setValue(int(self.engine.master_volume * 100))
        self.master_fader.setFixedHeight(150)
        self.master_fader.valueChanged.connect(self._master_changed)
        mid.addWidget(self.master_fader)
        v.addLayout(mid)
        self.master_db = QLabel("-∞")
        self.master_db.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.master_db.setStyleSheet(
            "color:#5c6373; font-family:'SF Mono','Consolas',monospace;"
            "font-size:9px; border:none;")
        v.addWidget(self.master_db)
        self.hlay.addWidget(frame, 0, Qt.AlignmentFlag.AlignTop)
        self.hlay.addStretch(1)

    def _master_changed(self, v):
        self.engine.master_volume = v / 100.0
        self.project.master_volume = self.engine.master_volume

    # ------------------------------------------------------------------
    def refresh(self):
        if len(self.strips) != len(self.project.channels) or \
                any(s.channel not in self.project.channels for s in self.strips):
            self.rebuild()
            return
        for s in self.strips:
            s._update_fx_badge()

    def update_meters(self, peaks: dict, master_peak: float):
        for strip in self.strips:
            strip.set_peak(peaks.get(strip.channel.id, 0.0))
        self.master_meter.set_peak(master_peak)
        if master_peak <= 0.00063:
            self.master_db.setText("-∞")
        else:
            db = 20 * math.log10(max(master_peak, 1e-9))
            self.master_db.setText(f"{db:.1f}" if db < 0 else f"+{db:.1f}")
