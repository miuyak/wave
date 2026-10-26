"""Plugin rack: per-channel and master effect chains.

Add/remove/enable plugins; every parameter auto-generates a knob (or combo),
tweaks are applied to the live engine without restarting the audio graph.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout,
                               QLabel, QMenu, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ..effects import EFFECT_MENU, EFFECTS, Effect
from .knob import Knob


def _fmt(key: str, value, kind: str) -> str:
    if kind == "log" and value >= 1000:
        return f"{value / 1000:.1f}k"
    if kind == "float":
        return f"{value:.1f}"
    if kind == "log":
        return f"{value:.0f}"
    return str(int(value))


class ParamControl(QWidget):
    """One auto-generated knob or combo for a plugin parameter."""
    paramChanged = Signal(str, float)

    def __init__(self, fx: Effect, spec: tuple, parent=None):
        super().__init__(parent)
        self.fx = fx
        self.spec = spec
        key, label, mn, mx, default, kind = spec[:6]
        self.key, self.kind, self.mn, self.mx = key, kind, mn, mx

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        if kind == "choice":
            combo = QComboBox()
            for item in spec[6]:
                combo.addItem(item)
            combo.setCurrentIndex(int(fx.get(key, default)))
            combo.currentIndexChanged.connect(
                lambda i: self.paramChanged.emit(key, float(i)))
            lay.addWidget(combo)
            self.combo = combo
        else:
            self.knob = Knob(0.0, 1.0, 0.0, size=30)
            self.knob.setValue(self._to_knob(fx.get(key, default)), emit=False)
            self.knob.valueChanged.connect(self._knob_changed)
            lay.addWidget(self.knob, 0, Qt.AlignmentFlag.AlignHCenter)

        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet("color:#8a90a0; font-size:10px;")
        self.lbl.setMinimumWidth(64)
        self._update_label()
        lay.addWidget(self.lbl, 0, Qt.AlignmentFlag.AlignHCenter)

    # log knobs map exponentially --------------------------------------
    def _to_knob(self, value):
        if self.kind == "log":
            return math.log(max(value, 1e-6) / self.mn) / math.log(self.mx / self.mn)
        return (value - self.mn) / (self.mx - self.mn)

    def _from_knob(self, t):
        if self.kind == "log":
            return self.mn * (self.mx / self.mn) ** t
        v = self.mn + t * (self.mx - self.mn)
        return int(round(v)) if self.kind == "int" else v

    def _knob_changed(self, t):
        value = self._from_knob(t)
        self.paramChanged.emit(self.key, float(value))
        self._update_label()

    def _update_label(self):
        if self.kind == "choice":
            self.lbl.setText(self.spec[1])
        else:
            self.lbl.setText(f"{self.spec[1]}  "
                             f"{_fmt(self.key, self.fx.get(self.key), self.kind)}")

    def pull(self):
        """Refresh from the model (undo/redo, project load)."""
        if self.kind != "choice":
            self.knob.blockSignals(True)
            self.knob.setValue(self._to_knob(self.fx.get(self.key)), emit=False)
            self.knob.blockSignals(False)
        self._update_label()


class FXCard(QFrame):
    """One plugin in the rack."""
    removed = Signal()
    toggled = Signal(bool)
    paramChanged = Signal(str, float)

    def __init__(self, fx: Effect, parent=None):
        super().__init__(parent)
        self.fx = fx
        self.setStyleSheet(
            "FXCard{background:#17191f; border:1px solid #262a33;"
            "border-radius:10px;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.power = QPushButton("●")
        self.power.setCheckable(True)
        self.power.setChecked(fx.enabled)
        self.power.setFixedSize(26, 24)
        self.power.setToolTip("Enable / bypass")
        self.power.setStyleSheet(
            "QPushButton{padding:0;color:#4f8dfd;border-radius:6px;}"
            "QPushButton:checked{color:#4f8dfd;}"
            "QPushButton:!checked{color:#3a3f4a;}")
        self.power.toggled.connect(self.toggled)
        head.addWidget(self.power)
        name = QLabel(fx.name)
        name.setStyleSheet("font-weight:600; font-size:13px;")
        head.addWidget(name, 1)
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(26, 24)
        btn_x.setToolTip("Remove plugin")
        btn_x.setStyleSheet("QPushButton{padding:0;border-radius:6px;}"
                            "QPushButton:hover{color:#ef5350;}")
        btn_x.clicked.connect(self.removed)
        head.addWidget(btn_x)
        lay.addLayout(head)

        if fx.PARAMS:
            params = QHBoxLayout()
            params.setSpacing(14)
            for spec in fx.PARAMS:
                ctl = ParamControl(fx, spec)
                ctl.paramChanged.connect(self.paramChanged)
                params.addWidget(ctl)
            params.addStretch(1)
            lay.addLayout(params)
            self.controls = [params.itemAt(i).widget()
                             for i in range(params.count() - 1)]
        else:
            self.controls = []


class FXRackDialog(QDialog):
    """Floating plugin-rack window for one channel or the master bus."""
    structureChanged = Signal()      # add/remove/toggle (undoable)

    def __init__(self, project, engine, target, title, parent=None):
        super().__init__(parent)
        self.project = project
        self.engine = engine
        self.target = target           # channel id or None (master)
        self.setWindowTitle(title)
        self.setMinimumSize(430, 300)
        self.resize(560, 420)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("font-weight:700; font-size:15px;")
        head.addWidget(t, 1)
        self.btn_add = QPushButton("＋ Add plugin")
        self.btn_add.setProperty("accent", True)
        menu = QMenu(self)
        for section, ids in EFFECT_MENU:
            menu.addSection(section)
            for tid in ids:
                menu.addAction(EFFECTS[tid].name,
                               lambda _=False, i=tid: self.add_fx(i))
        self.btn_add.setMenu(menu)
        head.addWidget(self.btn_add)
        lay.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_widget = QWidget()
        self.cards_lay = QVBoxLayout(self.cards_widget)
        self.cards_lay.setContentsMargins(0, 0, 0, 0)
        self.cards_lay.setSpacing(8)
        self.cards_lay.addStretch(1)
        self.scroll.setWidget(self.cards_widget)
        lay.addWidget(self.scroll, 1)

        self.empty_hint = QLabel("No plugins yet — add one above.\n"
                                 "Everything is processed live; knobs never "
                                 "interrupt the audio.")
        self.empty_hint.setObjectName("dim")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty_hint)

        self.rebuild()

    # ------------------------------------------------------------------
    def _chain_model(self):
        if self.target is None:
            return self.project.master_fx
        ch = self.project.channel(self.target)
        return ch.fx if ch is not None else []

    # ------------------------------------------------------------------
    def rebuild(self):
        while self.cards_lay.count() > 1:
            item = self.cards_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        # bind live instances so knobs touch the running graph
        live = self.engine.master_chain if self.target is None \
            else self.engine.fx_map.get(self.target, [])
        model = self._chain_model()
        for i, data in enumerate(model):
            fx = live[i] if i < len(live) else \
                EFFECTS[data["type"]](data.get("params"),
                                      data.get("enabled", True))
            card = FXCard(fx)
            card.removed.connect(lambda _=0, idx=i: self.remove_fx(idx))
            card.toggled.connect(lambda on, idx=i: self.toggle_fx(idx, on))
            card.paramChanged.connect(
                lambda key, val, idx=i: self.param_changed(idx, key, val))
            self.cards_lay.insertWidget(self.cards_lay.count() - 1, card)
        self.empty_hint.setVisible(not model)

    def add_fx(self, type_id: str):
        self.structureChanged.emit()
        self._chain_model().append(
            {"type": type_id, "enabled": True, "params": {}})
        self.engine.sync_fx()
        self.rebuild()

    def remove_fx(self, index: int):
        self.structureChanged.emit()
        chain = self._chain_model()
        if 0 <= index < len(chain):
            del chain[index]
        self.engine.sync_fx()
        self.rebuild()

    def toggle_fx(self, index: int, on: bool):
        chain = self._chain_model()
        if 0 <= index < len(chain):
            chain[index]["enabled"] = bool(on)
        self.engine.set_fx_enabled(self.target, index, on)

    def param_changed(self, index: int, key: str, value):
        chain = self._chain_model()
        if 0 <= index < len(chain):
            cls = EFFECTS[chain[index]["type"]]
            spec = next(s for s in cls.PARAMS if s[0] == key)
            if spec[5] == "int":
                value = int(round(value))
            chain[index].setdefault("params", {})[key] = value
        self.engine.update_fx_param(self.target, index, key, value)
