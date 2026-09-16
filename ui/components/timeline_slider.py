from PyQt6.QtWidgets import QSlider, QToolTip
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint, QRect, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient, QPolygon, QMouseEvent, QFont


class SIVTimelineSlider(QSlider):
    """Slider temporale personalizzato con marker per capitoli/manovre SIV,
    click-to-seek istantaneo e live-scrubbing fluido a frame continuo.
    """
    seek_requested = pyqtSignal(int)      # Emette il timestamp in millisecondi per il player
    drag_started = pyqtSignal()
    drag_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMouseTracking(True)
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._chapters = []
        self.is_dragging = False
        self._hovered_chapter = None
        self._target_seek_val = 0

        # Timer di throttling a 25 ms (~40 fps) per non sovraccaricare il decoder WMF durante il drag
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.setInterval(25)
        self._throttle_timer.timeout.connect(self._on_throttle_timeout)

    def set_chapters(self, chapters: list):
        """Imposta la lista dei capitoli/manovre [{'start': s, 'end': s, 'title': str}]."""
        self._chapters = chapters if chapters else []
        self.update()

    def _on_throttle_timeout(self):
        if self.is_dragging:
            self.seek_requested.emit(self._target_seek_val)

    def _get_track_rect(self) -> QRect:
        margin = 10
        h = 8
        y = (self.height() - h) // 2
        w = max(1, self.width() - 2 * margin)
        return QRect(margin, y, w, h)

    def _val_to_x(self, val: int, track: QRect) -> int:
        rng = self.maximum() - self.minimum()
        if rng <= 0:
            return track.left()
        pct = max(0.0, min(1.0, (val - self.minimum()) / rng))
        return int(track.left() + pct * (track.width() - 1))

    def _pos_to_val(self, x: int) -> int:
        track = self._get_track_rect()
        usable_w = max(1, track.width() - 1)
        pct = max(0.0, min(1.0, (x - track.left()) / usable_w))
        rng = self.maximum() - self.minimum()
        return int(self.minimum() + pct * rng)

    def _find_chapter_near_pos(self, x: int, tolerance: int = 8):
        track = self._get_track_rect()
        rng = self.maximum() - self.minimum()
        if rng <= 0:
            return None

        best_ch = None
        best_dist = 9999
        for ch in self._chapters:
            try:
                start_ms = int(float(ch.get("start", 0)) * 1000)
            except (ValueError, TypeError):
                continue
            ch_x = self._val_to_x(start_ms, track)
            dist = abs(ch_x - x)
            if dist <= tolerance and dist < best_dist:
                best_dist = dist
                best_ch = ch
        return best_ch

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            track = self._get_track_rect()
            x = event.pos().x()

            # Se si clicca in prossimità di un marker, aggancia (snap) esattamente all'inizio della manovra
            near_ch = self._find_chapter_near_pos(x, tolerance=8)
            if near_ch:
                val = int(near_ch.get("start", 0) * 1000)
            else:
                val = self._pos_to_val(x)

            self.setValue(val)
            self._target_seek_val = val
            self.drag_started.emit()
            self.seek_requested.emit(val)
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        x = event.pos().x()
        track = self._get_track_rect()

        if self.is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            val = self._pos_to_val(x)
            self.setValue(val)
            self._target_seek_val = val

            # Throttling continuo della richiesta di seek durante il drag
            if not self._throttle_timer.isActive():
                self._throttle_timer.start()

            # Tooltip con minutaggio corrente durante il trascinamento
            dur_s = self.maximum() // 1000
            curr_s = val // 1000
            near_ch = self._find_chapter_near_pos(x, tolerance=8)
            if near_ch:
                t_str = f"🎯 {curr_s//60:02d}:{curr_s%60:02d} - {near_ch.get('title', '')}"
            else:
                t_str = f"⏱ {curr_s//60:02d}:{curr_s%60:02d} / {dur_s//60:02d}:{dur_s%60:02d}"
            QToolTip.showText(event.globalPosition().toPoint(), t_str, self)

            self.update()
            event.accept()
        else:
            # Hovering senza drag: controllo se si passa su un marker manovra
            near_ch = self._find_chapter_near_pos(x, tolerance=7)
            if near_ch != self._hovered_chapter:
                self._hovered_chapter = near_ch
                self.update()

            if near_ch:
                st_s = int(near_ch.get("start", 0))
                time_str = f"{st_s//60:02d}:{st_s%60:02d}"
                title = near_ch.get("title", "Manovra")
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"🎯 <b>{time_str}</b> - {title}",
                    self
                )
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            if self._throttle_timer.isActive():
                self._throttle_timer.stop()

            # Seek definitivo al rilascio per garantire frame esatto
            self.seek_requested.emit(self.value())
            self.drag_ended.emit()
            self.update()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self._hovered_chapter is not None:
            self._hovered_chapter = None
            self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        self.seek_requested.emit(self.value())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = self._get_track_rect()
        thumb_x = self._val_to_x(self.value(), track)

        # 1. Traccia di sfondo (Groove non riprodotto)
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.setBrush(QBrush(QColor("#131b2e")))
        painter.drawRoundedRect(track, 4.0, 4.0)

        # 2. Barra di progresso (Porzione già riprodotta)
        if thumb_x > track.left():
            progress_rect = QRect(track.left(), track.top(), thumb_x - track.left(), track.height())
            grad = QLinearGradient(track.left(), 0, track.right(), 0)
            grad.setColorAt(0.0, QColor("#0284c7"))
            grad.setColorAt(1.0, QColor("#06b6d4"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(progress_rect, 4.0, 4.0)

        # 3. Marker delle manovre (Capitoli SIV)
        track_center_y = track.center().y()
        for ch in self._chapters:
            try:
                start_ms = int(float(ch.get("start", 0)) * 1000)
            except (ValueError, TypeError):
                continue
            ch_x = self._val_to_x(start_ms, track)

            # Evita di disegnare fuori dai margini
            if ch_x < track.left() or ch_x > track.right():
                continue

            is_hovered = (ch == self._hovered_chapter)

            # Tacca verticale (Tick) che interseca la barra
            tick_h = 16 if is_hovered else 12
            tick_w = 4 if is_hovered else 3
            tick_top = track_center_y - (tick_h // 2)

            tick_color = QColor("#fbbf24") if is_hovered else QColor("#f59e0b")
            painter.setPen(QPen(QColor("#0f172a"), 1))
            painter.setBrush(QBrush(tick_color))
            painter.drawRoundedRect(QRectF(ch_x - tick_w / 2, tick_top, tick_w, tick_h), 1.5, 1.5)

            # Pin / Triangolino indicatore in cima alla traccia per massima leggibilità
            pin_y = track.top() - 3
            pin = QPolygon([
                QPoint(ch_x - 3, pin_y - 4),
                QPoint(ch_x + 3, pin_y - 4),
                QPoint(ch_x, pin_y)
            ])
            painter.setPen(QPen(QColor("#0f172a"), 1))
            painter.setBrush(QBrush(tick_color))
            painter.drawPolygon(pin)

        # 4. Indicatore di scorrimento (Thumb / Cursore)
        thumb_r = 7 if not self.is_dragging else 8
        thumb_cy = track.center().y()

        # Anello esterno glow se in drag
        if self.is_dragging:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(6, 182, 212, 60)))
            painter.drawEllipse(QPoint(thumb_x, thumb_cy), thumb_r + 4, thumb_r + 4)

        # Bordo thumb
        painter.setPen(QPen(QColor("#38bdf8"), 2))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(QPoint(thumb_x, thumb_cy), thumb_r, thumb_r)

        painter.end()
