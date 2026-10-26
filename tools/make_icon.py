"""Draws the Wave Studio app icon (very dark grey tile, smooth blue wave)
and writes PNGs of several sizes into assets/."""
import math
import os

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)

SIZES = (512, 256, 128, 64, 48, 32, 16)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
os.makedirs(OUT, exist_ok=True)


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = size
    r = s * 0.22                                    # corner radius

    # tile background: very dark grey, subtle diagonal light
    grad = QLinearGradient(0, 0, s, s)
    grad.setColorAt(0.0, QColor("#181b21"))
    grad.setColorAt(0.55, QColor("#101216"))
    grad.setColorAt(1.0, QColor("#0b0c0f"))
    path = QPainterPath()
    path.addRoundedRect(0, 0, s, s, r, r)
    p.fillPath(path, grad)

    # soft blue glow behind the wave
    glow = QRadialGradient(QPointF(s * 0.5, s * 0.52), s * 0.42)
    glow.setColorAt(0.0, QColor(79, 141, 253, 46))
    glow.setColorAt(1.0, QColor(79, 141, 253, 0))
    p.fillPath(path, glow)

    # hairline edge
    p.setPen(QPen(QColor(255, 255, 255, 14), max(1.0, s * 0.006)))
    p.drawPath(path)

    # the wave: tapered sine, blue gradient stroke, round caps
    wave = QPainterPath()
    amp = s * 0.17
    cy = s * 0.52
    x0, x1 = s * 0.16, s * 0.84
    steps = 120
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t
        taper = math.sin(math.pi * t) ** 0.8
        y = cy + amp * taper * math.sin(2 * math.pi * (1.4 * t) - math.pi / 2)
        if i == 0:
            wave.moveTo(QPointF(x, y))
        else:
            wave.lineTo(QPointF(x, y))

    wg = QLinearGradient(x0, 0, x1, 0)
    wg.setColorAt(0.0, QColor("#3b82f6"))
    wg.setColorAt(0.5, QColor("#79aaff"))
    wg.setColorAt(1.0, QColor("#4f8dfd"))

    # bloom pass
    pen = QPen(wg, s * 0.075)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(QPen(QColor(96, 165, 250, 60)))
    p.pen().setWidthF(s * 0.12)
    p.setPen(pen)
    pen.setColor(QColor(96, 165, 250, 55))
    p.setPen(pen)
    p.drawPath(wave)

    pen = QPen(wg, s * 0.042)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawPath(wave)

    p.end()
    return img


def main():
    paths = []
    for s in SIZES:
        fp = os.path.join(OUT, f"icon_{s}.png")
        draw(s).save(fp)
        paths.append(fp)
        print("wrote", fp)
    try:                                   # also a Windows .ico if Pillow exists
        from PIL import Image
        im = Image.open(paths[0])
        im.save(os.path.join(OUT, "icon.ico"),
                sizes=[(32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print("wrote icon.ico")
    except Exception as exc:
        print("no .ico (pillow missing):", exc)


if __name__ == "__main__":
    main()
