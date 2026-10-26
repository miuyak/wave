"""Small animation helpers for the smooth, springy feel."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


def fade_in(widget: QWidget, duration=220, start=0.0, end=1.0):
    """Fade a widget in (keeps a reference so the animation isn't GC'd)."""
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if end >= 1.0:
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start()
    widget._fade_anim = anim          # noqa: keep alive
    return anim


def window_fade_in(window: QWidget, duration=300):
    anim = QPropertyAnimation(window, b"windowOpacity", window)
    window.setWindowOpacity(0.0)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    window._win_fade = anim
    return anim
