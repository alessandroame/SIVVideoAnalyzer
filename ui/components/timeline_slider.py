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
    keyframe_delete_requested = pyqtSignal(str, float)  # (subject 'pilot'|'wing', t_sec)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMouseTracking(True)
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._chapters = []
        self._keyframes = {"pilot": [], "wing": []}
        self._correction_intervals = {"pilot": [], "wing": []}
        self.is_dragging = False
        self._hovered_chapter = None
        self._hovered_keyframe = None
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

    def set_keyframes(self, keyframes: dict):
        """Imposta i keyframe di tracciamento {'pilot': [...], 'wing': [...]}."""
        self._keyframes = keyframes if isinstance(keyframes, dict) else {"pilot": [], "wing": []}
        self.update()

    def set_correction_intervals(self, intervals: dict):
        """Imposta gli intervalli temporali attivi di correzione per pilota e vela."""
        self._correction_intervals = intervals if isinstance(intervals, dict) else {"pilot": [], "wing": []}
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

    def _find_keyframe_near_pos(self, x: int, tolerance: int = 12):
        track = self._get_track_rect()
        rng = self.maximum() - self.minimum()
        if rng <= 0:
            return None

        best_kf = None
        best_dist = 9999
        for subject in ["pilot", "wing"]:
            for kf in self._keyframes.get(subject, []):
                try:
                    t_ms = int(float(kf.get("t", 0.0)) * 1000)
                except (ValueError, TypeError):
                    continue
                kf_x = self._val_to_x(t_ms, track)
                dist = abs(kf_x - x)
                if dist <= tolerance and dist < best_dist:
                    best_dist = dist
                    best_kf = (subject, kf)
        return best_kf

    def mousePressEvent(self, event: QMouseEvent):
        track = self._get_track_rect()
        x = event.pos().x()

        if event.button() == Qt.MouseButton.RightButton:
            # Clic con il tasto destro del mouse: elimina direttamente il keyframe
            near_kf = self._find_keyframe_near_pos(x, tolerance=12)
            if near_kf:
                subj, kf = near_kf
                t_s = float(kf.get("t", 0.0))
                self.keyframe_delete_requested.emit(subj, t_s)
                lbl = "Pilota" if subj == "pilot" else "Vela"
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"🗑 <b>Keyframe {lbl} eliminato</b>",
                    self
                )
                self.update()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True

            # Se si clicca in prossimità di un keyframe o di un capitolo, aggancia (snap)
            near_kf = self._find_keyframe_near_pos(x, tolerance=12)
            near_ch = self._find_chapter_near_pos(x, tolerance=8)
            if near_kf:
                val = int(near_kf[1].get("t", 0.0) * 1000)
            elif near_ch:
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
            near_kf = self._find_keyframe_near_pos(x, tolerance=12)
            near_ch = self._find_chapter_near_pos(x, tolerance=8)
            if near_kf:
                subj, kf = near_kf
                lbl = "Pilota" if subj == "pilot" else "Vela"
                t_str = f"◆ {curr_s//60:02d}:{curr_s%60:02d} - Keyframe {lbl}"
            elif near_ch:
                t_str = f"🎯 {curr_s//60:02d}:{curr_s%60:02d} - {near_ch.get('title', '')}"
            else:
                t_str = f"⏱ {curr_s//60:02d}:{curr_s%60:02d} / {dur_s//60:02d}:{dur_s%60:02d}"
            QToolTip.showText(event.globalPosition().toPoint(), t_str, self)

            self.update()
            event.accept()
        else:
            # Hovering senza drag: controllo se si passa su un keyframe o su un marker manovra
            near_kf = self._find_keyframe_near_pos(x, tolerance=10)
            near_ch = self._find_chapter_near_pos(x, tolerance=7)
            if near_kf != self._hovered_keyframe or near_ch != self._hovered_chapter:
                self._hovered_keyframe = near_kf
                self._hovered_chapter = near_ch
                self.update()

            if near_kf:
                subj, kf = near_kf
                t_s = float(kf.get("t", 0.0))
                w_s = float(kf.get("window", 2.0))
                lbl = "Pilota" if subj == "pilot" else "Vela"
                time_str = f"{int(t_s)//60:02d}:{t_s%60:04.1f}"
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"◆ <b>Keyframe {lbl}</b> ({time_str})<br>Finestra correzione: ±{w_s:.1f}s<br><span style='color:#94a3b8; font-size:10px;'>Clicca col tasto destro per eliminare</span>",
                    self
                )

            elif near_ch:
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

        # 4. Fasce delle Finestre di Correzione e Fade (Pilota / Vela)
        for subject, base_rgb, border_col in [
            ("wing", (245, 158, 11), QColor(245, 158, 11, 140)),
            ("pilot", (6, 182, 212), QColor(6, 182, 212, 140))
        ]:
            for interval in self._correction_intervals.get(subject, []):
                try:
                    st_ms = int(float(interval.get("start", 0.0)) * 1000)
                    en_ms = int(float(interval.get("end", 0.0)) * 1000)
                except (ValueError, TypeError):
                    continue
                x_st = self._val_to_x(st_ms, track)
                x_en = self._val_to_x(en_ms, track)
                x_st = max(track.left(), min(track.right(), x_st))
                x_en = max(track.left(), min(track.right(), x_en))
                if x_en > x_st + 1:
                    w_rect = QRect(x_st, track.top() - 1, x_en - x_st, track.height() + 2)
                    r, g, b = base_rgb
                    grad = QLinearGradient(x_st, 0, x_en, 0)
                    grad.setColorAt(0.0, QColor(r, g, b, 20))
                    grad.setColorAt(0.5, QColor(r, g, b, 90))
                    grad.setColorAt(1.0, QColor(r, g, b, 20))
                    painter.setPen(QPen(border_col, 1, Qt.PenStyle.DotLine))
                    painter.setBrush(QBrush(grad))
                    painter.drawRoundedRect(w_rect, 3.0, 3.0)

        # 5. Marker Keyframe di Tracciamento (Diamanti ◆)
        for subject, color_hex in [("wing", "#f59e0b"), ("pilot", "#06b6d4")]:
            for kf in self._keyframes.get(subject, []):
                try:
                    kf_ms = int(float(kf.get("t", 0.0)) * 1000)
                except (ValueError, TypeError):
                    continue
                kf_x = self._val_to_x(kf_ms, track)
                if kf_x < track.left() or kf_x > track.right():
                    continue

                is_kf_hovered = (self._hovered_keyframe and self._hovered_keyframe[1] == kf)
                d_size = 6 if is_kf_hovered else 4.5

                diamond = QPolygon([
                    QPoint(kf_x, int(track_center_y - d_size)),
                    QPoint(int(kf_x + d_size), int(track_center_y)),
                    QPoint(kf_x, int(track_center_y + d_size)),
                    QPoint(int(kf_x - d_size), int(track_center_y))
                ])
                painter.setPen(QPen(QColor("#0f172a"), 1.2))
                painter.setBrush(QBrush(QColor(color_hex)))
                painter.drawPolygon(diamond)

        # 5. Indicatore di scorrimento (Thumb / Cursore)
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
