"""Channel rack: channels with an animated step sequencer + pattern toolbar."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPushButton, QScrollArea,
                               QSlider, QSpinBox, QVBoxLayout, QWidget)

ACCENT_TINT = QColor(77, 141, 255, 15)
HOVER_TINT = QColor(255, 255, 255, 7)

from ..model import (DRUM_GENERATORS, GENERATORS, NUM_PATTERNS,
                     SAMPLE_GENERATORS, SYNTH_GENERATORS, Pattern)
from .knob import Knob
from .step_button import StepButton


class ChannelRow(QWidget):
    """One channel lane: selection LED, name, M/S, FX, pan, volume, steps."""
    requestPianoRoll = Signal(int)
    requestDelete = Signal(int)
    requestRename = Signal(int)
    requestPreview = Signal(int)
    requestFx = Signal(int)
    requestSample = Signal(int)
    selected = Signal(int)
    editMade = Signal()                 # user changed pattern data

    def __init__(self, project, channel, parent=None):
        super().__init__(parent)
        self.project = project
        self.channel = channel
        self.is_selected = False
        self._hover = 0.0
        self._anim = None
        self.step_buttons: list[StepButton] = []
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._build()

    # -- row background: hover tint + selected accent bar ----------------
    def _run_hover(self, target: float, msec=130):
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
        self._run_hover(0.0, 190)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        if self.is_selected:
            p.setBrush(ACCENT_TINT)
            p.drawRoundedRect(rect, 10, 10)
            bar = QColor("#4d8dff")
            p.setBrush(bar)
            p.drawRoundedRect(rect.adjusted(0, 8, -rect.width() + 3, -8), 2, 2)
        if self._hover > 0.01:
            tint = QColor(HOVER_TINT)
            tint.setAlpha(int(7 * self._hover))
            p.setBrush(tint)
            p.drawRoundedRect(rect, 10, 10)
        p.end()

    # ------------------------------------------------------------------
    def _build(self):
        ch = self.channel
        self.setFixedHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 6, 2)
        lay.setSpacing(6)

        # colored LED (click = audition + select)
        self.led = QPushButton()
        self.led.setFixedSize(10, 30)
        self.led.setToolTip("Audition sound · click lane to select channel")
        self.led.setStyleSheet(
            f"background:{ch.color}; border:none; border-radius:5px;")
        self.led.clicked.connect(self._led_clicked)
        lay.addWidget(self.led)

        # channel name button — soft dark "LCD"
        self.name_btn = QPushButton(ch.name)
        self.name_btn.setFixedSize(128, 28)
        self.name_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._style_name()
        self.name_btn.setToolTip("Click: Piano Roll · right-click: options")
        self.name_btn.clicked.connect(self._name_clicked)
        self.name_btn.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.name_btn)

        # mute / solo
        self.mute = QPushButton("M")
        self.mute.setCheckable(True)
        self.mute.setChecked(ch.mute)
        self.mute.setFixedSize(24, 24)
        self.mute.setStyleSheet("QPushButton{padding:0;font-size:10px;"
                                "border-radius:6px;}"
                                "QPushButton:checked{background:#a83c3c;"
                                "border-color:#a83c3c;color:#ffe2e2;}")
        self.mute.setToolTip("Mute")
        self.mute.toggled.connect(self._mute_toggled)
        self.solo = QPushButton("S")
        self.solo.setCheckable(True)
        self.solo.setChecked(ch.solo)
        self.solo.setFixedSize(24, 24)
        self.solo.setStyleSheet("QPushButton{padding:0;font-size:10px;"
                                "border-radius:6px;}"
                                "QPushButton:checked{background:#b07a2a;"
                                "border-color:#b07a2a;color:#fff3dc;}")
        self.solo.setToolTip("Solo")
        self.solo.toggled.connect(self._solo_toggled)
        lay.addWidget(self.mute)
        lay.addWidget(self.solo)

        # pan + volume
        self.pan = Knob(-1, 1, ch.pan, size=26, bipolar=True)
        self.pan.setToolTip("Pan")
        self.pan.valueChanged.connect(self._pan_changed)
        lay.addWidget(self.pan)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(int(ch.volume * 100))
        self.vol.setFixedWidth(66)
        self.vol.setToolTip("Channel volume")
        self.vol.valueChanged.connect(lambda v: self._vol_changed(v))
        lay.addWidget(self.vol)

        # steps ---------------------------------------------------------------
        self.steps_holder = QWidget()
        self.steps_holder.setStyleSheet("background:transparent;")
        self.steps_lay = QHBoxLayout(self.steps_holder)
        self.steps_lay.setContentsMargins(6, 0, 4, 0)
        self.steps_lay.setSpacing(5)
        self._build_steps()
        lay.addWidget(self.steps_holder, 1)

    def _style_name(self):
        self.name_btn.setStyleSheet(
            "text-align:left; padding-left:10px; background:#1a1e25;"
            "color:#e3e7f0; border:1px solid #262a33; border-radius:7px;")

    def set_selected(self, on: bool):
        if on != self.is_selected:
            self.is_selected = on
            self.update()

    # ------------------------------------------------------------------
    def _build_steps(self):
        while self.steps_lay.count():
            item = self.steps_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.step_buttons = []
        pat = self.project.pattern()
        states = pat.step_list(self.channel.id)
        for i in range(pat.length):
            btn = StepButton(i)
            btn.set_active(states[i], animate=False)
            btn.toggled.connect(lambda on, idx=i: self._step_toggled(idx, on))
            self.steps_lay.addWidget(btn)
            if i % 4 == 3:
                self.steps_lay.addSpacing(8)
            self.step_buttons.append(btn)
        self.steps_lay.addStretch(1)

    # ------------------------------------------------------------------
    def _led_clicked(self):
        self.selected.emit(self.channel.id)
        self.requestPreview.emit(self.channel.id)

    def _name_clicked(self):
        self.selected.emit(self.channel.id)
        self.requestPianoRoll.emit(self.channel.id)

    def _step_toggled(self, index: int, _on: bool):
        self.editMade.emit()                     # snapshot for undo
        pat = self.project.pattern()
        state = pat.toggle_step(self.channel.id, index)
        self.step_buttons[index].set_active(state)
        if state:
            self.requestPreview.emit(self.channel.id)

    def _mute_toggled(self, on):
        self.channel.mute = on

    def _solo_toggled(self, on):
        self.channel.solo = on

    def _pan_changed(self, v):
        self.channel.pan = v

    def _vol_changed(self, v):
        self.channel.volume = v / 100.0

    def _menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Piano roll",
                       lambda: self.requestPianoRoll.emit(self.channel.id))
        menu.addAction("Plugins…",
                       lambda: self.requestFx.emit(self.channel.id))
        if self.channel.kind == "sample":
            menu.addAction("Load sample…",
                           lambda: self.requestSample.emit(self.channel.id))
        menu.addSeparator()
        menu.addAction("Rename…", lambda: self.requestRename.emit(self.channel.id))
        menu.addAction("Delete channel",
                       lambda: self.requestDelete.emit(self.channel.id))
        menu.exec(self.mapToGlobal(pos))

    # ------------------------------------------------------------------
    def refresh(self):
        """Re-read model state (pattern switched / length changed / renamed)."""
        self.name_btn.setText(self.channel.name)
        self.mute.blockSignals(True); self.mute.setChecked(self.channel.mute)
        self.mute.blockSignals(False)
        self.solo.blockSignals(True); self.solo.setChecked(self.channel.solo)
        self.solo.blockSignals(False)
        self.pan.blockSignals(True); self.pan.setValue(self.channel.pan)
        self.pan.blockSignals(False)
        pat = self.project.pattern()
        if len(self.step_buttons) != pat.length:
            self._build_steps()
        else:
            states = pat.step_list(self.channel.id)
            for btn, st in zip(self.step_buttons, states):
                btn.blockSignals(True)
                btn.set_active(st, animate=False)
                btn.blockSignals(False)

    def set_current_step(self, step: float, playing: bool):
        cur = int(step)
        for i, btn in enumerate(self.step_buttons):
            btn.set_current(playing and i == cur)


class ChannelRack(QWidget):
    """Pattern toolbar + scrollable list of channel lanes."""
    requestPianoRoll = Signal(int)
    requestFx = Signal(int)
    structureChanged = Signal()
    patternSwitched = Signal()
    editMade = Signal()

    def __init__(self, project, engine, parent=None):
        super().__init__(parent)
        self.project = project
        self.engine = engine
        self.rows: list[ChannelRow] = []
        self.selected_channel_id = None
        self._pattern_clipboard: dict | None = None
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- toolbar ---------------------------------------------------
        bar = QWidget()
        bar.setStyleSheet("background:#101216; border-bottom:1px solid #1e222a;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)

        lbl = QLabel("Pattern")
        lbl.setObjectName("dim")
        h.addWidget(lbl)
        self.pattern_spin = QSpinBox()
        self.pattern_spin.setRange(1, NUM_PATTERNS)
        self.pattern_spin.setFixedWidth(64)
        self.pattern_spin.setFixedHeight(30)
        self.pattern_spin.valueChanged.connect(self._pattern_changed)
        h.addWidget(self.pattern_spin)

        self.pattern_name = QLineEdit()
        self.pattern_name.setFixedWidth(170)
        self.pattern_name.setFixedHeight(30)
        self.pattern_name.setPlaceholderText("Pattern name…")
        self.pattern_name.editingFinished.connect(self._name_edited)
        h.addWidget(self.pattern_name)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setProperty("ghost", True)
        self.btn_copy.setToolTip("Copy this pattern")
        self.btn_copy.clicked.connect(self._copy_pattern)
        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setProperty("ghost", True)
        self.btn_paste.setToolTip("Paste over this pattern")
        self.btn_paste.setEnabled(False)
        self.btn_paste.clicked.connect(self._paste_pattern)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setProperty("ghost", True)
        self.btn_clear.setToolTip("Erase all steps and notes in this pattern")
        self.btn_clear.clicked.connect(self._clear_pattern)
        h.addWidget(self.btn_copy)
        h.addWidget(self.btn_paste)
        h.addWidget(self.btn_clear)

        lbl2 = QLabel("Length")
        lbl2.setObjectName("dim")
        h.addSpacing(6)
        h.addWidget(lbl2)
        self.length_combo = QComboBox()
        for n in (16, 32, 48, 64):
            self.length_combo.addItem(f"{n} steps", n)
        self.length_combo.currentIndexChanged.connect(self._length_changed)
        h.addWidget(self.length_combo)

        h.addSpacing(16)
        self.btn_add = QPushButton("＋  Add channel")
        self.btn_add.setProperty("accent", True)
        self.btn_add.setFixedHeight(32)
        menu = QMenu(self)
        menu.addSection("Drums")
        for g in DRUM_GENERATORS:
            menu.addAction(GENERATORS[g]["name"],
                           lambda _=False, gen=g: self.add_channel(gen))
        menu.addSection("Sampler")
        for g in SAMPLE_GENERATORS:
            menu.addAction(GENERATORS[g]["name"],
                           lambda _=False, gen=g: self.add_channel(gen))
        menu.addSection("Synths")
        for g in SYNTH_GENERATORS:
            menu.addAction(GENERATORS[g]["name"],
                           lambda _=False, gen=g: self.add_channel(gen))
        self.btn_add.setMenu(menu)
        h.addWidget(self.btn_add)
        h.addStretch(1)
        lay.addWidget(bar)

        # ---- column header with step numbers ---------------------------
        head = QWidget()
        head.setFixedHeight(20)
        head.setStyleSheet("background:transparent;")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(4, 0, 6, 0)
        hh.setSpacing(6)
        spacer = QWidget()
        spacer.setFixedWidth(10 + 6 + 128 + 6 + 24 + 6 + 24 + 6 + 26 + 6 + 66 + 6)
        hh.addWidget(spacer)
        self._head_steps = QWidget()
        self._head_steps.setStyleSheet("background:transparent;")
        self._head_lay = QHBoxLayout(self._head_steps)
        self._head_lay.setContentsMargins(0, 0, 0, 0)
        self._head_lay.setSpacing(5)
        hh.addWidget(self._head_steps, 1)
        lay.addWidget(head)

        # ---- scrollable rows -------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.rows_widget = QWidget()
        self.rows_widget.setStyleSheet("background:transparent;")
        self.rows_lay = QVBoxLayout(self.rows_widget)
        self.rows_lay.setContentsMargins(0, 2, 0, 2)
        self.rows_lay.setSpacing(2)
        self.rows_lay.addStretch(1)
        self.scroll.setWidget(self.rows_widget)
        lay.addWidget(self.scroll, 1)

        self.rebuild_rows()
        self._build_head()
        self._sync_toolbar()

    # ------------------------------------------------------------------
    def _build_head(self):
        while self._head_lay.count():
            item = self._head_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        pat = self.project.pattern()
        for i in range(pat.length):
            lb = QLabel(str(i % 16 + 1))
            lb.setFixedSize(28, 14)
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lb.setStyleSheet("color:#5c6373; font-size:9px; background:transparent;")
            if i % 4 == 0:
                lb.setStyleSheet("color:#8b93a5; font-size:9px; font-weight:600;"
                                 " background:transparent;")
            self._head_lay.addWidget(lb)
            if i % 4 == 3:
                self._head_lay.addSpacing(8)
        self._head_lay.addStretch(1)

    # ------------------------------------------------------------------
    def rebuild_rows(self):
        for row in self.rows:
            self.rows_lay.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.rows = []
        for ch in self.project.channels:
            row = ChannelRow(self.project, ch)
            row.requestPianoRoll.connect(self.requestPianoRoll)
            row.requestFx.connect(self.requestFx)
            row.requestDelete.connect(self._delete_channel)
            row.requestRename.connect(self._rename_channel)
            row.requestSample.connect(self._load_sample)
            row.requestPreview.connect(self._preview)
            row.selected.connect(self._select)
            row.editMade.connect(self.editMade)
            row.set_selected(ch.id == self.selected_channel_id)
            self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
            self.rows.append(row)

    def refresh_rows(self):
        if len(self.rows) != len(self.project.channels) or \
                any(r.channel.id not in [c.id for c in self.project.channels]
                    for r in self.rows):
            self.rebuild_rows()
        self._sync_toolbar()
        pat = self.project.pattern()
        li = self.length_combo.findData(pat.length)
        if li >= 0 and li != self.length_combo.currentIndex():
            self.length_combo.blockSignals(True)
            self.length_combo.setCurrentIndex(li)
            self.length_combo.blockSignals(False)
        for row in self.rows:
            row.refresh()
        self._build_head()

    def _sync_toolbar(self):
        idx = self.project.current_pattern
        if self.pattern_spin.value() - 1 != idx:
            self.pattern_spin.blockSignals(True)
            self.pattern_spin.setValue(idx + 1)
            self.pattern_spin.blockSignals(False)
        name = self.project.patterns[idx].name
        if self.pattern_name.text() != name:
            self.pattern_name.blockSignals(True)
            self.pattern_name.setText(name)
            self.pattern_name.blockSignals(False)

    def set_current_step(self, step: float, playing: bool):
        for row in self.rows:
            row.set_current_step(step, playing)

    def selected_channel(self):
        ch = self.project.channel(self.selected_channel_id)
        if ch is None and self.project.channels:
            ch = self.project.channels[0]
            self.selected_channel_id = ch.id
        return ch

    # ------------------------------------------------------------------
    def _select(self, ch_id: int):
        self.selected_channel_id = ch_id
        for row in self.rows:
            row.set_selected(row.channel.id == ch_id)

    def _pattern_changed(self, v):
        with self.engine.lock:
            self.project.current_pattern = v - 1
        self.refresh_rows()
        self.patternSwitched.emit()

    def _name_edited(self):
        pat = self.project.pattern()
        text = self.pattern_name.text().strip()
        if text and text != pat.name:
            self.editMade.emit()
            pat.name = text
            self.patternSwitched.emit()

    def _copy_pattern(self):
        self._pattern_clipboard = self.project.pattern().to_dict()
        self.btn_paste.setEnabled(True)

    def _paste_pattern(self):
        if not self._pattern_clipboard:
            return
        self.editMade.emit()
        idx = self.project.current_pattern
        with self.engine.lock:
            self.project.patterns[idx] = Pattern.from_dict(self._pattern_clipboard)
            # strips steps of channels that no longer exist are rebuilt fine
        self.refresh_rows()
        self.patternSwitched.emit()
        self.structureChanged.emit()

    def _length_changed(self, idx):
        n = int(self.length_combo.itemData(idx))
        self.editMade.emit()
        with self.engine.lock:
            self.project.pattern().set_length(n)
            for c in self.project.clips:
                if c.pattern == self.project.current_pattern:
                    c.length = max(4, min(n, c.length if c.length > n else n))
        self.refresh_rows()
        self.structureChanged.emit()

    def _clear_pattern(self):
        self.editMade.emit()
        with self.engine.lock:
            self.project.pattern().clear()
        self.refresh_rows()
        self.structureChanged.emit()

    def add_channel(self, generator: str):
        self.editMade.emit()
        with self.engine.lock:
            ch = self.project.add_channel(generator)
        self.rebuild_rows()
        self._select(ch.id)
        self.structureChanged.emit()
        if ch.kind == "sample":
            self._load_sample(ch.id)

    def _delete_channel(self, ch_id: int):
        self.editMade.emit()
        with self.engine.lock:
            self.project.remove_channel(ch_id)
        if self.selected_channel_id == ch_id:
            self.selected_channel_id = None
        self.rebuild_rows()
        self.structureChanged.emit()

    def _rename_channel(self, ch_id: int):
        from PySide6.QtWidgets import QInputDialog
        ch = self.project.channel(ch_id)
        if not ch:
            return
        name, ok = QInputDialog.getText(self, "Rename channel", "Name:", text=ch.name)
        if ok and name.strip():
            self.editMade.emit()
            ch.name = name.strip()
            self.refresh_rows()

    def _load_sample(self, ch_id: int):
        ch = self.project.channel(ch_id)
        if not ch:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load sample", "", "WAV audio (*.wav)")
        if path:
            self.editMade.emit()
            ch.extra["sample"] = path
            self.engine.sample_cache.pop(path, None)
            self._preview(ch_id)

    def _preview(self, ch_id: int):
        ch = self.project.channel(ch_id)
        if ch:
            self.engine.preview(ch)
