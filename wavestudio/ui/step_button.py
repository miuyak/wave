"""Animated step button for the sequencer — design/mockup.html look:
28px, radius 7, gradient + glow when on, hover lift, playhead flash."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

OFF_A = QColor("#1d2026")                    # even beat group
OFF_B = QColor("#171a20")                    # odd beat group
HOVER = QColor("#262b35")
ON_TOP = QColor("#8fb6ff")                   # active step (light blue)
ON_BOT = QColor("#4d8dff")                   # ... to richer blue
BORDER = QColor("#101216")
BORDER_ON = QColor("#2a52b8")
GLOW = QColor("#4d8dff")
CHASE = QColor("#9ec2ff")


def _lerp(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class StepButton(QWidget):
    toggled = Signal(bool)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.active = False
        self.current = False
        self._blend = 0.0                      # 0 = off, 1 = on (animated)
        self._flash = 0.0                      # playhead flash overlay
        self._hover = 0.0
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._anim = None
        self._flash_anim = None

    # ------------------------------------------------------------------
    def _run(self, attr: str, target: float, msec=120,
             easing=QEasingCurve.Type.OutCubic):
        anim = QVariantAnimation(self)
        anim.setStartValue(getattr(self, attr))
        anim.setEndValue(target)
        anim.setDuration(msec)
        anim.setEasingCurve(easing)
        anim.valueChanged.connect(lambda v: (setattr(self, attr, v),
                                             self.update()))
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
        return anim

    def set_active(self, on: bool, animate=True):
        if on != self.active:
            self.active = on
            if animate:
                self._anim = self._run("_blend", 1.0 if on else 0.0)
            else:
                self._blend = 1.0 if on else 0.0
                self.update()

    def set_current(self, on: bool):
        newly = on and not self.current
        self.current = on
        if newly and self.active:              # the moment the head hits it
            self._flash_anim = self._run("_flash", 1.0, 80)
            self._flash_anim.finished.connect(
                lambda: setattr(self, "_flash_anim",
                                self._run("_flash", 0.0, 220)))
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)

        base = OFF_A if (self.index // 4) % 2 == 0 else OFF_B
        if self._hover > 0 and self._blend < 0.05:
            base = _lerp(base, HOVER, self._hover)

        t = self._blend
        top = _lerp(base, ON_TOP, t)
        bot = _lerp(base, ON_BOT, t)

        if t > 0.25:                           # glow behind active steps
            glow = QColor(GLOW)
            glow.setAlpha(int(70 * t))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 8, 8)

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bot)
        p.setBrush(grad)
        border = _lerp(BORDER, BORDER_ON, t)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(rect, 7, 7)

        if t > 0.6:                            # glossy top highlight
            shine = QColor(255, 255, 255, int(38 * t))
            p.setBrush(shine)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -rect.height() // 2), 5, 5)

        if self._flash > 0.01:                 # playhead hit flash
            overlay = QColor(CHASE)
            overlay.setAlpha(int(160 * self._flash))
            p.setBrush(overlay)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 7, 7)
        elif self.current:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(CHASE, 2))
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)
        p.end()

    # ------------------------------------------------------------------
    def mousePressEvent(self, _e):
        self.toggled.emit(not self.active)

    def enterEvent(self, _e):
        self._run("_hover", 1.0, 90)

    def leaveEvent(self, _e):
        self._run("_hover", 0.0, 140)
