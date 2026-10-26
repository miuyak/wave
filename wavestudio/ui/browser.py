"""Left-hand browser dock: instrument palette + quick tips."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDockWidget, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QVBoxLayout, QWidget)

from ..model import DRUM_GENERATORS, GENERATORS, SAMPLE_GENERATORS, \
    SYNTH_GENERATORS


class InstrumentItem(QWidget):
    addRequested = Signal(str)
    previewRequested = Signal(str)

    def __init__(self, gen_id: str, parent=None):
        super().__init__(parent)
        self.gen_id = gen_id
        info = GENERATORS[gen_id]
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setStyleSheet("border-radius:8px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(10)

        dot = QLabel()
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(f"background:{info['color']}; border-radius:6px;")
        lay.addWidget(dot)

        name = QLabel(info["name"])
        lay.addWidget(name, 1)

        kind = QLabel(info["kind"])
        kind.setStyleSheet("color:#5c6373; font-size:10px;")
        lay.addWidget(kind)
        self.setToolTip("Double-click — add to project")

    def mouseDoubleClickEvent(self, _e):
        self.addRequested.emit(self.gen_id)

    def enterEvent(self, _e):
        self.setStyleSheet("background:#212633; border-radius:8px;")

    def leaveEvent(self, _e):
        self.setStyleSheet("background:transparent; border-radius:8px;")


class BrowserDock(QDockWidget):
    addChannel = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Browser", parent)
        self.setObjectName("browserDock")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self.setMinimumWidth(210)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable |
                         QDockWidget.DockWidgetFeature.DockWidgetMovable)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sounds…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        self.list_lay = QVBoxLayout(body)
        self.list_lay.setContentsMargins(0, 4, 0, 4)
        self.list_lay.setSpacing(2)

        self._rows: list[tuple[InstrumentItem, str]] = []

        def section(text):
            lbl = QLabel(text)
            lbl.setObjectName("section")
            self.list_lay.addWidget(lbl)

        def add_items(ids):
            for g in ids:
                item = InstrumentItem(g)
                item.addRequested.connect(self.addChannel)
                self.list_lay.addWidget(item)
                self._rows.append((item, GENERATORS[g]["name"].lower()))

        section("DRUMS")
        add_items(DRUM_GENERATORS)
        section("SAMPLER")
        add_items(SAMPLE_GENERATORS)
        section("SYNTHS")
        add_items(SYNTH_GENERATORS)
        self.list_lay.addStretch(1)

        tips = QLabel("TIPS\n"
                      "Space — play / pause (anywhere)\n"
                      "Z X C V B … — play notes\n"
                      "REC + play — record keys\n"
                      "F11 — fullscreen\n"
                      "Ctrl+Z — undo")
        tips.setObjectName("dim")
        tips.setStyleSheet("color:#5c6373; padding:8px 4px;")
        self.list_lay.addWidget(tips)

        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        self.setWidget(container)

    def _filter(self, text: str):
        text = text.strip().lower()
        for item, name in self._rows:
            item.setVisible(not text or text in name)
