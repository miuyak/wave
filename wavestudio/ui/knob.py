"""A small rotary knob — minimal dark style, blue value arc, drag vertically."""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class Knob(QWidget):
    valueChanged = Signal(float)

    def __init__(self, minimum=0.0, maximum=1.0, value=0.5, label="",
                 size=36, bipolar=False, default=None, parent=None):
        super().__init__(parent)
        self._min = float(minimum)
        self._max = float(maximum)
        self._default = float(default) if default is not None else (
            (self._max + self._min) / 2.0 if bipolar else float(minimum))
        self._value = min(max(float(value), minimum), maximum)
        self.bipolar = bipolar
        self._drag_y = None
        self._drag_start = 0.0
        self._size = size
        self.setFixedSize(size, size + (13 if label else 4))
        self._label = None
        if label:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            lay.addStretch(1)
            self._label = QLabel(label)
            self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._label.setStyleSheet("color:#8a90a0; font-size:9px;")
            lay.addWidget(self._label)

    # ------------------------------------------------------------------
    def value(self):
        return self._value

    def setValue(self, v, emit=True):
        v = min(max(float(v), self._min), self._max)
        if v != self._value:
            self._value = v
            self.update()
            if emit:
                self.valueChanged.emit(self._value)

    def set_label(self, text):
        if self._label is not None:
            self._label.setText(text)

    # ------------------------------------------------------------------
    def _angles(self):
        """Qt angle convention: 3 o'clock = 0, positive counter-clockwise."""
        frac = (self._value - self._min) / max(1e-9, self._max - self._min)
        span_deg = 270.0
        if self.bipolar:
            start = 90.0                      # 12 o'clock
            span = -(frac - 0.5) * span_deg
        else:
            start = 225.0                     # 7:30 position
            span = -frac * span_deg
        return start, span

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = self._size
        cx, cy = self.width() / 2, d / 2
        r = d / 2 - 3

        start, span = self._angles()
        arc_rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        # track
        pen = QPen(QColor("#262a33"), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if self.bipolar:
            p.drawArc(arc_rect, int((90 - 135) * 16), int(270 * 16))
        else:
            p.drawArc(arc_rect, int(225 * 16), int(-270 * 16))

        # value arc
        if abs(span) > 0.5 or not self.bipolar:
            pen = QPen(QColor("#4d8dff"), 2.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(arc_rect, int(start * 16), int(span * 16))

        # body
        grad = QRadialGradient(QPointF(cx - r * 0.3, cy - r * 0.35), r * 1.5)
        grad.setColorAt(0.0, QColor("#2a2e37"))
        grad.setColorAt(1.0, QColor("#191c22"))
        p.setBrush(grad)
        p.setPen(QPen(QColor("#0d0e11"), 1))
        p.drawEllipse(QPointF(cx, cy), r * 0.78, r * 0.78)

        # dial indicator
        end_qt = start + span
        ang = math.radians(end_qt)
        ix = cx + math.cos(ang) * r * 0.55
        iy = cy - math.sin(ang) * r * 0.55
        p.setPen(QPen(QColor("#dbeafe"), 2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(ix, iy))
        p.end()

    # ------------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_y = e.position().y()
            self._drag_start = self._value

    def mouseMoveEvent(self, e):
        if self._drag_y is not None:
            dv = (self._drag_y - e.position().y()) / 150.0
            self.setValue(self._drag_start + dv * (self._max - self._min))

    def mouseReleaseEvent(self, _e):
        self._drag_y = None

    def mouseDoubleClickEvent(self, _e):       # double-click resets to default
        self.setValue(self._default)

    def wheelEvent(self, e):
        step = (self._max - self._min) / 40.0
        self.setValue(self._value + step * (1 if e.angleDelta().y() > 0 else -1))
