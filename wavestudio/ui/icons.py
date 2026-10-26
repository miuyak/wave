"""Tiny painted vector icons — crisp on every display, no font/emoji risk."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pixmap(kind: str, size: int, color: QColor) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)

    if kind == "play":
        path = QPainterPath()
        path.moveTo(QPointF(s * 0.32, s * 0.2))
        path.lineTo(QPointF(s * 0.32, s * 0.8))
        path.lineTo(QPointF(s * 0.8, s * 0.5))
        path.closeSubpath()
        # rounded look via stroked outline
        p.setPen(QPen(color, s * 0.07, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.fillPath(path, color)
    elif kind == "pause":
        w, h, gap = s * 0.16, s * 0.56, s * 0.12
        y = (s - h) / 2
        x = (s - (2 * w + gap)) / 2
        p.drawRoundedRect(QRectF(x, y, w, h), w / 2, w / 2)
        p.drawRoundedRect(QRectF(x + w + gap, y, w, h), w / 2, w / 2)
    elif kind == "stop":
        r = s * 0.30
        p.drawRoundedRect(QRectF((s - 2 * r) / 2, (s - 2 * r) / 2,
                                 2 * r, 2 * r), s * 0.08, s * 0.08)
    elif kind == "rec":
        p.setBrush(color)
        p.drawEllipse(QPointF(s / 2, s / 2), s * 0.3, s * 0.3)
    elif kind == "plus":
        p.setPen(QPen(color, s * 0.11, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(s * 0.2, s * 0.5), QPointF(s * 0.8, s * 0.5))
        p.drawLine(QPointF(s * 0.5, s * 0.2), QPointF(s * 0.5, s * 0.8))
    elif kind == "plug":                     # three mini faders
        p.setPen(QPen(color, s * 0.09, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        for i, k in enumerate((0.28, 0.5, 0.72)):
            x = s * (0.25 + i * 0.25)
            p.drawLine(QPointF(x, s * 0.22), QPointF(x, s * 0.78))
            p.drawEllipse(QPointF(x, s * k), s * 0.13, s * 0.13)
    elif kind == "copy":
        pen = QPen(color, s * 0.07)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(s * 0.2, s * 0.3, s * 0.5, s * 0.5), 3, 3)
        p.drawRoundedRect(QRectF(s * 0.35, s * 0.18, s * 0.5, s * 0.5), 3, 3)
    elif kind == "paste":
        pen = QPen(color, s * 0.08)
        p.setPen(pen)
        p.drawLine(QPointF(s * 0.5, s * 0.15), QPointF(s * 0.5, s * 0.85))
        p.drawLine(QPointF(s * 0.22, s * 0.58), QPointF(s * 0.5, s * 0.85))
        p.drawLine(QPointF(s * 0.78, s * 0.58), QPointF(s * 0.5, s * 0.85))
    elif kind == "metro":                    # metronome
        body = QPainterPath()
        body.moveTo(QPointF(s * 0.30, s * 0.82))
        body.lineTo(QPointF(s * 0.43, s * 0.18))
        body.lineTo(QPointF(s * 0.57, s * 0.18))
        body.lineTo(QPointF(s * 0.70, s * 0.82))
        body.closeSubpath()
        p.setPen(QPen(color, s * 0.07, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(body)
        p.drawLine(QPointF(s * 0.5, s * 0.3), QPointF(s * 0.68, s * 0.62))
        p.drawEllipse(QPointF(s * 0.68, s * 0.62), s * 0.05, s * 0.05)
    elif kind == "note":
        p.setPen(QPen(color, s * 0.08, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(s * 0.62, s * 0.18), QPointF(s * 0.62, s * 0.62))
        p.drawEllipse(QPointF(s * 0.42, s * 0.68), s * 0.16, s * 0.12)
    p.end()
    return pm


def icon(kind: str, color: str = "#d6dae2", size: int = 32) -> QIcon:
    ic = QIcon()
    for sz in (16, 20, 24, 32, 48):
        ic.addPixmap(_pixmap(kind, sz, QColor(color)))
    return ic
