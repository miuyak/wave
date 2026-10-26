"""Playlist: arrange patterns as clips on tracks (song mode).

v2.1: track-header column with mute toggles, clip right-edge resize,
zoom, ruler-click seeking, clip context menu, diamond-tipped playhead.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..model import PLAYLIST_BARS, PLAYLIST_TRACKS, STEPS_PER_BAR, Clip

HEADER_H = 26
ROW_H = 44
TRACK_HEAD_W = 122
EDGE = 9                                # px grab zone for clip resize

PATTERN_COLORS = ["#4d8dff", "#38bdf8", "#818cf8", "#22d3ee",
                  "#60a5fa", "#7c8cf8", "#0ea5e9", "#93c5fd",
                  "#a78bfa", "#67e8f9", "#3b82f6", "#5eead4",
                  "#8ea2ff", "#7dd3fc", "#6366f1", "#45c8f0"]


class PlaylistCanvas(QWidget):
    clipsChanged = Signal()
    aboutToEdit = Signal()
    seekRequested = Signal(int)          # absolute song step
    openPattern = Signal(int)            # pattern index

    def __init__(self, project, engine, parent=None):
        super().__init__(parent)
        self.project = project
        self.engine = engine
        self.snap = 16                       # steps
        self.bar_w = 92                      # px per bar (zoom)
        self.selected: Clip | None = None
        self.playhead_step = None
        self._drag = None                    # (clip, grab_offset_steps)
        self._resize = None                  # (clip,)
        self._drag_moved = False
        self.setMouseTracking(True)
        self._resize_canvas()

    # ------------------------------------------------------------------
    @property
    def step_w(self):
        return self.bar_w / STEPS_PER_BAR

    def grid_width(self):
        return int(PLAYLIST_BARS * STEPS_PER_BAR * self.step_w) + 2

    def _resize_canvas(self):
        h = HEADER_H + PLAYLIST_TRACKS * ROW_H + 6
        self.setFixedSize(TRACK_HEAD_W + self.grid_width(), h)

    def set_bar_w(self, w: int):
        self.bar_w = w
        self._resize_canvas()
        self.update()

    # ------------------------------------------------------------------
    def _cell(self, x, y):
        step = int((x - TRACK_HEAD_W) // self.step_w)
        track = int((y - HEADER_H) // ROW_H)
        return max(0, step), track

    def _clip_at(self, step, track):
        for clip in reversed(self.project.clips):
            if clip.track == track and clip.start <= step < clip.start + clip.length:
                return clip
        return None

    def _overlaps(self, clip: Clip) -> bool:
        for c in self.project.clips:
            if c is clip or c.track != clip.track:
                continue
            if clip.start < c.start + c.length and c.start < clip.start + clip.length:
                return True
        return False

    def _clip_right_x(self, clip):
        return TRACK_HEAD_W + (clip.start + clip.length) * self.step_w

    def _on_clip_edge(self, x, y):
        """Return clip whose right edge is near (x, y), else None."""
        if y < HEADER_H or x < TRACK_HEAD_W:
            return None
        _step, track = self._cell(x, y)
        if not (0 <= track < PLAYLIST_TRACKS):
            return None
        for clip in reversed(self.project.clips):
            if clip.track != track:
                continue
            if abs(self._clip_right_x(clip) - x) <= EDGE:
                sw = TRACK_HEAD_W + clip.start * self.step_w
                if sw - 2 <= x <= self._clip_right_x(clip) + EDGE:
                    return clip
        return None

    # ------------------------------------------------------------------
    # painting
    # ------------------------------------------------------------------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        body_top = HEADER_H
        muted = self.project.track_muted
        gw = self.grid_width()

        # --- track lanes ------------------------------------------------
        for t in range(PLAYLIST_TRACKS):
            y = body_top + t * ROW_H
            lane = QColor("#14161c") if t % 2 == 0 else QColor("#111318")
            if t < len(muted) and muted[t]:
                lane = lane.darker(118)
            lane_wide = QColor(lane)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(lane_wide)
            p.drawRect(0, y, w, ROW_H)
        # ruler
        p.setBrush(QColor("#0e1014"))
        p.drawRect(0, 0, w, HEADER_H)
        p.setPen(QPen(QColor("#1e222a"), 1))
        p.drawLine(0, HEADER_H - 1, w, HEADER_H - 1)

        # --- grid -------------------------------------------------------
        total_steps = PLAYLIST_BARS * STEPS_PER_BAR
        from PySide6.QtGui import QFont
        font = p.font()
        for s in range(total_steps + 1):
            x = int(TRACK_HEAD_W + s * self.step_w)
            if s % 16 == 0:
                p.setPen(QPen(QColor("#262a33"), 1))
                p.drawLine(x, 0, x, h)
                bold = (s // 16) % 4 == 0
                font.setBold(bold)
                p.setFont(font)
                p.setPen(QColor("#8b93a5") if bold else QColor("#5c6373"))
                p.drawText(x + 5, 17, str(s // 16 + 1))
            elif s % 4 == 0:
                p.setPen(QPen(QColor("#1c2029"), 1))
                p.drawLine(x, body_top, x, h)
        font.setBold(False)
        p.setFont(font)

        # --- clips -------------------------------------------------------
        for clip in self.project.clips:
            x = TRACK_HEAD_W + clip.start * self.step_w
            y = body_top + clip.track * ROW_H + 5
            cw = clip.length * self.step_w - 3
            chh = ROW_H - 10
            base = QColor(PATTERN_COLORS[clip.pattern % len(PATTERN_COLORS)])
            is_muted = 0 <= clip.track < len(muted) and muted[clip.track]
            fill = QColor(base)
            fill.setAlpha(13 if is_muted else
                          (96 if clip is self.selected else 46))
            border = QColor(base)
            if is_muted:
                border.setAlpha(90)
            p.setBrush(fill)
            p.setPen(QPen(border if clip is not self.selected
                          else base.lighter(140),
                          1 if is_muted else
                          (2 if clip is self.selected else 1)))
            p.drawRoundedRect(int(x), int(y), int(cw), int(chh), 7, 7)
            # left accent stripe
            stripe = QColor(base)
            stripe.setAlpha(120 if not is_muted else 60)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(stripe)
            p.drawRoundedRect(int(x) + 1, int(y) + 4, 3, int(chh) - 8, 2, 2)
            # label
            p.setPen(QColor("#c9d5ea") if not is_muted else QColor("#5c6373"))
            pat_name = self.project.patterns[clip.pattern].name
            p.drawText(int(x) + 9, int(y) + 1, int(cw) - 14, int(chh) - 2,
                       Qt.AlignmentFlag.AlignVCenter,
                       f"P{clip.pattern + 1} · {pat_name}")
            # resize grip dots on the right edge
            if clip is self.selected:
                p.setBrush(base.lighter(160))
                cx = int(x + cw) - 5
                for i in range(3):
                    p.drawEllipse(QPoint(cx, int(y) + int(chh) // 2 - 6 + 6 * i),
                                  1, 1)

        # --- track headers (fixed left column) ---------------------------
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0e1014"))
        p.drawRect(0, 0, TRACK_HEAD_W, h)
        p.setPen(QPen(QColor("#1e222a"), 1))
        p.drawLine(TRACK_HEAD_W - 1, 0, TRACK_HEAD_W - 1, h)
        for t in range(PLAYLIST_TRACKS):
            y = body_top + t * ROW_H
            is_muted = t < len(muted) and muted[t]
            p.setPen(QPen(QColor("#16181d"), 1))
            p.drawLine(0, y + ROW_H - 1, TRACK_HEAD_W - 1, y + ROW_H - 1)
            p.setPen(QColor("#5c6373") if is_muted else QColor("#8b93a5"))
            p.drawText(12, y, TRACK_HEAD_W - 52, ROW_H,
                       Qt.AlignmentFlag.AlignVCenter, f"Track {t + 1}")
            # mute LED
            cx = TRACK_HEAD_W - 30
            cy = y + ROW_H // 2
            p.setPen(QPen(QColor("#a83c3c") if is_muted else QColor("#2c3140"), 1))
            p.setBrush(QColor("#5a2727") if is_muted else QColor("#1a1e25"))
            p.drawRoundedRect(cx - 9, cy - 9, 18, 18, 9, 9)
            if is_muted:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#ef5350"))
                p.drawEllipse(QPoint(cx, cy), 3, 3)
                p.setPen(QColor("#d98c8c"))
                p.drawText(cx - 20, y, 18, ROW_H,
                           Qt.AlignmentFlag.AlignVCenter, "M")
        # header label
        p.setPen(QColor("#5c6373"))
        p.drawText(12, 0, TRACK_HEAD_W - 12, HEADER_H - 1,
                   Qt.AlignmentFlag.AlignVCenter, "Tracks")

        # --- playhead -----------------------------------------------------
        if self.playhead_step is not None:
            x = int(TRACK_HEAD_W + self.playhead_step * self.step_w)
            p.setPen(QPen(QColor("#8fb6ff"), 2))
            p.drawLine(x, 8, x, h)
            glow = QColor("#4d8dff")
            glow.setAlpha(70)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRect(x - 3, 8, 6, h - 8)
            p.setBrush(QColor("#8fb6ff"))
            tip = QPolygon([QPoint(x - 5, 8), QPoint(x + 5, 8),
                            QPoint(x, 16)])
            p.drawPolygon(tip)
        p.end()

    # ------------------------------------------------------------------
    # interaction
    # ------------------------------------------------------------------
    def mousePressEvent(self, e):
        x, y = e.position().x(), e.position().y()

        # ruler click -> seek
        if y < HEADER_H and x >= TRACK_HEAD_W:
            if e.button() == Qt.MouseButton.LeftButton:
                step, _ = self._cell(x, HEADER_H + 1)
                self.seekRequested.emit(step)
                self.playhead_step = step
                self.update()
            return

        # track header clicks -> mute toggle
        if x < TRACK_HEAD_W:
            _s, track = self._cell(TRACK_HEAD_W + 1, y)
            if 0 <= track < PLAYLIST_TRACKS and \
                    e.button() == Qt.MouseButton.LeftButton:
                cx = TRACK_HEAD_W - 30
                cy = HEADER_H + track * ROW_H + ROW_H // 2
                if abs(x - cx) <= 12 and abs(y - cy) <= 12:
                    self.aboutToEdit.emit()
                    self.project.track_muted[track] = \
                        not self.project.track_muted[track]
                    self.clipsChanged.emit()
                    self.update()
            return

        step, track = self._cell(x, y)
        if not (0 <= track < PLAYLIST_TRACKS):
            return
        with self.engine.lock:
            hit = self._clip_at(step, track)
            if e.button() == Qt.MouseButton.RightButton:
                if hit is not None:
                    self.selected = hit
                    self.update()
                    self._clip_menu(hit, e.globalPosition().toPoint())
                return
            if e.button() != Qt.MouseButton.LeftButton:
                return

            edge = self._on_clip_edge(x, y)
            if edge is not None:
                self.selected = edge
                self._resize = edge
                self._orig_len = edge.length
                self.update()
                return

            if hit is not None:
                self.selected = hit
                self._drag = (hit, step - hit.start)
                self._drag_moved = False
                self.update()
            else:
                self.aboutToEdit.emit()
                start = (step // self.snap) * self.snap
                pat_idx = self.project.current_pattern
                pat = self.project.patterns[pat_idx]
                clip = Clip(pattern=pat_idx, track=track,
                            start=start, length=pat.length)
                self.project.clips.append(clip)
                self.selected = clip
                for c in list(self.project.clips):
                    if c is not clip and c.track == track and \
                            clip.start < c.start + c.length and \
                            c.start < clip.start + clip.length:
                        self.project.clips.remove(c)
                self.clipsChanged.emit()
                self.update()

    def _clip_menu(self, clip: Clip, pos):
        menu = QMenu(self)
        act_dup = menu.addAction("Duplicate")
        act_open = menu.addAction("Open pattern P%d" % (clip.pattern + 1))
        menu.addSeparator()
        act_del = menu.addAction("Delete")
        chosen = menu.exec(pos)
        if chosen is act_dup:
            self.aboutToEdit.emit()
            with self.engine.lock:
                copy = Clip(pattern=clip.pattern, track=clip.track,
                            start=clip.start + clip.length, length=clip.length)
                if not self._overlaps(copy):
                    self.project.clips.append(copy)
                    self.selected = copy
            self.clipsChanged.emit()
            self.update()
        elif chosen is act_open:
            self.openPattern.emit(clip.pattern)
        elif chosen is act_del:
            self.delete_clip(clip)

    def mouseMoveEvent(self, e):
        x, y = e.position().x(), e.position().y()
        step, track = self._cell(x, y)

        if self._resize is not None:
            clip = self._resize
            new_len = max(4, ((step - clip.start + self.snap - 1)
                              // self.snap) * self.snap)
            if new_len != clip.length:
                with self.engine.lock:
                    old = clip.length
                    clip.length = new_len
                    if self._overlaps(clip):
                        clip.length = old
                    else:
                        if not self._resizing_started:
                            self.aboutToEdit.emit()
                            self._resizing_started = True
                self.update()
                if clip.length != old:
                    self.clipsChanged.emit()
            return

        if self._drag is not None:
            clip, grab = self._drag
            if not (0 <= track < PLAYLIST_TRACKS):
                return
            if not self._drag_moved:
                self.aboutToEdit.emit()
                self._drag_moved = True
            new_start = max(0, ((step - grab) // self.snap) * self.snap)
            with self.engine.lock:
                old_start, old_track = clip.start, clip.track
                clip.start, clip.track = new_start, track
                if self._overlaps(clip):
                    clip.start, clip.track = old_start, old_track
            self.update()
            if (clip.start, clip.track) != (old_start, old_track):
                self.clipsChanged.emit()
            return

        # hover feedback: resize cursor near clip right edges
        if self._on_clip_edge(x, y) is not None:
            if self.cursor().shape() != Qt.CursorShape.SizeHorCursor:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            if self.cursor().shape() != Qt.CursorShape.ArrowCursor:
                self.unsetCursor()

    def mouseReleaseEvent(self, _e):
        self._drag = None
        self._resize = None
        self._resizing_started = False

    _resizing_started = False

    # ------------------------------------------------------------------
    def delete_clip(self, clip: Clip):
        self.aboutToEdit.emit()
        with self.engine.lock:
            if clip in self.project.clips:
                self.project.clips.remove(clip)
        if self.selected is clip:
            self.selected = None
        self.clipsChanged.emit()
        self.update()

    def delete_selected(self):
        if self.selected is not None:
            self.delete_clip(self.selected)

    def add_clip(self, pattern: int, track: int, start: int, length: int):
        """Programmatic placement (used by tests)."""
        with self.engine.lock:
            clip = Clip(pattern=pattern, track=track, start=start,
                        length=length)
            self.project.clips.append(clip)
        self.clipsChanged.emit()
        self.update()
        return clip

    def set_playhead(self, step):
        if step != self.playhead_step:
            self.playhead_step = step
            self.update()


class PlaylistPanel(QWidget):
    clipsChanged = Signal()
    seekRequested = Signal(int)
    openPattern = Signal(int)

    def __init__(self, project, engine, parent=None):
        super().__init__(parent)
        self.project = project
        self.engine = engine

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("background:#101216; border-bottom:1px solid #1e222a;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)
        lbl = QLabel("Snap")
        lbl.setObjectName("dim")
        h.addWidget(lbl)
        self.snap_combo = QComboBox()
        self.snap_combo.setFixedHeight(30)
        for label, steps in (("Bar", 16), ("Beat", 4), ("Step", 1)):
            self.snap_combo.addItem(label, steps)
        self.snap_combo.currentIndexChanged.connect(
            lambda _i: setattr(self.canvas, "snap",
                               int(self.snap_combo.currentData())))
        h.addWidget(self.snap_combo)

        zl = QLabel("Zoom")
        zl.setObjectName("dim")
        h.addWidget(zl)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setFixedHeight(30)
        for label, w in (("60 %", 56), ("100 %", 92), ("150 %", 138),
                         ("220 %", 200)):
            self.zoom_combo.addItem(label, w)
        self.zoom_combo.setCurrentIndex(1)
        self.zoom_combo.currentIndexChanged.connect(
            lambda _i: self.canvas.set_bar_w(int(self.zoom_combo.currentData())))
        h.addWidget(self.zoom_combo)

        self.placing = QLabel()
        self.placing.setObjectName("dim")
        h.addWidget(self.placing)
        self.update_placing()

        self.btn_del = QPushButton("Delete clip")
        self.btn_del.setProperty("ghost", True)
        self.btn_del.setFixedHeight(30)
        self.btn_del.clicked.connect(lambda: self.canvas.delete_selected())
        h.addWidget(self.btn_del)

        hint = QLabel("click ruler to seek · drag clip edge to resize · "
                      "right-click for clip menu")
        hint.setObjectName("dimmer")
        h.addStretch(1)
        h.addWidget(hint)
        lay.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.canvas = PlaylistCanvas(project, engine)
        self.canvas.clipsChanged.connect(self.clipsChanged)
        self.canvas.seekRequested.connect(self.seekRequested)
        self.canvas.openPattern.connect(self.openPattern)
        self.scroll.setWidget(self.canvas)
        lay.addWidget(self.scroll, 1)

    def set_playhead(self, step):
        self.canvas.set_playhead(step)
        if step is not None and self.width() > 0:
            x = TRACK_HEAD_W + step * self.canvas.step_w
            sb = self.scroll.horizontalScrollBar()
            vw = self.scroll.viewport().width()
            if x < sb.value() + TRACK_HEAD_W + 12 or \
                    x > sb.value() + vw - 90:
                sb.setValue(max(0, int(x - TRACK_HEAD_W - 90)))

    # ------------------------------------------------------------------
    def update_placing(self):
        idx = self.project.current_pattern
        color = PATTERN_COLORS[idx % len(PATTERN_COLORS)]
        self.placing.setText(
            f"Placing: <b style='color:{color}'>P{idx + 1} · "
            f"{self.project.patterns[idx].name}</b> "
            f"<span style='color:#5c6373'>(pick in Channel Rack)</span>")

    def refresh(self):
        self.canvas._resize_canvas()
        self.update_placing()
        self.canvas.update()
