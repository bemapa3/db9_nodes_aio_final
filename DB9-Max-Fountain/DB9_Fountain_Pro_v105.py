import pymxs
from PySide2 import QtWidgets, QtCore, QtGui
import math, colorsys, copy, json, os, random

rt = pymxs.runtime


# ==============================================================================
# FLOW LAYOUT — wraps widgets to next row
# ==============================================================================
class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=4, spacing=4):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        row_h = 0
        for item in self._items:
            w = item.widget()
            if w is None:
                continue
            item_w = item.sizeHint().width()
            item_h = item.sizeHint().height()
            if x + item_w > effective.right() + 1 and row_h > 0:
                x = effective.x()
                y = y + row_h + self._spacing
                row_h = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))
            x = x + item_w + self._spacing
            row_h = max(row_h, item_h)
        return y + row_h - rect.y() + m.bottom()


# ==============================================================================
# KEYFRAME TIMELINE WIDGET
# ==============================================================================
class KeyframeTimelineWidget(QtWidgets.QWidget):
    key_deleted = QtCore.Signal(str, int)  # (nid, frame)

    RULER_H = 22
    ROW_H = 20
    LEFT_MARGIN = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._frame_range = (0, 100)
        self._visible_range = (0, 100)
        self._current_frame = 0
        self._key_data = {}
        self._dragging = False
        self._pan_dragging = False
        self._pan_last_x = 0
        self._selected_key = None  # Luu tru (nid, frame)
        self.setMouseTracking(True)

    def set_keys(self, data):
        self._key_data = data
        rows = max(len(data), 1)
        self.setMinimumHeight(self.RULER_H + rows * self.ROW_H + 10)
        self.update()

    def set_current_frame(self, f):
        self._current_frame = f
        self.update()

    def set_frame_range(self, start, end):
        self._frame_range = (start, end)
        self._visible_range = (start, end)
        self.update()

    def _frame_to_x(self, f):
        s, e = self._visible_range
        span = max(1, e - s)
        track_w = self.width() - self.LEFT_MARGIN - 10
        return self.LEFT_MARGIN + (f - s) / span * track_w

    def _x_to_frame(self, x):
        s, e = self._visible_range
        span = max(1, e - s)
        track_w = self.width() - self.LEFT_MARGIN - 10
        t = (x - self.LEFT_MARGIN) / max(1, track_w)
        return int(s + t * span)

    def _set_max_frame(self, frame):
        try:
            rt.sliderTime = int(frame)
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QtGui.QColor(8, 8, 14))

        s, e = self._visible_range
        span = max(1, e - s)
        track_w = w - self.LEFT_MARGIN - 10

        # Ruler
        painter.setPen(QtGui.QPen(QtGui.QColor(50, 50, 70), 1))
        ruler_y = self.RULER_H
        painter.drawLine(self.LEFT_MARGIN, ruler_y, w - 10, ruler_y)
        step = max(1, span // 20)
        font = painter.font()
        font.setPixelSize(9)
        painter.setFont(font)
        for f in range(s, e + 1, step):
            fx = self._frame_to_x(f)
            painter.setPen(QtGui.QPen(QtGui.QColor(50, 50, 70), 1))
            painter.drawLine(int(fx), ruler_y - 6, int(fx), ruler_y)
            painter.setPen(QtGui.QPen(QtGui.QColor(100, 100, 130), 1))
            painter.drawText(int(fx) - 12, ruler_y - 8, str(f))

        # Rows
        row_i = 0
        for nid, info in self._key_data.items():
            ry = self.RULER_H + 4 + row_i * self.ROW_H
            cr, cg, cb = info.get('color', (100, 180, 255))
            painter.fillRect(self.LEFT_MARGIN, ry, track_w, self.ROW_H - 2,
                             QtGui.QColor(cr, cg, cb, 15))
            painter.setPen(QtGui.QPen(QtGui.QColor(cr, cg, cb), 1))
            font2 = painter.font()
            font2.setPixelSize(10)
            font2.setBold(True)
            painter.setFont(font2)
            name_lbl = info.get('name', nid[:12])
            painter.drawText(4, ry + 13, name_lbl)
            
            for kf in info.get('keys', []):
                kx = self._frame_to_x(kf)
                if self.LEFT_MARGIN <= kx <= w - 10:
                    ky = ry + self.ROW_H // 2
                    diamond = QtGui.QPolygonF([
                        QtCore.QPointF(kx, ky - 5), QtCore.QPointF(kx + 4, ky),
                        QtCore.QPointF(kx, ky + 5), QtCore.QPointF(kx - 4, ky),
                    ])
                    # To mau trang/do neu dang duoc chon
                    if self._selected_key == (nid, kf):
                        painter.setBrush(QtGui.QColor(255, 255, 255, 255))
                        painter.setPen(QtGui.QPen(QtGui.QColor(255, 50, 50), 1))
                    else:
                        painter.setBrush(QtGui.QColor(cr, cg, cb, 220))
                        painter.setPen(QtCore.Qt.NoPen)
                        
                    painter.drawPolygon(diamond)
                    
            painter.setPen(QtGui.QPen(QtGui.QColor(30, 30, 45), 1))
            painter.drawLine(self.LEFT_MARGIN, ry + self.ROW_H - 1, w - 10, ry + self.ROW_H - 1)
            row_i += 1

        # Playhead
        px = self._frame_to_x(self._current_frame)
        if self.LEFT_MARGIN <= px <= w - 10:
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 40, 40), 2))
            painter.drawLine(int(px), 0, int(px), h)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 80, 80), 1))
            font3 = painter.font()
            font3.setPixelSize(10)
            font3.setBold(True)
            painter.setFont(font3)
            painter.drawText(int(px) + 3, 12, str(self._current_frame))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_dragging = True
            self._pan_last_x = event.pos().x()
            event.accept()
            return
        if event.button() == QtCore.Qt.LeftButton:
            # Uu tien check xem co click trung keyframe nao khong
            hit = False
            row_i = 0
            for nid, info in self._key_data.items():
                ry = self.RULER_H + 4 + row_i * self.ROW_H
                ky = ry + self.ROW_H // 2
                for kf in info.get('keys', []):
                    kx = self._frame_to_x(kf)
                    if abs(event.pos().x() - kx) < 7 and abs(event.pos().y() - ky) < 7:
                        self._selected_key = (nid, kf)
                        hit = True
                        self.update()
                        break
                if hit: break
                row_i += 1
                
            if hit:
                # Neu trung keyframe, chi nhay timeframe den do
                try:
                    self._set_max_frame(self._selected_key[1])
                except Exception: pass
                return
                
            # Khong trung key -> bam de scrub timeline binh thuong
            self._selected_key = None
            f = self._x_to_frame(event.pos().x())
            s, e = self._visible_range
            f = max(s, min(e, f))
            self._dragging = True
            try:
                self._set_max_frame(f)
            except Exception:
                pass
            self.update()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_pan_dragging') and self._pan_dragging:
            delta_x = event.pos().x() - self._pan_last_x
            self._pan_last_x = event.pos().x()
            vstart, vend = self._visible_range
            span = vend - vstart
            track_w = self.width() - self.LEFT_MARGIN - 10
            if track_w > 0:
                delta_f = -delta_x * span / track_w
                fstart, fend = self._frame_range
                new_start = max(fstart, min(vstart + delta_f, fend - span))
                new_end = new_start + span
                self._visible_range = (new_start, new_end)
                self.update()
            return
        if self._dragging:
            f = self._x_to_frame(event.pos().x())
            s, e = self._visible_range
            f = max(s, min(e, f))
            try:
                self._set_max_frame(f)
            except Exception:
                pass

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_dragging = False
            event.accept()
            return
        self._dragging = False

    def wheelEvent(self, event):
        s, e = self._visible_range
        span = e - s
        delta = event.angleDelta().y()
        fs, fe = self._frame_range
        if delta > 0:
            shrink = max(1, span // 10)
            new_s = max(fs, s + shrink)
            new_e = min(fe, max(new_s + 1, e - shrink))
            self._visible_range = (new_s, new_e)
        else:
            grow = max(1, span // 8)
            new_s = max(fs, s - grow)
            new_e = min(fe, e + grow)
            self._visible_range = (new_s, new_e)
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            if self._selected_key:
                self.key_deleted.emit(self._selected_key[0], self._selected_key[1])
                self._selected_key = None
        else:
            super().keyPressEvent(event)


# ==============================================================================
# SPLASH SCREEN
# ==============================================================================
class SplashScreen(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(480, 300)
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            sg = screen.geometry()
            self.move(sg.x() + (sg.width() - 480) // 2,
                      sg.y() + (sg.height() - 300) // 2)
        self._logo_pixmap = None
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db9_logo.jpg")
        if not os.path.isfile(logo_path):
            logo_path = "/root/.openclaw/media/inbound/Logo---d1e0b41a-c96c-4406-9da4-c76305011c96.jpg"
        if os.path.isfile(logo_path):
            px = QtGui.QPixmap(logo_path)
            if not px.isNull():
                self._logo_pixmap = px.scaled(120, 120, QtCore.Qt.KeepAspectRatio,
                                              QtCore.Qt.SmoothTransformation)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        grad = QtGui.QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QtGui.QColor(18, 18, 40, 240))
        grad.setColorAt(0.5, QtGui.QColor(30, 25, 60, 245))
        grad.setColorAt(1, QtGui.QColor(10, 10, 25, 240))
        painter.setBrush(grad)
        painter.setPen(QtGui.QPen(QtGui.QColor(90, 90, 180, 150), 2))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 20, 20)
        y_offset = 30
        if self._logo_pixmap:
            lx = (self.width() - self._logo_pixmap.width()) // 2
            painter.drawPixmap(lx, y_offset, self._logo_pixmap)
            y_offset += self._logo_pixmap.height() + 15
        else:
            font_e = painter.font()
            font_e.setPixelSize(48)
            painter.setFont(font_e)
            painter.setPen(QtGui.QColor(100, 180, 255))
            painter.drawText(QtCore.QRect(0, y_offset, self.width(), 60),
                             QtCore.Qt.AlignCenter, "\u26f2")
            y_offset += 65
        font_t = painter.font()
        font_t.setPixelSize(28)
        font_t.setBold(True)
        font_t.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 4)
        painter.setFont(font_t)
        painter.setPen(QtGui.QColor(220, 220, 240))
        painter.drawText(QtCore.QRect(0, y_offset, self.width(), 40),
                         QtCore.Qt.AlignCenter, "DB9 FOUNTAIN PRO")
        y_offset += 45
        font_v = painter.font()
        font_v.setPixelSize(16)
        font_v.setBold(False)
        font_v.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 6)
        painter.setFont(font_v)
        painter.setPen(QtGui.QColor(120, 140, 255))
        painter.drawText(QtCore.QRect(0, y_offset, self.width(), 25),
                         QtCore.Qt.AlignCenter, "v104")
        y_offset += 30
        font_c = painter.font()
        font_c.setPixelSize(12)
        font_c.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 2)
        painter.setFont(font_c)
        painter.setPen(QtGui.QColor(140, 140, 160))
        painter.drawText(QtCore.QRect(0, y_offset, self.width(), 20),
                         QtCore.Qt.AlignCenter, "by DB9 Studio")
        painter.end()

    def mousePressEvent(self, event):
        self.close()

# ==============================================================================
# CLICKABLE VALUE LABEL
# ==============================================================================
class ClickableValueLabel(QtWidgets.QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setCursor(QtCore.Qt.IBeamCursor)
        self._editor = None
        self._slider = None
        self._nid = None
        self._attr = None
        self._main_win = None
        self._committing = False

    def link(self, slider, nid, attr, main_win):
        self._slider = slider
        self._nid = nid
        self._attr = attr
        self._main_win = main_win

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_dragging = True
            self._pan_last_x = event.pos().x()
            event.accept()
            return
        if event.button() == QtCore.Qt.LeftButton:
            if self._editor:
                return
            self._editor = QtWidgets.QLineEdit(self.text(), self.parent())
            self._editor.setGeometry(self.geometry())
            self._editor.setStyleSheet(
                "QLineEdit { background:#1a1a2e; color:#00e5ff; border:2px solid #00e5ff;"
                " border-radius:3px; font-size:11px; font-weight:bold; }"
            )
            self._editor.selectAll()
            self._editor.show()
            self._editor.setFocus()
            self._editor.returnPressed.connect(self._commit)
            self._editor.editingFinished.connect(self._commit)
        else:
            super().mousePressEvent(event)

    def _commit(self):
        if not self._editor or self._committing:
            return
        self._committing = True
        editor = self._editor
        self._editor = None
        try:
            val = int(float(editor.text().strip()))
            if self._slider:
                val = max(self._slider.minimum(), min(self._slider.maximum(), val))
                self._slider.setValue(val)
                self.setText(str(val))
            if self._main_win and self._nid is not None and self._attr is not None:
                self._main_win.sync_values(self._attr, self._nid, val)
        except (ValueError, AttributeError):
            pass
        editor.deleteLater()
        self._committing = False


# ==============================================================================
# BEZIER CURVE WIDGET
# ==============================================================================
class BezierCurveWidget(QtWidgets.QWidget):
    curve_updated = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self._pan_mode = False
        self._pan_start_y = None
        self._pan_start_pts = None
        self.pts = [
            {'x': 0.0, 'y': 0.0, 'smooth': False},
            {'x': 0.25, 'y': 0.5, 'smooth': True},
            {'x': 0.5, 'y': 1.0, 'smooth': True},
            {'x': 0.75, 'y': 0.5, 'smooth': True},
            {'x': 1.0, 'y': 0.0, 'smooth': False},
        ]
        self.active_pt = -1
        self.setMouseTracking(True)

    def reset_to_default(self):
        import math as _math
        self.pts = [
            {'x': 0.0,  'y': 0.0,  'smooth': False},
            {'x': 0.25, 'y': 0.5,  'smooth': True},
            {'x': 0.5,  'y': 1.0,  'smooth': True},
            {'x': 0.75, 'y': 0.5,  'smooth': True},
            {'x': 1.0,  'y': 0.0,  'smooth': False},
        ]
        self.update()
        self.curve_updated.emit()

    def flip_y(self):
        for p in self.pts:
            p['y'] = 1.0 - p['y']
        self.update()
        self.curve_updated.emit()

    def get_y_at_t(self, t):
        t = max(0.0, min(1.0, t))
        if not self.pts:
            return 0.0
        if t <= self.pts[0]['x']:
            return self.pts[0]['y']
        if t >= self.pts[-1]['x']:
            return self.pts[-1]['y']
        for i in range(len(self.pts) - 1):
            if self.pts[i]['x'] <= t <= self.pts[i + 1]['x']:
                p1 = self.pts[i]
                p2 = self.pts[i + 1]
                span = p2['x'] - p1['x']
                if span < 0.0001:
                    return p1['y']
                lt = (t - p1['x']) / span
                return p1['y'] + (p2['y'] - p1['y']) * lt
        return 0.0

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QtGui.QColor(12, 12, 18))
        painter.setPen(QtGui.QPen(QtGui.QColor(40, 40, 50), 1))
        for i in range(1, 4):
            painter.drawLine(0, int(i * (h / 4.0)), w, int(i * (h / 4.0)))
            painter.drawLine(int(i * (w / 4.0)), 0, int(i * (w / 4.0)), h)

        def to_scr(pt):
            return QtCore.QPointF(pt['x'] * w, (1.0 - pt['y']) * h)

        path = QtGui.QPainterPath()
        if not self.pts:
            return
        path.moveTo(to_scr(self.pts[0]))
        for i in range(len(self.pts) - 1):
            p1 = self.pts[i]
            p2 = self.pts[i + 1]
            sp2 = to_scr(p2)
            if not p1['smooth'] or not p2['smooth']:
                path.lineTo(sp2)
            else:
                dx = (p2['x'] - p1['x']) / 3.0
                if i == 0:
                    m1 = (p2['y'] - p1['y']) / (p2['x'] - p1['x']) if p2['x'] != p1['x'] else 0
                else:
                    m1 = (p2['y'] - self.pts[i - 1]['y']) / (p2['x'] - self.pts[i - 1]['x']) if p2['x'] != self.pts[i - 1]['x'] else 0
                if i + 2 < len(self.pts):
                    m2 = (self.pts[i + 2]['y'] - p1['y']) / (self.pts[i + 2]['x'] - p1['x']) if self.pts[i + 2]['x'] != p1['x'] else 0
                else:
                    m2 = (p2['y'] - p1['y']) / (p2['x'] - p1['x']) if p2['x'] != p1['x'] else 0
                path.cubicTo(
                    to_scr({'x': p1['x'] + dx, 'y': p1['y'] + m1 * dx}),
                    to_scr({'x': p2['x'] - dx, 'y': p2['y'] - m2 * dx}),
                    sp2,
                )
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 150, 60), 6))
        painter.drawPath(path)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 255, 150), 2))
        painter.drawPath(path)
        painter.setPen(QtCore.Qt.NoPen)
        for p in self.pts:
            sp = to_scr(p)
            if p['smooth']:
                painter.setBrush(QtGui.QColor(255, 170, 0))
                painter.drawEllipse(sp, 6, 6)
            else:
                painter.setBrush(QtGui.QColor(255, 50, 50))
                painter.drawRect(QtCore.QRectF(sp.x() - 5, sp.y() - 5, 10, 10))

    def mousePressEvent(self, event):
        w, h = self.width(), self.height()
        mx, my = event.pos().x(), event.pos().y()
        mods = event.modifiers()
        if mods & QtCore.Qt.ControlModifier:
            for i in range(1, len(self.pts) - 1):
                p = self.pts[i]
                sx, sy = p['x']*w, (1.0-p['y'])*h
                if abs(mx - sx) < 14 and abs(my - sy) < 14:
                    del self.pts[i]
                    self.update()
                    self.curve_updated.emit()
                    return
            return
        if event.button() == QtCore.Qt.RightButton:
            hit = False
            for i, p in enumerate(self.pts):
                sx, sy = p['x']*w, (1.0-p['y'])*h
                if abs(mx - sx) < 10 and abs(my - sy) < 10:
                    hit = True
                    break
            if not hit:
                self._pan_mode = True
                self._pan_start_y = my
                self._pan_start_pts = [p['y'] for p in self.pts]
                return
        for i, p in enumerate(self.pts):
            sx = p['x'] * w
            sy = (1.0 - p['y']) * h
            if abs(mx - sx) < 10 and abs(my - sy) < 10:
                self.active_pt = i
                if event.button() == QtCore.Qt.RightButton:
                    p['smooth'] = not p['smooth']
                    self.update()
                    self.curve_updated.emit()
                return
        if event.button() == QtCore.Qt.LeftButton and event.type() == QtCore.QEvent.MouseButtonDblClick:
            nx = mx / w
            ny = 1.0 - my / h
            ny = max(0.0, min(1.0, ny))
            for i in range(len(self.pts) - 1):
                if self.pts[i]['x'] <= nx <= self.pts[i + 1]['x']:
                    self.pts.insert(i + 1, {'x': nx, 'y': ny, 'smooth': True})
                    self.active_pt = i + 1
                    break
            self.update()
            self.curve_updated.emit()

    def mouseMoveEvent(self, event):
        w, h = self.width(), self.height()
        my = event.pos().y()
        if self._pan_mode and self._pan_start_pts is not None:
            dy = (self._pan_start_y - my) / h
            for i, p in enumerate(self.pts):
                p['y'] = max(0.0, min(1.0, self._pan_start_pts[i] + dy))
            self.update()
            self.curve_updated.emit()
            return
        if self.active_pt < 0:
            return
        nx = event.pos().x() / w
        ny = max(0.0, min(1.0, 1.0 - my / h))
        p = self.pts[self.active_pt]
        if self.active_pt == 0 or self.active_pt == len(self.pts) - 1:
            p['y'] = ny
        else:
            lo = self.pts[self.active_pt - 1]['x'] + 0.01
            hi = self.pts[self.active_pt + 1]['x'] - 0.01
            p['x'] = max(lo, min(hi, nx))
            p['y'] = ny
        self.update()
        self.curve_updated.emit()

    def mouseReleaseEvent(self, event):
        if self._pan_mode:
            self._pan_mode = False
            self._pan_start_pts = None
            return
        if self.active_pt != -1:
            self.active_pt = -1
            self.curve_updated.emit()

class NodeScene(QtWidgets.QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QtGui.QColor(10, 10, 16))
        painter.setPen(QtGui.QPen(QtGui.QColor(25, 25, 35), 1))
        l = int(rect.left()) - (int(rect.left()) % 50)
        t = int(rect.top()) - (int(rect.top()) % 50)
        for x in range(l, int(rect.right()), 50):
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(t, int(rect.bottom()), 50):
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)


# ==============================================================================
# VOI PROXY WIDGET
# ==============================================================================
class VoiProxyWidget(QtWidgets.QGraphicsProxyWidget):
    def __init__(self, nid, main_win, parent=None):
        super().__init__(parent)
        self.nid = nid
        self.main_win = main_win
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)

    def mouseDoubleClickEvent(self, event):
        d = self.main_win.voi_widgets.get(self.nid)
        if d and rt.isValidNode(d['base']):
            rt.select(d['base'])
            rt.redrawViews()
        super().mouseDoubleClickEvent(event)


# ==============================================================================
# ZOOMABLE VIEW
# ==============================================================================
class ZoomableView(QtWidgets.QGraphicsView):
    focus_requested = QtCore.Signal()
    selection_changed = QtCore.Signal(list, str) 

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self._dragging = False
        self._drag_start = None
        self._rubber_band = None
        self._rubber_origin = None

    def wheelEvent(self, event):
        f = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(f, f)

    def _find_proxy_at(self, pos):
        for item in self.items(pos):
            while item:
                if isinstance(item, VoiProxyWidget):
                    return item
                item = item.parentItem()
        return None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._dragging = True
            self._drag_start = event.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
            return

        if event.button() == QtCore.Qt.LeftButton:
            mods = event.modifiers()
            proxy = self._find_proxy_at(event.pos())

            if proxy:
                if mods & QtCore.Qt.ControlModifier:
                    self.selection_changed.emit([proxy], 'add')
                    event.accept()
                    return
                elif mods & QtCore.Qt.AltModifier:
                    self.selection_changed.emit([proxy], 'remove')
                    event.accept()
                    return
                else:
                    self.selection_changed.emit([proxy], 'set')
                    super().mousePressEvent(event)
                    return
            else:
                if not (mods & QtCore.Qt.ControlModifier) and not (mods & QtCore.Qt.AltModifier):
                    self.selection_changed.emit([], 'set')

                self._rubber_origin = event.pos()
                self._rubber_band = QtWidgets.QRubberBand(
                    QtWidgets.QRubberBand.Rectangle, self.viewport()
                )
                self._rubber_band.setGeometry(QtCore.QRect(self._rubber_origin, QtCore.QSize()))
                self._rubber_band.show()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._drag_start:
            delta = event.pos() - self._drag_start
            self._drag_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self._rubber_band and self._rubber_origin:
            self._rubber_band.setGeometry(
                QtCore.QRect(self._rubber_origin, event.pos()).normalized()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            event.accept()
            return
        if self._rubber_band:
            rect = self._rubber_band.geometry()
            self._rubber_band.hide()
            self._rubber_band = None
            scene_rect = self.mapToScene(rect).boundingRect()
            items = self.scene().items(scene_rect, QtCore.Qt.IntersectsItemBoundingRect)
            proxies = [it for it in items if isinstance(it, VoiProxyWidget)]

            mods = event.modifiers()
            if mods & QtCore.Qt.ControlModifier:
                mode = 'add'
            elif mods & QtCore.Qt.AltModifier:
                mode = 'remove'
            else:
                mode = 'set'

            if proxies:
                self.selection_changed.emit(proxies, mode)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_F:
            self.focus_requested.emit()
        super().keyPressEvent(event)


# ==============================================================================
# MAIN APPLICATION
# ==============================================================================
class DB9FountainV102(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("\u26f2 DB9 Fountain Pro v104.0")
        self.resize(1500, 950)
        self.setMinimumSize(900, 600)
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
        )

        self.voi_widgets = {}
        self.groups_log = {}
        self.custom_presets = {}
        self.syncing_selection = False
        self._last_sel_names = set()
        self._last_frame = None
        self._last_range = None
        self._suppress_frame_read = False

        self._apply_stylesheet()

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root_lay = QtWidgets.QVBoxLayout(central)
        root_lay.setContentsMargins(4, 4, 4, 4)
        root_lay.setSpacing(2)

        header = QtWidgets.QLabel("\u26f2 DB9 FOUNTAIN PRO v104")
        header.setAlignment(QtCore.Qt.AlignCenter)
        header.setStyleSheet(
            "font-size: 16px; font-weight: 900; color: #ffffff; padding: 8px 16px;"
            "letter-spacing: 4px;"
            "background: qlineargradient(x1:0, x2:1, stop:0 #0d47a1, stop:0.5 #1565c0, stop:1 #0d47a1);"
            "border-radius: 8px; border: 1px solid #4fc3f7;"
        )
        root_lay.addWidget(header)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background: qlineargradient(x1:0,x2:1, stop:0 #1e2a3a,"
            " stop:0.5 #4fc3f7, stop:1 #1e2a3a); border-radius: 3px; }"
        )
        root_lay.addWidget(self.splitter, stretch=1)

        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(380)
        left_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        left_widget = QtWidgets.QWidget()
        self.left_lay = QtWidgets.QVBoxLayout(left_widget)
        self.left_lay.setContentsMargins(4, 4, 4, 4)
        self.left_lay.setSpacing(4)
        left_scroll.setWidget(left_widget)
        self.splitter.addWidget(left_scroll)

        self._build_system_controls()
        self._build_groups_presets()
        self._build_master_sliders()
        self._build_curve_editor()
        self._build_rotation_presets()
        self._build_bottom_buttons()
        self.left_lay.addStretch()
        # FIX 4: Populate preset tags on startup
        QtCore.QTimer.singleShot(0, lambda: self._refresh_preset_tags())

        right_widget = QtWidgets.QWidget()
        right_lay = QtWidgets.QVBoxLayout(right_widget)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        canvas_header = QtWidgets.QLabel("  CANVAS — VOI PHUN MAP")
        canvas_header.setStyleSheet(
            "font-size: 11px; font-weight: 900; color: #ffa726; padding: 4px;"
            "background: #13131a; border-bottom: 1px solid #333346;"
        )
        right_lay.addWidget(canvas_header)

        self.scene = NodeScene(self)
        self.scene.setSceneRect(-500000, -500000, 1000000, 1000000)
        self.view = ZoomableView(self.scene)
        self.view.focus_requested.connect(self.focus_selected_vois)
        self.view.selection_changed.connect(self.on_canvas_selection)
        right_lay.addWidget(self.view, stretch=1)

        canvas_bar = QtWidgets.QHBoxLayout()
        canvas_bar.setContentsMargins(4, 2, 4, 2)

        self._frame_label = QtWidgets.QLabel("")
        self._frame_label.setStyleSheet("color:#ffab40; font-size:10px; font-weight:bold;")
        canvas_bar.addWidget(self._frame_label)

        lbl_cs = QtWidgets.QLabel("Card:")
        lbl_cs.setStyleSheet("color:#b0b0b0; font-size:10px;")
        self.sld_card_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_card_scale.setRange(40, 200)
        self.sld_card_scale.setValue(100)
        self.sld_card_scale.setFixedWidth(100)
        self.sld_card_scale.valueChanged.connect(self.set_card_scale)
        self.lbl_card_scale = QtWidgets.QLabel("100%")
        self.lbl_card_scale.setStyleSheet("color:#ffa726; font-size:10px;")
        
        btn_fit = QtWidgets.QPushButton("FIT")
        btn_fit.setFixedWidth(44)
        btn_fit.clicked.connect(self.fit_canvas)
        
        btn_map3d = QtWidgets.QPushButton("MAP 3D")
        btn_map3d.setFixedWidth(66)
        btn_map3d.setStyleSheet("color:#ff9800; font-weight:bold;")
        btn_map3d.clicked.connect(self.auto_map_from_3d)

        btn_sel_phx = QtWidgets.QPushButton("SEL PHX")
        btn_sel_phx.setFixedWidth(66)
        btn_sel_phx.setStyleSheet("color:#4fc3f7; font-weight:bold;")
        btn_sel_phx.setToolTip("Chon nhanh cac Phoenix Source cua the dang chon")
        btn_sel_phx.clicked.connect(self.select_phoenix_sources)

        canvas_bar.addWidget(lbl_cs)
        canvas_bar.addWidget(self.sld_card_scale)
        canvas_bar.addWidget(self.lbl_card_scale)
        canvas_bar.addStretch()
        canvas_bar.addWidget(btn_fit)
        canvas_bar.addWidget(btn_map3d)
        canvas_bar.addWidget(btn_sel_phx)
        right_lay.addLayout(canvas_bar)

        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([450, 700])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        # FIX 2a: Timeline full-width at bottom
        self.timeline_widget = self._build_keyframe_timeline()
        self.timeline_widget.setFixedHeight(180)
        root_lay.addWidget(self.timeline_widget)

        self._last_frame = self._get_current_frame()
        self._frame_timer = QtCore.QTimer(self)
        self._frame_timer.timeout.connect(self._check_frame_change)
        self._frame_timer.start(200)

        self._sel_timer = QtCore.QTimer(self)
        self._sel_timer.timeout.connect(self.sync_selection_from_max)
        self._sel_timer.start(300)

        self._update_frame_label()

    def _apply_stylesheet(self):
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #0d0d14;
            color: #e0e0f0;
            font-family: "Segoe UI", "Arial", sans-serif;
            font-size: 12px;
        }
        QGroupBox {
            border: 1px solid #1e2a3a;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 14px;
            background: #0f111a;
            color: #64b5f6;
            font-weight: 700;
            font-size: 11px;
            letter-spacing: 1px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 6px;
            color: #4fc3f7;
        }
        QPushButton {
            background: #1a1f2e;
            color: #90caf9;
            border: 1px solid #2a3a4a;
            border-radius: 6px;
            padding: 5px 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #1e2d42;
            border-color: #4fc3f7;
            color: #ffffff;
        }
        QPushButton:pressed {
            background: #0d1a2a;
        }
        QSlider::groove:horizontal {
            height: 4px;
            background: #1e2a3a;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            width: 14px;
            height: 14px;
            background: #4fc3f7;
            border-radius: 7px;
            margin: -5px 0;
        }
        QSlider::sub-page:horizontal {
            background: qlineargradient(x1:0, x2:1, stop:0 #1565c0, stop:1 #4fc3f7);
            border-radius: 2px;
        }
        QSlider::groove:vertical {
            width: 4px;
            background: #1e2a3a;
            border-radius: 2px;
        }
        QSlider::handle:vertical {
            width: 14px;
            height: 14px;
            background: #4fc3f7;
            border-radius: 7px;
            margin: 0 -5px;
        }
        QComboBox {
            background: #1a1f2e;
            border: 1px solid #2a3a4a;
            border-radius: 5px;
            padding: 3px 8px;
            color: #b0bec5;
        }
        QComboBox:hover { border-color: #4fc3f7; }
        QComboBox::drop-down { border: none; width: 20px; }
        QSpinBox, QDoubleSpinBox {
            background: #1a1f2e;
            border: 1px solid #2a3a4a;
            border-radius: 5px;
            padding: 3px 6px;
            color: #b0bec5;
        }
        QLineEdit {
            background: #1a1f2e;
            border: 1px solid #2a3a4a;
            border-radius: 5px;
            padding: 4px 8px;
            color: #e0e0f0;
        }
        QLineEdit:focus { border-color: #4fc3f7; }
        QScrollBar:vertical {
            background: #0d0d14;
            width: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #2a3a4a;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar:horizontal {
            background: #0d0d14;
            height: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:horizontal {
            background: #2a3a4a;
            border-radius: 4px;
            min-width: 30px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QCheckBox { spacing: 6px; color: #b0bec5; }
        QCheckBox::indicator {
            width: 16px; height: 16px;
            border: 1px solid #2a3a4a;
            border-radius: 3px;
            background: #1a1f2e;
        }
        QCheckBox::indicator:checked {
            background: #1565c0;
            border-color: #4fc3f7;
        }
        QRadioButton { color: #b0bec5; font-size: 11px; }
        QLabel { color: #b0bec5; }
        QTabWidget::pane {
            border: 1px solid #1e2a3a;
            border-radius: 6px;
            background: #0f111a;
        }
        QTabBar::tab {
            background: #1a1f2e;
            color: #7986cb;
            padding: 5px 14px;
            border-radius: 5px 5px 0 0;
            font-weight: 600;
            font-size: 11px;
        }
        QTabBar::tab:selected {
            background: #0f111a;
            color: #4fc3f7;
            border-bottom: 2px solid #4fc3f7;
        }
        QFrame { border: none; }
        QSplitter::handle {
            background: #1e2a3a;
        }
        QScrollArea { border: none; background: transparent; }
        QToolTip {
            background: #1a1f2e;
            color: #e0e0f0;
            border: 1px solid #4fc3f7;
            border-radius: 4px;
            padding: 4px 8px;
        }
        """)

    def _build_system_controls(self):
        grp = QtWidgets.QGroupBox("HE THONG")
        lay = QtWidgets.QVBoxLayout(grp)

        r1 = QtWidgets.QHBoxLayout()
        r1.addWidget(QtWidgets.QLabel("Don vi:"))
        self.radio_auto = QtWidgets.QRadioButton("Auto")
        self.radio_auto.setChecked(True)
        self.radio_m = QtWidgets.QRadioButton("m")
        self.radio_cm = QtWidgets.QRadioButton("cm")
        r1.addWidget(self.radio_auto)
        r1.addWidget(self.radio_m)
        r1.addWidget(self.radio_cm)
        r1.addSpacing(6)
        r1.addWidget(QtWidgets.QLabel("Mui ten:"))
        self.sld_global_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_global_scale.setRange(1, 100000)
        self.sld_global_scale.setValue(100)
        self.sld_global_scale.valueChanged.connect(self.run_global_update)
        self.lbl_scale_val = QtWidgets.QLabel("1.00x")
        self.lbl_scale_val.setStyleSheet("color:#ffa726;font-weight:bold;")
        r1.addWidget(self.sld_global_scale)
        r1.addWidget(self.lbl_scale_val)
        lay.addLayout(r1)

        r2 = QtWidgets.QHBoxLayout()
        self.chk_phoenix = QtWidgets.QCheckBox("PHOENIX LINK")
        self.chk_phoenix.setChecked(True)
        self.chk_phoenix.setStyleSheet("color:#ff7043;font-weight:bold;")
        self.chk_autokey = QtWidgets.QCheckBox("AUTOKEY")
        self.chk_autokey.setChecked(True)
        self.chk_autokey.stateChanged.connect(
            lambda s: rt.setKeyMode(s == QtCore.Qt.Checked)
        )
        r2.addWidget(self.chk_phoenix)
        r2.addWidget(self.chk_autokey)
        r2.addStretch()

        self.btn_force_key = QtWidgets.QPushButton("CHOT KEY")
        self.btn_force_key.setStyleSheet(
            "background:qlineargradient(x1:0,x2:1,stop:0 #0d47a1,stop:1 #1976d2);"
            "color:white;font-weight:900;border:none;border-radius:5px;"
        )
        self.btn_force_key.clicked.connect(self.force_keyframe)
        r2.addWidget(self.btn_force_key)

        self.btn_reset_key = QtWidgets.QPushButton("RESET KEY")
        self.btn_reset_key.setStyleSheet(
            "background:qlineargradient(x1:0,x2:1,stop:0 #880e4f,stop:1 #c62828);"
            "color:white;font-weight:900;border:none;border-radius:5px;"
        )
        self.btn_reset_key.setToolTip("Xoa tat ca keyframe cua doi tuong/nhom dang chon")
        self.btn_reset_key.clicked.connect(self.reset_keyframes)
        r2.addWidget(self.btn_reset_key)

        self.btn_undo = QtWidgets.QPushButton("↶ UNDO")
        self.btn_undo.setStyleSheet("background:#546e7a;color:white;font-weight:900;border:none;border-radius:5px;")
        self.btn_undo.setToolTip("Lui lai thao tac gan nhat (Undo 3ds Max)")
        self.btn_undo.clicked.connect(lambda: rt.execute("max undo"))
        r2.addWidget(self.btn_undo)

        lay.addLayout(r2)

        r3 = QtWidgets.QHBoxLayout()
        r3.addWidget(QtWidgets.QLabel("VEL MIN:"))
        self.spin_out_min = QtWidgets.QDoubleSpinBox()
        self.spin_out_min.setRange(0, 99999)
        self.spin_out_min.setValue(0)
        self.spin_out_min.setDecimals(1)
        self.spin_out_min.valueChanged.connect(self._on_lock_range_changed)
        r3.addWidget(self.spin_out_min)
        r3.addWidget(QtWidgets.QLabel("MAX:"))
        self.spin_out_max = QtWidgets.QDoubleSpinBox()
        self.spin_out_max.setRange(0, 99999)
        self.spin_out_max.setValue(500)
        self.spin_out_max.setDecimals(1)
        self.spin_out_max.valueChanged.connect(self._on_lock_range_changed)
        r3.addWidget(self.spin_out_max)

        self.chk_lock_range = QtWidgets.QCheckBox("LOCK")
        self.chk_lock_range.setStyleSheet("color:#ff5252;font-weight:bold;")
        self.chk_lock_range.setToolTip("Khoa slider trong khoang MIN-MAX")
        self.chk_lock_range.stateChanged.connect(self._on_lock_range_changed)
        r3.addWidget(self.chk_lock_range)

        self.btn_push_phx = QtWidgets.QPushButton("PUSH PHX")
        self.btn_push_phx.setStyleSheet(
            "background:qlineargradient(x1:0,x2:1,stop:0 #4a148c,stop:1 #7b1fa2);"
            "color:white;font-weight:900;border:none;border-radius:5px;"
        )
        self.btn_push_phx.clicked.connect(self.push_outgoing_to_phoenix)
        r3.addWidget(self.btn_push_phx)
        lay.addLayout(r3)

        # INSERT NEW ROW FOR PHOENIX MODE & POLY ID
        r4 = QtWidgets.QHBoxLayout()
        r4.addWidget(QtWidgets.QLabel("PHX MODE:"))
        self.cmb_phx_mode = QtWidgets.QComboBox()
        self.cmb_phx_mode.addItems(["Volume Inject", "Surface Force"])
        self.cmb_phx_mode.setStyleSheet("color:#ffb74d;font-weight:bold; padding: 2px 5px;")
        self.cmb_phx_mode.currentIndexChanged.connect(self.change_phoenix_mode)
        r4.addWidget(self.cmb_phx_mode)
        
        r4.addSpacing(15)
        r4.addWidget(QtWidgets.QLabel("POLY ID:"))
        self.spin_poly_id = QtWidgets.QSpinBox()
        self.spin_poly_id.setRange(0, 9999)
        self.spin_poly_id.setValue(0)
        self.spin_poly_id.setFixedWidth(55)
        self.spin_poly_id.setStyleSheet("color:#4fc3f7; font-weight:bold;")
        r4.addWidget(self.spin_poly_id)

        self.btn_set_poly_id = QtWidgets.QPushButton("SET ID")
        self.btn_set_poly_id.setStyleSheet("background:#0277bd; color:white; font-weight:bold; border-radius:3px; padding:2px 8px;")
        self.btn_set_poly_id.clicked.connect(self.set_phoenix_poly_id)
        r4.addWidget(self.btn_set_poly_id)

        r4.addStretch()
        lay.addLayout(r4)

        self.left_lay.addWidget(grp)

    def change_phoenix_mode(self, idx):
        em_val = 1 if idx == 0 else 0
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        
        if not targets:
            targets = list(self.voi_widgets.keys())
            
        for nid in targets:
            d = self.voi_widgets[nid]
            if rt.isValidNode(d['sp']):
                phx_idx = d['sp'].name.split("_")[-1]
                sn = "PHX_LiquidSrc_" + phx_idx
                mxs = (
                    '(local src = getNodeByName "{sn}";'
                    ' if src != undefined do ('
                    '   try (src.emitMode = {val}) catch()'
                    ' ))'
                ).format(sn=sn, val=em_val)
                rt.execute(mxs)

    def set_phoenix_poly_id(self):
        poly_id = self.spin_poly_id.value()
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        
        if not targets:
            targets = list(self.voi_widgets.keys())
            
        for nid in targets:
            d = self.voi_widgets[nid]
            if rt.isValidNode(d['sp']):
                phx_idx = d['sp'].name.split("_")[-1]
                sn = "PHX_LiquidSrc_" + phx_idx
                mxs = (
                    '(local src = getNodeByName "{sn}";'
                    ' if src != undefined do ('
                    '   try (src.polyId = {val}) catch();'
                    '   try (src.polygonID = {val}) catch();'
                    '   try (if {val} > 0 then src.polyIdOnly = true else src.polyIdOnly = false) catch()'
                    ' ))'
                ).format(sn=sn, val=poly_id)
                rt.execute(mxs)

    def _build_groups_presets(self):
        grp = QtWidgets.QGroupBox("NHOM & PRESETS")
        lay = QtWidgets.QVBoxLayout(grp)

        r1 = QtWidgets.QHBoxLayout()
        self.txt_grp = QtWidgets.QLineEdit()
        self.txt_grp.setPlaceholderText("Ten nhom...")
        btn_sg = QtWidgets.QPushButton("LUU")
        btn_sg.clicked.connect(self.save_group)
        btn_dg = QtWidgets.QPushButton("XOA")
        btn_dg.setStyleSheet("color:#ef5350;border-color:#ef5350;")
        btn_dg.clicked.connect(self.delete_group)
        r1.addWidget(self.txt_grp)
        r1.addWidget(btn_sg)
        r1.addWidget(btn_dg)
        lay.addLayout(r1)

        self.grp_btns_container = QtWidgets.QWidget()
        self.grp_btns_lay = FlowLayout(self.grp_btns_container, margin=2, spacing=4)
        lay.addWidget(self.grp_btns_container)

        r2 = QtWidgets.QHBoxLayout()
        self.txt_preset = QtWidgets.QLineEdit()
        self.txt_preset.setPlaceholderText("Ten preset...")
        btn_sp = QtWidgets.QPushButton("SAVE")
        btn_sp.clicked.connect(self.save_preset)
        self.cmb_presets = QtWidgets.QComboBox()
        btn_lp = QtWidgets.QPushButton("LOAD")
        btn_lp.clicked.connect(self.load_preset)
        
        # NÚT XÓA PRESET ĐƯỢC CHỌN TRONG COMBOBOX
        btn_dp = QtWidgets.QPushButton("XOA")
        btn_dp.setStyleSheet("color:#ef5350;border-color:#ef5350;")
        btn_dp.clicked.connect(self.delete_preset)

        r2.addWidget(self.txt_preset)
        r2.addWidget(btn_sp)
        r2.addWidget(self.cmb_presets)
        r2.addWidget(btn_lp)
        r2.addWidget(btn_dp) # Thêm nút XOA vào layout

        btn_export = QtWidgets.QPushButton("EXPORT")
        btn_export.setToolTip("Xuat tat ca presets ra file JSON")
        btn_export.setStyleSheet("color:#4fc3f7;font-weight:bold;")
        btn_export.clicked.connect(self.export_presets)
        btn_import = QtWidgets.QPushButton("IMPORT")
        btn_import.setToolTip("Nhap presets tu file JSON")
        btn_import.setStyleSheet("color:#aed581;font-weight:bold;")
        btn_import.clicked.connect(self.import_presets)
        r2.addWidget(btn_export)
        r2.addWidget(btn_import)

        lay.addLayout(r2)

        # FIX 4: Preset tags display (pill buttons)
        self.preset_tags_container = QtWidgets.QWidget()
        self.preset_tags_lay = FlowLayout(self.preset_tags_container, margin=2, spacing=4)
        lay.addWidget(self.preset_tags_container)

        self.chk_realtime = QtWidgets.QCheckBox("REALTIME PREVIEW")
        self.chk_realtime.setChecked(True)
        self.chk_realtime.setStyleSheet("color:#64b5f6;font-weight:bold;")
        self.chk_realtime.stateChanged.connect(self.toggle_realtime_preview)
        lay.addWidget(self.chk_realtime)

        self.left_lay.addWidget(grp)

    def _build_master_sliders(self):
        grp = QtWidgets.QGroupBox("MASTER")
        lay = QtWidgets.QVBoxLayout(grp)

        r = QtWidgets.QHBoxLayout()
        _master_spinboxes = [('h', 'spin_m_h', 0, 1000), ('t', 'spin_m_t', 0, 500), ('a', 'spin_m_a', 0, 360)]
        for label, color, attr, rng in [
            ("LUC:", "#4fc3f7", "h", (0, 1000)),
            ("NGHIENG:", "#aed581", "t", (0, 500)),
            ("XOAY:", "#ce93d8", "a", (0, 360)),
        ]:
            lbl = QtWidgets.QLabel(label)
            lbl.setStyleSheet("color:{};font-weight:bold;".format(color))
            sld = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            sld.setRange(rng[0], rng[1])
            sld.valueChanged.connect(lambda v, a=attr: self.master_sync(a, v))
            spb = QtWidgets.QDoubleSpinBox()
            spb.setRange(rng[0], rng[1])
            spb.setDecimals(0)
            spb.setFixedWidth(65)
            spb.setStyleSheet("color:{};font-weight:bold;".format(color))
            sld.valueChanged.connect(lambda v, s=spb: (s.blockSignals(True), s.setValue(v), s.blockSignals(False)))
            spb.valueChanged.connect(lambda v, s=sld: (s.blockSignals(True), s.setValue(int(v)), s.blockSignals(False)))
            spb.valueChanged.connect(lambda v, a=attr: self.master_sync(a, int(v)))
            r.addWidget(lbl)
            r.addWidget(sld)
            r.addWidget(spb)
            setattr(self, 'm_sld_' + attr, sld)
            setattr(self, 'spin_m_' + attr, spb)
        lay.addLayout(r)

        br = QtWidgets.QHBoxLayout()
        btn0 = QtWidgets.QPushButton("SET 0")
        btn0.setStyleSheet("background:#b71c1c;color:white;font-weight:900;border:none;border-radius:5px;padding:10px 18px;")
        btn0.clicked.connect(self.master_set_zero)
        btn_min = QtWidgets.QPushButton("SET MIN")
        btn_min.setStyleSheet("background:#004d40;color:white;font-weight:900;border:none;border-radius:5px;padding:10px 18px;")
        btn_min.clicked.connect(lambda: self.set_minmax("min"))
        btn_max = QtWidgets.QPushButton("SET MAX")
        btn_max.setStyleSheet("background:#e65100;color:white;font-weight:900;border:none;border-radius:5px;padding:10px 18px;")
        btn_max.clicked.connect(lambda: self.set_minmax("max"))
        br.addWidget(btn0)
        br.addWidget(btn_min)
        br.addWidget(btn_max)
        lay.addLayout(br)

        self.left_lay.addWidget(grp)

    def _build_curve_editor(self):
        grp = QtWidgets.QGroupBox("CURVE")
        lay = QtWidgets.QVBoxLayout(grp)

        self.curve_editor = BezierCurveWidget()
        self.curve_editor.curve_updated.connect(self.apply_spatial_curve)
        lay.addWidget(self.curve_editor)

        curve_btns = QtWidgets.QHBoxLayout()
        btn_curve_reset = QtWidgets.QPushButton("↺ RESET CURVE")
        btn_curve_reset.setStyleSheet("background:#1a237e;color:white;border:none;border-radius:4px;padding:4px;font-size:10px;font-weight:bold;")
        btn_curve_reset.clicked.connect(self.curve_editor.reset_to_default)
        btn_curve_flip = QtWidgets.QPushButton("⇅ FLIP Y")
        btn_curve_flip.setStyleSheet("background:#212121;color:#ce93d8;border:1px solid #ce93d8;border-radius:4px;padding:4px;font-size:10px;font-weight:bold;")
        btn_curve_flip.clicked.connect(self.curve_editor.flip_y)
        curve_btns.addWidget(btn_curve_reset, stretch=1)
        curve_btns.addWidget(btn_curve_flip, stretch=1)
        lay.addLayout(curve_btns)

        apply_curve_btns = QtWidgets.QHBoxLayout()
        btn_curve_to_angle = QtWidgets.QPushButton("↗ CURVE → ANGLE")
        btn_curve_to_angle.setStyleSheet("background:#1a237e;color:#ce93d8;border:1px solid #ce93d8;border-radius:4px;padding:4px;font-size:10px;font-weight:bold;")
        btn_curve_to_angle.clicked.connect(self.apply_spatial_curve_to_angle)
        btn_curve_to_vel = QtWidgets.QPushButton("↑ CURVE → VEL")
        btn_curve_to_vel.setStyleSheet("background:#212121;color:#4fc3f7;border:1px solid #4fc3f7;border-radius:4px;padding:4px;font-size:10px;font-weight:bold;")
        btn_curve_to_vel.clicked.connect(self.apply_spatial_curve)
        apply_curve_btns.addWidget(btn_curve_to_angle, stretch=1)
        apply_curve_btns.addWidget(btn_curve_to_vel, stretch=1)
        lay.addLayout(apply_curve_btns)

        r = QtWidgets.QHBoxLayout()
        self.chk_mirror = QtWidgets.QCheckBox("MIRROR")
        self.chk_mirror.setStyleSheet("color:#ce93d8;font-weight:bold;")
        self.chk_mirror.stateChanged.connect(self.apply_spatial_curve)
        r.addWidget(self.chk_mirror)

        r.addWidget(QtWidgets.QLabel("Amp:"))
        self.sld_amp = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_amp.setRange(0, 200)
        self.sld_amp.setValue(100)
        self.sld_amp.valueChanged.connect(self.update_amplitude)
        self.sld_amp.setFixedWidth(80)
        self.lbl_amp = QtWidgets.QLabel("100%")
        self.lbl_amp.setStyleSheet("color:#ffa726;")
        r.addWidget(self.sld_amp)
        r.addWidget(self.lbl_amp)

        r.addWidget(QtWidgets.QLabel("Xoay:"))
        self.sld_rotate = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_rotate.setRange(0, 360)
        self.sld_rotate.setValue(0)
        self.sld_rotate.valueChanged.connect(self.apply_spatial_curve)
        self.sld_rotate.setFixedWidth(60)
        r.addWidget(self.sld_rotate)
        r.addStretch()
        lay.addLayout(r)

        preset_container = QtWidgets.QWidget()
        preset_flow = FlowLayout(preset_container, margin=2, spacing=3)

        all_presets = [
            ("Sin", [{'x': 0, 'y': 0, 's': False}, {'x': 0.25, 'y': 1.0, 's': True}, {'x': 0.5, 'y': 0.0, 's': True}, {'x': 0.75, 'y': 1.0, 's': True}, {'x': 1.0, 'y': 0.0, 's': False}]),
            ("Dome", [{'x': 0, 'y': 0, 's': False}, {'x': 0.5, 'y': 1.0, 's': True}, {'x': 1.0, 'y': 0.0, 's': False}]),
            ("Flat", [{'x': 0, 'y': 1.0, 's': False}, {'x': 1.0, 'y': 1.0, 's': False}]),
            ("Ramp", [{'x': 0, 'y': 0, 's': False}, {'x': 1.0, 'y': 1.0, 's': False}]),
            ("V", [{'x': 0, 'y': 1.0, 's': False}, {'x': 0.5, 'y': 0.0, 's': False}, {'x': 1.0, 'y': 1.0, 's': False}]),
            ("Pulse", [{'x': 0, 'y': 0, 's': False}, {'x': 0.05, 'y': 1.0, 's': False}, {'x': 0.15, 'y': 1.0, 's': False}, {'x': 0.2, 'y': 0, 's': False}, {'x': 1.0, 'y': 0, 's': False}]),
            ("Wave3", [{'x': 0, 'y': 0, 's': False}, {'x': 0.17, 'y': 1.0, 's': True}, {'x': 0.33, 'y': 0, 's': True}, {'x': 0.5, 'y': 1.0, 's': True}, {'x': 0.67, 'y': 0, 's': True}, {'x': 0.83, 'y': 1.0, 's': True}, {'x': 1.0, 'y': 0, 's': False}]),
            ("Cascade", [{'x': 0, 'y': 0, 's': False}, {'x': 0.2, 'y': 0, 's': False}, {'x': 0.2, 'y': 0.33, 's': False}, {'x': 0.4, 'y': 0.33, 's': False}, {'x': 0.4, 'y': 0.66, 's': False}, {'x': 0.6, 'y': 0.66, 's': False}, {'x': 0.6, 'y': 1.0, 's': False}, {'x': 0.8, 'y': 1.0, 's': False}, {'x': 0.8, 'y': 0.5, 's': False}, {'x': 1.0, 'y': 0.5, 's': False}]),
            ("Bloom", [{'x': 0, 'y': 0, 's': True}, {'x': 0.3, 'y': 0.2, 's': True}, {'x': 0.5, 'y': 1.0, 's': True}, {'x': 0.7, 'y': 0.2, 's': True}, {'x': 1.0, 'y': 0, 's': True}]),
            ("Heart", [{'x': 0, 'y': 0, 's': True}, {'x': 0.15, 'y': 0.8, 's': True}, {'x': 0.25, 'y': 0.3, 's': True}, {'x': 0.35, 'y': 1.0, 's': True}, {'x': 0.5, 'y': 0.2, 's': True}, {'x': 1.0, 'y': 0, 's': False}]),
            ("Ripple", [{'x': 0, 'y': 1.0, 's': True}, {'x': 0.15, 'y': 0.6, 's': True}, {'x': 0.3, 'y': 0.8, 's': True}, {'x': 0.45, 'y': 0.4, 's': True}, {'x': 0.6, 'y': 0.6, 's': True}, {'x': 0.75, 'y': 0.2, 's': True}, {'x': 0.9, 'y': 0.3, 's': True}, {'x': 1.0, 'y': 0, 's': False}]),
            ("Crown", [{'x': 0, 'y': 0.3, 's': True}, {'x': 0.15, 'y': 0.9, 's': True}, {'x': 0.3, 'y': 0.5, 's': True}, {'x': 0.5, 'y': 1.0, 's': True}, {'x': 0.7, 'y': 0.5, 's': True}, {'x': 0.85, 'y': 0.9, 's': True}, {'x': 1.0, 'y': 0.3, 's': True}]),
            ("Burst", [{'x': 0, 'y': 0, 's': False}, {'x': 0.1, 'y': 0, 's': False}, {'x': 0.15, 'y': 1.0, 's': False}, {'x': 0.2, 'y': 0, 's': False}, {'x': 1.0, 'y': 0, 's': False}]),
            ("Gentle", [{'x': 0, 'y': 0, 's': True}, {'x': 0.5, 'y': 0.6, 's': True}, {'x': 1.0, 'y': 0, 's': True}]),
            ("Zigzag", [{'x': 0, 'y': 0, 's': False}, {'x': 0.125, 'y': 1.0, 's': False}, {'x': 0.25, 'y': 0, 's': False}, {'x': 0.375, 'y': 1.0, 's': False}, {'x': 0.5, 'y': 0, 's': False}, {'x': 0.625, 'y': 1.0, 's': False}, {'x': 0.75, 'y': 0, 's': False}, {'x': 0.875, 'y': 1.0, 's': False}, {'x': 1.0, 'y': 0, 's': False}]),
            ("Spiral", [{'x': 0, 'y': 0, 's': True}, {'x': 0.2, 'y': 0.3, 's': True}, {'x': 0.4, 'y': 0.5, 's': True}, {'x': 0.6, 'y': 0.8, 's': True}, {'x': 0.8, 'y': 1.0, 's': True}, {'x': 1.0, 'y': 0.5, 's': True}]),
            ("Dance", [{'x': 0, 'y': 0, 's': False}, {'x': 0.1, 'y': 0.8, 's': True}, {'x': 0.2, 'y': 0.2, 's': True}, {'x': 0.3, 'y': 1.0, 's': True}, {'x': 0.4, 'y': 0.1, 's': True}, {'x': 0.5, 'y': 0.9, 's': True}, {'x': 0.6, 'y': 0.3, 's': True}, {'x': 0.7, 'y': 0.7, 's': True}, {'x': 0.8, 'y': 0.5, 's': True}, {'x': 0.9, 'y': 0.85, 's': True}, {'x': 1.0, 'y': 0, 's': False}]),
            ("Rain", [{'x': 0, 'y': 0.3, 's': True}, {'x': 0.1, 'y': 0.5, 's': True}, {'x': 0.2, 'y': 0.2, 's': True}, {'x': 0.3, 'y': 0.6, 's': True}, {'x': 0.4, 'y': 0.35, 's': True}, {'x': 0.5, 'y': 0.55, 's': True}, {'x': 0.6, 'y': 0.25, 's': True}, {'x': 0.7, 'y': 0.45, 's': True}, {'x': 0.8, 'y': 0.4, 's': True}, {'x': 0.9, 'y': 0.5, 's': True}, {'x': 1.0, 'y': 0.3, 's': True}]),
            ("Volcano", [{'x': 0, 'y': 0, 's': True}, {'x': 0.15, 'y': 1.0, 's': True}, {'x': 0.5, 'y': 0.5, 's': True}, {'x': 1.0, 'y': 0, 's': True}]),
            ("Sweep", [{'x': 0, 'y': 0, 's': True}, {'x': 0.3, 'y': 0, 's': True}, {'x': 0.5, 'y': 1.0, 's': True}, {'x': 0.7, 'y': 0, 's': True}, {'x': 1.0, 'y': 0, 's': True}]),
        ]

        for name, pts in all_presets:
            btn = QtWidgets.QPushButton(name)
            btn.setFixedWidth(56)
            btn.setFixedHeight(26)
            btn.setStyleSheet("font-size:9px;padding:2px 4px;")
            normalized = [{'x': p['x'], 'y': p['y'], 'smooth': p['s']} for p in pts]
            btn.clicked.connect(lambda c=False, p=normalized: self.set_curve_shape(p))
            preset_flow.addWidget(btn)

        lay.addWidget(preset_container)
        self.left_lay.addWidget(grp)

    def _build_rotation_presets(self):
        grp = QtWidgets.QGroupBox("CHE DO XOAY")
        grp.setStyleSheet(
            "QGroupBox { color: #ce93d8; font-weight: bold; font-size: 11px;"
            " border: 1px solid #2a1a3a; margin-top: 14px; padding-top: 14px;"
            " border-radius: 8px; background-color: #14121e; }"
            "QGroupBox::title { subcontrol-origin: margin;"
            " subcontrol-position: top left; left: 10px; padding: 0 6px; }"
        )
        lay = QtWidgets.QVBoxLayout(grp)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        r1 = QtWidgets.QHBoxLayout()
        r1.addWidget(QtWidgets.QLabel("Kieu xoay:"))
        self.cmb_rotation = QtWidgets.QComboBox()
        self.cmb_rotation.addItems([
            "Khong xoay", "Xoay 360 lien tuc", "Xoay qua lai",
            "Xoay theo nhom", "Xoay ngau nhien", "Lan song xoay", "Song curve"
        ])
        r1.addWidget(self.cmb_rotation, stretch=1)
        lay.addLayout(r1)

        r2 = QtWidgets.QHBoxLayout()
        r2.addWidget(QtWidgets.QLabel("Toc do:"))
        self.sld_rot_speed = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_rot_speed.setRange(1, 10)
        self.sld_rot_speed.setValue(3)
        self.lbl_rot_speed = QtWidgets.QLabel("3")
        self.lbl_rot_speed.setStyleSheet("color:#ce93d8;font-weight:bold;min-width:20px;")
        self.sld_rot_speed.valueChanged.connect(lambda v: self.lbl_rot_speed.setText(str(v)))
        r2.addWidget(self.sld_rot_speed, stretch=1)
        r2.addWidget(self.lbl_rot_speed)
        lay.addLayout(r2)

        btn_row = QtWidgets.QHBoxLayout()
        btn_apply = QtWidgets.QPushButton("▶ AP DUNG XOAY")
        btn_apply.setStyleSheet("background:qlineargradient(x1:0,x2:1,stop:0 #4a148c,stop:1 #7b1fa2);color:white;font-weight:900;border:none;border-radius:5px;padding:8px;")
        btn_apply.clicked.connect(self.apply_rotation_preset)
        btn_row.addWidget(btn_apply, stretch=3)

        self.btn_rot_cancel = QtWidgets.QPushButton("⏹ DUNG")
        self.btn_rot_cancel.setStyleSheet("background:#b71c1c;color:white;font-weight:bold;border:none;border-radius:5px;padding:8px;")
        self.btn_rot_cancel.setVisible(False)
        self.btn_rot_cancel.clicked.connect(self.apply_rotation_preset)
        btn_row.addWidget(self.btn_rot_cancel, stretch=1)
        lay.addLayout(btn_row)

        self.left_lay.addWidget(grp)

    def _build_bottom_buttons(self):
        r = QtWidgets.QHBoxLayout()
        self.btn_scan = QtWidgets.QPushButton("\U0001F50D SCAN")
        self.btn_scan.setStyleSheet("background:qlineargradient(x1:0,x2:1,stop:0 #1b5e20,stop:1 #43a047);color:white;font-weight:900;border:none;border-radius:6px;padding:10px 18px;font-size:13px;")
        self.btn_scan.clicked.connect(self.scan_and_setup)
        self.btn_phx = QtWidgets.QPushButton("\u26A1 TAO PHX")
        self.btn_phx.setStyleSheet("background:qlineargradient(x1:0,x2:1,stop:0 #e65100,stop:1 #ff6d00);color:white;font-weight:900;border:none;border-radius:6px;padding:10px 18px;font-size:13px;")
        self.btn_phx.clicked.connect(self.auto_create_phoenix)
        self.btn_reset = QtWidgets.QPushButton("\U0001F5D1 RESET")
        self.btn_reset.setStyleSheet("background:qlineargradient(x1:0,x2:1,stop:0 #b71c1c,stop:1 #d32f2f);color:white;font-weight:900;border:none;border-radius:6px;padding:10px 18px;font-size:13px;")
        self.btn_reset.clicked.connect(self.reset_all)
        r.addWidget(self.btn_scan)
        r.addWidget(self.btn_phx)
        r.addWidget(self.btn_reset)
        self.left_lay.addLayout(r)

    def _check_frame_change(self):
        try:
            cur_range = self._get_animation_range_frames()
            if not hasattr(self, '_last_range') or self._last_range != cur_range:
                self._last_range = cur_range
                self._refresh_timeline()

            cur = self._get_current_frame()
            if cur != self._last_frame:
                self._last_frame = cur
                self._update_frame_label()
                if hasattr(self, 'tl_widget_main'):
                    self.tl_widget_main.set_current_frame(cur)
                if not self._suppress_frame_read:
                    self.read_back_from_3d()
        except Exception:
            pass

    def read_back_from_3d(self):
        sc = self.get_u_scale()
        if sc < 0.00001:
            sc = 1.0
        for nid, d in self.voi_widgets.items():
            if not rt.isValidNode(d['sp']) or not rt.isValidNode(d['base']):
                continue
            try:
                bp = rt.getProperty(d['base'], 'pos')

                h_val = d['h']  
                idx = d['sp'].name.split("_")[-1]
                sn = "PHX_LiquidSrc_" + idx
                if self.chk_phoenix.isChecked():
                    mxs_read = (
                        '(local src = getNodeByName "{sn}";'
                        ' local v = undefined;'
                        ' if src != undefined do ('
                        '   try (if isProperty src #velocity then v = src.velocity) catch();'
                        '   if v == undefined do try (if isProperty src #discharge then v = src.discharge) catch();'
                        '   if v == undefined do try (if isProperty src #outvel then v = src.outvel) catch();'
                        '   if v == undefined do try (if isProperty src #outgoingVelocity then v = src.outgoingVelocity) catch()'
                        ' ); v)'
                    ).format(sn=sn)
                    result = rt.execute(mxs_read)
                    if result is not None:
                        try:
                            divisor = self._get_unit_divisor()
                            h_val = max(0, min(1000, int(round(float(result) * divisor))))
                        except (TypeError, ValueError):
                            pass

                k2 = rt.getKnotPoint(d['sp'], 1, 2)
                dx = k2.x - bp.x
                dy = k2.y - bp.y

                t_val = max(0, min(500, int(round(math.sqrt(dx * dx + dy * dy) / sc))))
                a_val = int(round(math.degrees(math.atan2(dy, dx)))) % 360

                d['h'] = h_val
                d['t'] = t_val
                d['a'] = a_val

                for key, val in [('sh', h_val), ('st', t_val), ('sa', a_val)]:
                    if key in d:
                        d[key].blockSignals(True)
                        d[key].setValue(val)
                        d[key].blockSignals(False)
                if 'lbl_h_val' in d:
                    d['lbl_h_val'].setText(str(h_val))
                if 'lbl_vel' in d:
                    phx_vel = self.get_phoenix_velocity(h_val)
                    d['lbl_vel'].setText("VEL: {:.1f}".format(phx_vel))

                # Preview by frame must stay read-only; writing the spline here
                # forces the last sampled state back onto the current frame.

            except Exception:
                pass

        if self.voi_widgets:
            first = next(iter(self.voi_widgets.values()))
            for sld, spb, attr in [(self.m_sld_h, self.spin_m_h, 'h'), (self.m_sld_t, self.spin_m_t, 't'), (self.m_sld_a, self.spin_m_a, 'a')]:
                sld.blockSignals(True)
                sld.setValue(first[attr])
                sld.blockSignals(False)
                spb.blockSignals(True)
                spb.setValue(first[attr])
                spb.blockSignals(False)

        rt.redrawViews()

    def _update_frame_label(self):
        try:
            f = self._get_current_frame()
            self._frame_label.setText("F:{}".format(f))
        except Exception:
            pass

    def _get_ticks_per_frame(self):
        try:
            return max(1, int(rt.ticksPerFrame))
        except Exception:
            return 160

    def _time_to_frame(self, time_value):
        try:
            return int(time_value)
        except Exception:
            return 0

    def _frame_to_time(self, frame):
        return int(frame)

    def _get_current_frame(self):
        return self._time_to_frame(rt.currentTime)

    def _set_current_frame(self, frame):
        rt.sliderTime = self._frame_to_time(frame)

    def _get_animation_range_frames(self):
        try:
            return (
                int(rt.animationRange.start),
                int(rt.animationRange.end),
            )
        except Exception:
            return (0, 100)

    def get_u_scale(self):
        m = self.sld_global_scale.value() / 100.0
        if self.radio_m.isChecked():
            return 0.01 * m
        if self.radio_auto.isChecked() and "meter" in str(rt.units.SystemType).lower():
            return 0.01 * m
        return 1.0 * m

    def _get_unit_divisor(self):
        try:
            sys_type = str(rt.units.SystemType).lower()
            if "meter" in sys_type and "centi" not in sys_type and "milli" not in sys_type:
                return 100.0
            elif "centimeter" in sys_type:
                return 1.0
            elif "millimeter" in sys_type:
                return 0.1  
            elif "inch" in sys_type:
                return 2.54
            elif "feet" in sys_type or "foot" in sys_type:
                return 30.48
            else:
                return 1.0
        except Exception:
            return 1.0

    def get_phoenix_velocity(self, h_val):
        divisor = self._get_unit_divisor()
        return float(h_val) / divisor

    def _key_phoenix_velocity(self, d, force_key=False):
        if not self.chk_phoenix.isChecked():
            return
        if not rt.isValidNode(d['sp']):
            return
        fd = self.get_phoenix_velocity(d['h'])
        idx = d['sp'].name.split("_")[-1]
        sn = "PHX_LiquidSrc_" + idx
        f = self._get_current_frame()
        mxs = (
            '(local src = getNodeByName "{sn}";'
            ' if src != undefined do ('
            '   with animate on at time {f}f ('
            '     try (if isProperty src #discharge then src.discharge = {fd}) catch();'
            '     try (if isProperty src #velocity then src.velocity = {fd}) catch();'
            '     try (if isProperty src #outvel then src.outvel = {fd}) catch();'
            '     try (if isProperty src #outgoingVelocity then'
            '       src.outgoingVelocity = {fd}) catch()'
            '   )'
            ' ))'
        ).format(sn=sn, f=f, fd=fd)
        rt.execute(mxs)

    def _on_lock_range_changed(self):
        if not self.chk_lock_range.isChecked():
            lo, hi = 0, 1000
            self.m_sld_h.setRange(lo, hi)
            for nid, d in self.voi_widgets.items():
                if 'sh' in d:
                    d['sh'].setRange(lo, hi)
            return
        lo = int(self.spin_out_min.value())
        hi = int(self.spin_out_max.value())
        if hi < lo:
            hi = lo
        self.m_sld_h.setRange(lo, hi)
        for nid, d in self.voi_widgets.items():
            if 'sh' in d:
                d['sh'].setRange(lo, hi)
                cur = d['h']
                if cur < lo:
                    self.sync_values("h", nid, lo, respect_selection=False, redraw=False)
                elif cur > hi:
                    self.sync_values("h", nid, hi, respect_selection=False, redraw=False)
        rt.redrawViews()

    def run_global_update(self, v):
        self.lbl_scale_val.setText("{:.2f}x".format(v / 100.0))
        sc = self.get_u_scale()
        for d in self.voi_widgets.values():
            if rt.isValidNode(d['sp']):
                self.update_3d_render(d, sc)
        rt.redrawViews()

    def set_card_scale(self, v):
        self.lbl_card_scale.setText("{}%".format(v))
        s = v / 100.0
        for d in self.voi_widgets.values():
            if 'proxy' in d:
                d['proxy'].setScale(s)

    def fit_canvas(self):
        if self.voi_widgets:
            self.view.fitInView(self.scene.itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)

    def select_phoenix_sources(self):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        if not targets:
            targets = list(self.voi_widgets.keys())

        phx_nodes = []
        for nid in targets:
            d = self.voi_widgets[nid]
            if rt.isValidNode(d['sp']):
                idx = d['sp'].name.split("_")[-1]
                sn = "PHX_LiquidSrc_" + idx
                phx_node = rt.getNodeByName(sn)
                if phx_node:
                    phx_nodes.append(phx_node)

        if phx_nodes:
            rt.select(rt.array(*phx_nodes))
            rt.redrawViews()

    def on_canvas_selection(self, proxies, mode):
        nids_in = set()
        for p in proxies:
            if isinstance(p, VoiProxyWidget):
                nids_in.add(p.nid)

        current_sel = set(o.name for o in rt.selection if rt.isValidNode(o))
        new_nodes = []

        if mode == 'set':
            if not nids_in:
                rt.clearSelection()
                rt.redrawViews()
                return
            for nid in nids_in:
                d = self.voi_widgets.get(nid)
                if d:
                    if rt.isValidNode(d['base']):
                        new_nodes.append(d['base'])
                    if rt.isValidNode(d['sp']):
                        new_nodes.append(d['sp'])
            if new_nodes:
                rt.select(rt.array(*new_nodes))
            else:
                rt.clearSelection()

        elif mode == 'add':
            for o in rt.selection:
                if rt.isValidNode(o):
                    new_nodes.append(o)
            for nid in nids_in:
                d = self.voi_widgets.get(nid)
                if d:
                    if rt.isValidNode(d['base']) and d['base'].name not in current_sel:
                        new_nodes.append(d['base'])
                    if rt.isValidNode(d['sp']) and d['sp'].name not in current_sel:
                        new_nodes.append(d['sp'])
            if new_nodes:
                rt.select(rt.array(*new_nodes))

        elif mode == 'remove':
            remove_names = set()
            for nid in nids_in:
                d = self.voi_widgets.get(nid)
                if d:
                    if rt.isValidNode(d['base']):
                        remove_names.add(d['base'].name)
                    if rt.isValidNode(d['sp']):
                        remove_names.add(d['sp'].name)
            for o in rt.selection:
                if rt.isValidNode(o) and o.name not in remove_names:
                    new_nodes.append(o)
            if new_nodes:
                rt.select(rt.array(*new_nodes))
            else:
                rt.clearSelection()

        rt.redrawViews()

    def scan_and_setup(self):
        raw = []
        for o in rt.selection:
            if rt.isValidNode(o) and rt.isProperty(o, "pos"):
                if not o.name.startswith("DB9_Voi_Helper_") and not o.name.startswith("PHX_"):
                    raw.append(o)
        if not raw:
            QtWidgets.QMessageBox.warning(self, "Loi", "Chua chon Voi Phun hop le!")
            return
        self.reset_all()
        sc = self.get_u_scale()
        sorted_objs = sorted(raw, key=lambda o: rt.getProperty(o, 'pos').x)
        for i, obj in enumerate(sorted_objs):
            rgb = [int(x * 255) for x in colorsys.hsv_to_rgb(
                i / max(len(sorted_objs), 1), 0.75, 0.95
            )]
            idx = "{:02d}".format(i + 1)
            name = "DB9_Voi_Helper_" + idx
            rt.setProperty(obj, 'name', "DB9_Voi_Emitter_" + idx)
            sp = rt.Line(name=name, wirecolor=rt.color(rgb[0], rgb[1], rgb[2]))
            rt.addNewSpline(sp)
            for _ in range(3):
                rt.addKnot(sp, 1, rt.name("corner"), rt.name("line"),
                           rt.getProperty(obj, 'pos'))
            sp.render_renderable = True
            sp.render_thickness = 2.0
            sp.showFrozenInGray = False
            self.voi_widgets[name] = {
                'h': 100, 't': 0, 'a': 0,
                'sp': sp, 'base': obj, 'color': rgb,
            }
            self.add_card_ui(name, i // 6, i % 6)
            self.update_3d_render(self.voi_widgets[name], sc)
        # FIX 1: Call update_3d_render for all vois after scan so they point straight up Z
        sc = self.get_u_scale()
        for nid, d in self.voi_widgets.items():
            self.update_3d_render(d, sc)
        rt.redrawViews()
        self._last_frame = self._get_current_frame()
        if self.voi_widgets:
            self.view.fitInView(self.scene.itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)

    def auto_create_phoenix(self):
        count = 0
        em_val = 1
        if hasattr(self, 'cmb_phx_mode') and self.cmb_phx_mode.currentIndex() == 1:
            em_val = 0
            
        poly_id = 0
        if hasattr(self, 'spin_poly_id'):
            poly_id = self.spin_poly_id.value()

        for nid, d in self.voi_widgets.items():
            base = d['base']
            if not rt.isValidNode(base):
                continue
            bp = rt.getProperty(base, 'pos')
            idx = nid.split("_")[-1]
            sn = "PHX_LiquidSrc_" + idx
            fd = self.get_phoenix_velocity(d['h'])
            mxs = (
                '(local src = getNodeByName "{sn}";'
                ' if src == undefined do ('
                '   local ns = undefined;'
                '   try (ns = execute "LiquidSrc()") catch();'
                '   if ns == undefined do try (ns = execute "PhoenixFDLiquidSrc()") catch();'
                '   if ns != undefined do (ns.name = "{sn}"; ns.pos = [{px},{py},{pz}]; src = ns)'
                ' );'
                ' if src != undefined do ('
                '   local emt = getNodeByName "{bn}";'
                '   if emt != undefined do ('
                '     try (if isProperty src #sources then src.sources = #(emt)) catch();'
                '     try (if isProperty src #nodes then src.nodes = #(emt)) catch();'
                '     try (if isProperty src #emitterNodes then src.emitterNodes = #(emt)) catch()'
                '   );'
                '   try (if isProperty src #type then src.type = 1) catch();'
                '   try (if isProperty src #emitMode then src.emitMode = {em_val}) catch();'
                '   try (src.polyId = {poly_id}) catch();'
                '   try (if {poly_id} > 0 then src.polyIdOnly = true else src.polyIdOnly = false) catch()'
                ' );'
                ' (src != undefined))'
            ).format(sn=sn, px=bp.x, py=bp.y, pz=bp.z + 15, bn=base.name, em_val=em_val, poly_id=poly_id)
            ok = rt.execute(mxs)
            if ok:
                count += 1
                src = rt.getNodeByName(sn)
                if src:
                    for p in ['discharge', 'velocity', 'outvel', 'outgoingVelocity']:
                        try:
                            rt.setProperty(src, p, fd)
                        except Exception:
                            pass
        if count > 0:
            QtWidgets.QMessageBox.information(
                self, "OK",
                "Da tao {} Liquid Source!".format(count),
            )

    def add_card_ui(self, nid, r, c):
        d = self.voi_widgets[nid]
        rgb = d['color']

        box = QtWidgets.QFrame()
        box.setFixedWidth(185)
        box.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        box.setStyleSheet(
            "QFrame {{ background: rgba(15,17,26,220);"
            "border: 1.5px solid rgba({r},{g},{b},180);"
            "border-radius: 10px; padding: 4px; }}".format(r=rgb[0], g=rgb[1], b=rgb[2])
        )
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        hf = QtWidgets.QFrame()
        hf.setMinimumHeight(32)
        hf.setMaximumHeight(38)
        hf.setStyleSheet(
            "QFrame {{ background:qlineargradient(x1:0,x2:1,"
            "stop:0 rgb({r},{g},{b}),stop:1 rgba({r},{g},{b},80));"
            "border-radius:5px;border:none;padding:0px; }}".format(
                r=rgb[0], g=rgb[1], b=rgb[2]
            )
        )
        hl = QtWidgets.QHBoxLayout(hf)
        hl.setContentsMargins(6, 4, 4, 4)
        hl.setSpacing(3)
        ttl = QtWidgets.QLabel("VOI {}".format(nid[-2:]))
        ttl.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        ttl.setStyleSheet(
            "QLabel { font-weight:900;font-size:12px;color:white;letter-spacing:1px;"
            "border:none;background:transparent;padding:0px; }"
        )
        hl.addWidget(ttl)
        hl.addStretch()

        btn_qk = QtWidgets.QPushButton("K")
        btn_qk.setFixedSize(26, 26)
        btn_qk.setToolTip("CHOT KEY voi nay tai frame hien tai")
        btn_qk.setStyleSheet(
            "QPushButton { background:rgba(25,118,210,200);color:white;font-size:11px;"
            "font-weight:900;border:none;border-radius:13px;padding:0px;"
            "min-height:26px;min-width:26px; }"
            "QPushButton:hover { background:rgba(66,165,245,255); }"
        )
        btn_qk.clicked.connect(lambda c=False, n=nid: self._key_single_voi(n))
        hl.addWidget(btn_qk)

        br = QtWidgets.QPushButton("\u00d7")
        br.setFixedSize(24, 24)
        br.setStyleSheet(
            "QPushButton { background:rgba(255,50,50,180);color:white;font-size:14px;"
            "font-weight:900;border:none;border-radius:12px;padding:0px;"
            "min-height:24px;min-width:24px; }"
        )
        br.clicked.connect(lambda c=False, n=nid: self.reset_single_voi(n))
        hl.addWidget(br)
        lay.addWidget(hf)

        vel_label = QtWidgets.QLabel("VEL: --")
        vel_label.setAlignment(QtCore.Qt.AlignCenter)
        vel_label.setStyleSheet(
            "QLabel { color:#ff9800;font-size:9px;font-weight:bold;"
            "border:none;background:transparent; }"
        )
        d['lbl_vel'] = vel_label
        lay.addWidget(vel_label)

        hc = QtWidgets.QHBoxLayout()
        lh = QtWidgets.QLabel("LUC\nPHUN")
        lh.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        lh.setAlignment(QtCore.Qt.AlignCenter)
        lh.setStyleSheet(
            "QLabel { color:#4fc3f7;font-size:8px;font-weight:bold;"
            "border:none;background:transparent; }"
        )
        sh = QtWidgets.QSlider(QtCore.Qt.Vertical)
        sh.setRange(0, 1000)
        sh.setValue(d['h'])
        sh.setFixedHeight(90)
        sh.setStyleSheet(
            "QSlider::groove:vertical{width:6px;"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #4fc3f7,stop:1 #1a1a28);"
            "border-radius:3px;}"
            " QSlider::handle:vertical{background:#4fc3f7;height:16px;"
            "margin:0 -6px;border-radius:8px;border:1px solid #0288d1;}"
        )
        sh.valueChanged.connect(lambda v, n=nid: self.sync_values("h", n, v))
        lhv = ClickableValueLabel(str(d['h']))
        lhv.setStyleSheet(
            "QLabel { color:#4fc3f7;font-size:11px;font-weight:bold;"
            "border:none;background:transparent; }"
        )
        lhv.setFixedWidth(35)
        lhv.setToolTip("Double-click de go so truc tiep")
        hc.addStretch()
        hc.addWidget(lh)
        hc.addWidget(sh)
        hc.addWidget(lhv)
        hc.addStretch()
        lay.addLayout(hc)

        lt = QtWidgets.QLabel("NGHIENG")
        lt.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        lt.setStyleSheet("color:#aed581;font-size:8px;font-weight:bold;border:none;")
        lay.addWidget(lt, alignment=QtCore.Qt.AlignCenter)
        st = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        st.setRange(0, 500)
        st.setValue(d['t'])
        st.setMinimumHeight(18)
        st.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;"
            "background:qlineargradient(x1:0,x2:1,stop:0 #1a1a28,stop:1 #aed581);"
            "border-radius:2px;}"
            " QSlider::handle:horizontal{background:#aed581;width:14px;"
            "margin:-5px 0;border-radius:7px;border:1px solid #689f38;}"
        )
        st.valueChanged.connect(lambda v, n=nid: self.sync_values("t", n, v))
        ltv = ClickableValueLabel(str(d['t']))
        ltv.setStyleSheet("QLabel { color:#aed581;font-size:10px;font-weight:bold;border:none;background:transparent; }")
        ltv.setToolTip("Double-click de go so truc tiep")
        trow = QtWidgets.QHBoxLayout()
        trow.addWidget(st, stretch=1)
        trow.addWidget(ltv)
        lay.addLayout(trow)

        la = QtWidgets.QLabel("XOAY")
        la.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        la.setStyleSheet("color:#ce93d8;font-size:8px;font-weight:bold;border:none;")
        lay.addWidget(la, alignment=QtCore.Qt.AlignCenter)
        sa = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        sa.setRange(0, 360)
        sa.setValue(d['a'])
        sa.setMinimumHeight(18)
        sa.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;"
            "background:qlineargradient(x1:0,x2:1,stop:0 #1a1a28,stop:1 #ce93d8);"
            "border-radius:2px;}"
            " QSlider::handle:horizontal{background:#ce93d8;width:14px;"
            "margin:-5px 0;border-radius:7px;border:1px solid #8e24aa;}"
        )
        sa.valueChanged.connect(lambda v, n=nid: self.sync_values("a", n, v))
        lav = ClickableValueLabel(str(d['a']))
        lav.setStyleSheet("QLabel { color:#ce93d8;font-size:10px;font-weight:bold;border:none;background:transparent; }")
        lav.setToolTip("Double-click de go so truc tiep")
        arow = QtWidgets.QHBoxLayout()
        arow.addWidget(sa, stretch=1)
        arow.addWidget(lav)
        lay.addLayout(arow)

        d['sh'] = sh
        d['st'] = st
        d['sa'] = sa
        d['lbl_h_val'] = lhv
        d['lbl_t_val'] = ltv
        d['lbl_a_val'] = lav
        d['box'] = box

        if hasattr(self, 'chk_lock_range') and self.chk_lock_range.isChecked():
            lo = int(self.spin_out_min.value())
            hi = int(self.spin_out_max.value())
            sh.setRange(lo, hi)

        proxy = VoiProxyWidget(nid, self)
        proxy.setWidget(box)
        csv = getattr(self, 'sld_card_scale', None)
        if csv:
            proxy.setScale(csv.value() / 100.0)
        proxy.setPos(c * 200, r * 340)
        self.scene.addItem(proxy)
        d['proxy'] = proxy
        lhv.link(sh, nid, 'h', self)
        ltv.link(st, nid, 't', self)
        lav.link(sa, nid, 'a', self)

    def sync_values(self, attr, nid, v, respect_selection=True, redraw=True):
        d = self.voi_widgets[nid]
        d[attr] = v
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid]
        if respect_selection and (d['base'].name in sel_names or d['sp'].name in sel_names):
            targets = [n for n, dd in self.voi_widgets.items()
                       if dd['base'].name in sel_names or dd['sp'].name in sel_names]
        sc = self.get_u_scale()
        self._suppress_frame_read = True  
        for tid in targets:
            td = self.voi_widgets[tid]
            td[attr] = v
            ui_key = 's' + attr
            if ui_key in td:
                td[ui_key].blockSignals(True)
                td[ui_key].setValue(v)
                td[ui_key].blockSignals(False)
            if attr == 'h' and 'lbl_h_val' in td:
                td['lbl_h_val'].setText(str(v))
            if attr == 't' and 'lbl_t_val' in td:
                td['lbl_t_val'].setText(str(v))
            if attr == 'a' and 'lbl_a_val' in td:
                td['lbl_a_val'].setText(str(v))
            if attr == 'h' and 'lbl_vel' in td:
                phx_vel = self.get_phoenix_velocity(v)
                td['lbl_vel'].setText("VEL: {:.1f}".format(phx_vel))
            self.update_3d_render(td, sc, _respect_autokey=True)
            if attr == 'h':
                self._key_phoenix_velocity(td)
        self._suppress_frame_read = False
        if redraw:
            rt.redrawViews()

    def master_sync(self, mode, val):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        if not targets:
            targets = list(self.voi_widgets.keys())
        for nid in targets:
            self.sync_values(mode, nid, val, respect_selection=False, redraw=False)
        rt.redrawViews()

    def get_spatial_targets(self):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        if not targets:
            targets = list(self.voi_widgets.keys())
        if len(targets) < 2:
            return targets, lambda nid: 0.5

        positions = {}
        xs, ys = [], []
        for nid in targets:
            d = self.voi_widgets[nid]
            if rt.isValidNode(d['base']):
                p = rt.getProperty(d['base'], 'pos')
                positions[nid] = (p.x, p.y)
                xs.append(p.x)
                ys.append(p.y)

        if not xs:
            return targets, lambda nid: 0.5

        x_span = max(xs) - min(xs)
        y_span = max(ys) - min(ys)

        if x_span >= y_span:
            # Use X axis
            mn, mx = min(xs), max(xs)
            sp = mx - mn if mx != mn else 1.0
            def get_t(nid):
                return (positions.get(nid, (mn, 0))[0] - mn) / sp
        else:
            # Use Y axis
            mn, mx = min(ys), max(ys)
            sp = mx - mn if mx != mn else 1.0
            def get_t(nid):
                return (positions.get(nid, (0, mn))[1] - mn) / sp

        return targets, get_t

    def apply_spatial_curve(self):
        targets, get_t = self.get_spatial_targets()
        if not targets:
            return
        
        amp = self.sld_amp.value() / 100.0
        
        # Lấy giá trị min/max từ giao diện. Nếu đang bật Lock thì lấy theo user set.
        if hasattr(self, 'chk_lock_range') and self.chk_lock_range.isChecked():
            min_v = float(self.spin_out_min.value())
            max_v = float(self.spin_out_max.value())
        else:
            min_v = 0.0
            max_v = 1000.0
            
        mirror = self.chk_mirror.isChecked()
        phase_offset = self.sld_rotate.value() / 360.0

        for nid in targets:
            t = get_t(nid)
            if mirror:
                t = 1.0 - t
                
            t = (t - phase_offset) % 1.0
            
            # curve_y chạy từ 0.0 đến 1.0
            curve_y = self.curve_editor.get_y_at_t(t)
            
            # Áp dụng min/max vào kết quả của curve, có nhân thêm biên độ amp
            val = int(min_v + (max_v - min_v) * curve_y * amp)
            
            self.sync_values("h", nid, val, respect_selection=False, redraw=False)
        rt.redrawViews()

    def apply_spatial_curve_to_angle(self):
        targets, get_t = self.get_spatial_targets()
        if not targets:
            return
        mirror = self.chk_mirror.isChecked()
        
        phase_offset = self.sld_rotate.value() / 360.0

        for nid in targets:
            t = get_t(nid)
            if mirror:
                t = 1.0 - t
                
            t = (t - phase_offset) % 1.0
            
            val = int(self.curve_editor.get_y_at_t(t) * 360)
            self.sync_values("a", nid, val, respect_selection=False, redraw=False)
        rt.redrawViews()

    def update_amplitude(self, val):
        self.lbl_amp.setText("{}%".format(val))
        self.apply_spatial_curve()

    def set_curve_shape(self, pts):
        self.curve_editor.pts = copy.deepcopy(pts)
        self.curve_editor.update()
        self.apply_spatial_curve()

    def apply_rotation_preset(self):
        if hasattr(self, '_rot_timer') and self._rot_timer and self._rot_timer.isActive():
            self._rot_timer.stop()
            self._rot_timer = None
            self._rot_steps = None
            if hasattr(self, 'btn_rot_cancel'):
                self.btn_rot_cancel.setVisible(False)
            return

        mode = self.cmb_rotation.currentText()
        speed = self.sld_rot_speed.value()

        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        if not targets:
            targets = list(self.voi_widgets.keys())
        if not targets:
            return

        start_f, end_f = self._get_animation_range_frames()

        total = max(1, end_f - start_f)
        step  = max(1, total // (speed * 4))
        frames = list(range(start_f, end_f + 1, step))

        import random as _random
        steps = []
        for idx, nid in enumerate(targets):
            for f in frames:
                progress = (f - start_f) / total
                if mode == "Khong xoay":
                    angle = 0
                elif mode == "Xoay 360 lien tuc":
                    angle = int(progress * 360) % 360
                elif mode == "Xoay qua lai":
                    angle = int(math.sin(progress * math.pi * 2 * speed) * 180)
                elif mode == "Xoay ngau nhien":
                    angle = _random.randint(0, 360)
                elif mode == "Xoay theo nhom":
                    num_groups = max(2, len(targets) // 3)  
                    group_idx = idx // 3
                    phase_offset = (group_idx / num_groups) * 360
                    angle = int((progress * 360 + phase_offset) % 360)
                elif mode == "Lan song xoay":
                    phase_offset = (idx / max(1, len(targets))) * 360
                    angle = int(math.sin((progress * math.pi * 2 * speed) + math.radians(phase_offset)) * 180)
                elif mode == "Song curve":
                    total_frames_span = max(1, end_f - start_f)
                    t_val = (idx / max(len(targets) - 1, 1) + (f - start_f) / total_frames_span) % 1.0
                    angle = int(self.curve_editor.get_y_at_t(t_val) * 360)
                else:
                    angle = 0
                steps.append((nid, f, angle))

        if not steps:
            return

        self._rot_steps = iter(steps)
        self._rot_total = len(steps)
        self._rot_done  = 0

        if hasattr(self, 'btn_rot_cancel'):
            self.btn_rot_cancel.setVisible(True)

        def _tick():
            try:
                nid, f, angle = next(self._rot_steps)
                self._set_current_frame(f)
                self.sync_values("a", nid, angle, respect_selection=False, redraw=False)
                self.force_keyframe()
                self._rot_done += 1
                if self._rot_done % 10 == 0:
                    rt.redrawViews()
            except StopIteration:
                self._rot_timer.stop()
                self._rot_timer = None
                rt.redrawViews()
                if hasattr(self, 'btn_rot_cancel'):
                    self.btn_rot_cancel.setVisible(False)

        from PySide2 import QtCore as _QC
        self._rot_timer = _QC.QTimer()
        self._rot_timer.timeout.connect(_tick)
        self._rot_timer.start(16)  

    def set_minmax(self, mode):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        if not targets:
            targets = list(self.voi_widgets.keys())
        if mode == "min":
            val_h = int(self.spin_out_min.value())
        else:
            val_h = int(self.spin_out_max.value())
        for nid in targets:
            self.sync_values("h", nid, val_h, respect_selection=False, redraw=False)
        rt.redrawViews()

    def master_set_zero(self):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        if not targets:
            targets = list(self.voi_widgets.keys())
        for nid in targets:
            self.sync_values("h", nid, 0, respect_selection=False, redraw=False)
            self.sync_values("t", nid, 0, respect_selection=False, redraw=False)
            self.sync_values("a", nid, 0, respect_selection=False, redraw=False)
        rt.redrawViews()

    def reset_single_voi(self, nid):
        if nid in self.voi_widgets:
            self.sync_values("h", nid, 0, respect_selection=False, redraw=False)
            self.sync_values("t", nid, 0, respect_selection=False, redraw=False)
            self.sync_values("a", nid, 0, respect_selection=False, redraw=False)
            rt.redrawViews()

    def save_group(self):
        gn = self.txt_grp.text().strip()
        if not gn:
            return
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        if not sel_names:
            QtWidgets.QMessageBox.warning(self, "Loi", "Chua chon doi tuong!")
            return
        self.groups_log[gn] = list(sel_names)
        self.refresh_group_ui()

    def delete_group(self):
        gn = self.txt_grp.text().strip()
        if gn in self.groups_log:
            del self.groups_log[gn]
            self._refresh_group_buttons()

    def _refresh_group_buttons(self):
        while self.grp_btns_lay.count():
            w = self.grp_btns_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for gn in self.groups_log:
            btn = QtWidgets.QPushButton(gn)
            btn.setObjectName("BTN_" + gn)
            btn._act = False
            btn.setStyleSheet("border:2px solid #333346;color:#ffa726;")
            btn.clicked.connect(lambda c=False, n=gn: self.select_group(n))
            self.grp_btns_lay.addWidget(btn)

    refresh_group_ui = _refresh_group_buttons

    def select_group(self, gn):
        names = self.groups_log.get(gn, [])
        nodes = []
        for n in names:
            obj = rt.getNodeByName(n)
            if obj and rt.isValidNode(obj):
                nodes.append(obj)
        if nodes:
            rt.select(rt.array(*nodes))
            rt.redrawViews()

    def save_preset(self):
        pn = self.txt_preset.text().strip()
        if not pn or not self.voi_widgets:
            return
        data = {}
        for nid, d in self.voi_widgets.items():
            data[nid] = {'h': d['h'], 't': d['t'], 'a': d['a']}
        self.custom_presets[pn] = data
        existing = [self.cmb_presets.itemText(i) for i in range(self.cmb_presets.count())]
        if pn not in existing:
            self.cmb_presets.addItem(pn)
        self._refresh_preset_tags()

    def _refresh_preset_tags(self):
        """FIX 4: Refresh pill-shaped preset tag buttons."""
        if not hasattr(self, 'preset_tags_lay'):
            return
        while self.preset_tags_lay.count():
            item = self.preset_tags_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for pname in self.custom_presets:
            btn = QtWidgets.QPushButton(pname)
            btn.setStyleSheet(
                "QPushButton { background:#1a237e; color:#90caf9; border:1px solid #3949ab;"
                " border-radius:10px; padding:2px 10px; font-size:11px; }"
                "QPushButton:hover { background:#283593; }"
            )
            btn.clicked.connect(lambda checked, n=pname: self._load_preset_by_name(n))
            btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, n=pname, b=btn: self._delete_preset_tag(n, b)
            )
            self.preset_tags_lay.addWidget(btn)

    def _load_preset_by_name(self, pname):
        """FIX 4: Load a preset by name."""
        pd = self.custom_presets.get(pname)
        if not pd:
            return
        for nid, vals in pd.items():
            if nid not in self.voi_widgets:
                continue
            self.sync_values("h", nid, vals['h'],
                             respect_selection=False, redraw=False)
            self.sync_values("t", nid, vals['t'],
                             respect_selection=False, redraw=False)
            self.sync_values("a", nid, vals['a'],
                             respect_selection=False, redraw=False)
        self.force_keyframe()
        rt.redrawViews()

    def _delete_preset_tag(self, pname, btn):
        """FIX 4: Delete a preset via right-click on tag."""
        if pname in self.custom_presets:
            del self.custom_presets[pname]
            idx = self.cmb_presets.findText(pname)
            if idx >= 0:
                self.cmb_presets.removeItem(idx)
        btn.deleteLater()

    def load_preset(self):
        pn = self.cmb_presets.currentText()
        pd = self.custom_presets.get(pn)
        if not pd:
            return
        for nid, vals in pd.items():
            if nid not in self.voi_widgets:
                continue
            self.sync_values("h", nid, vals['h'],
                             respect_selection=False, redraw=False)
            self.sync_values("t", nid, vals['t'],
                             respect_selection=False, redraw=False)
            self.sync_values("a", nid, vals['a'],
                             respect_selection=False, redraw=False)
        self.force_keyframe()
        rt.redrawViews()

    # XÓA PRESET ĐƯỢC CHỌN TRONG COMBOBOX
    def delete_preset(self):
        pn = self.cmb_presets.currentText()
        if pn in self.custom_presets:
            del self.custom_presets[pn]
            idx = self.cmb_presets.findText(pn)
            if idx >= 0:
                self.cmb_presets.removeItem(idx)
            self._refresh_preset_tags()

    def export_presets(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Presets", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        voi_state = {}
        for nid, d in self.voi_widgets.items():
            base_name = d['base'].name if rt.isValidNode(d['base']) else ''
            sp_name = d['sp'].name if rt.isValidNode(d['sp']) else ''
            voi_state[nid] = {
                'h': d['h'], 't': d['t'], 'a': d['a'],
                'base_name': base_name, 'sp_name': sp_name,
                'color': d.get('color', [100, 180, 255]),
            }
        # FIX 3: Export keyframe data
        keyframe_data = {}
        for nid, d in self.voi_widgets.items():
            if not rt.isValidNode(d['sp']):
                continue
            sp_name = d['sp'].name
            frames = self._get_key_frames_for_node(sp_name)
            frame_states = {}
            for fr in frames:
                mxs = (
                    '(local sp = getNodeByName "{n}"; local res = #();'
                    ' if sp != undefined do ('
                    '   at time {f} ('
                    '     append res (getKnotPoint sp 1 1);'
                    '     append res (getKnotPoint sp 1 2);'
                    '     append res (getKnotPoint sp 1 3)'
                    '   )'
                    ' ); res)'
                ).format(n=sp_name, f=fr)
                result = rt.execute(mxs)
                if result and len(result) >= 3:
                    frame_states[str(fr)] = [
                        [result[0].x, result[0].y, result[0].z],
                        [result[1].x, result[1].y, result[1].z],
                        [result[2].x, result[2].y, result[2].z],
                    ]
            if frame_states:
                keyframe_data[nid] = {'sp_name': sp_name, 'frames': frame_states}

        export_data = {
            'version': 'DB9_Fountain_v104',
            'presets': self.custom_presets,
            'groups': self.groups_log,
            'voi_state': voi_state,
            'curve_pts': self.curve_editor.pts,
            'amp_value': self.sld_amp.value(),
            'vel_min': self.spin_out_min.value(),
            'vel_max': self.spin_out_max.value(),
            'keyframe_data': keyframe_data,
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            QtWidgets.QMessageBox.information(
                self, "Export", "Da export {} preset(s), {} nhom(s), {} voi(s) ra:\n{}".format(
                    len(self.custom_presets), len(self.groups_log), len(voi_state), path))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Export Error", str(e))

    def import_presets(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Presets", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            imported_presets = data.get('presets', {})
            for pn, pd in imported_presets.items():
                self.custom_presets[pn] = pd
                existing = [self.cmb_presets.itemText(i) for i in range(self.cmb_presets.count())]
                if pn not in existing:
                    self.cmb_presets.addItem(pn)
            self._refresh_preset_tags()
            imported_groups = data.get('groups', {})
            for gn, names in imported_groups.items():
                self.groups_log[gn] = names
            self._refresh_group_buttons()

            curve_pts = data.get('curve_pts')
            if curve_pts:
                self.curve_editor.pts = curve_pts
                self.curve_editor.update()

            amp_val = data.get('amp_value')
            if amp_val is not None:
                self.sld_amp.setValue(int(amp_val))
            vel_min = data.get('vel_min')
            if vel_min is not None:
                self.spin_out_min.setValue(float(vel_min))
            vel_max = data.get('vel_max')
            if vel_max is not None:
                self.spin_out_max.setValue(float(vel_max))

            voi_state = data.get('voi_state', {})
            restored = 0
            if voi_state:
                base_to_nid = {}
                for nid, d in self.voi_widgets.items():
                    if rt.isValidNode(d['base']):
                        base_to_nid[d['base'].name] = nid

                for saved_nid, sv in voi_state.items():
                    target_nid = None
                    if saved_nid in self.voi_widgets:
                        target_nid = saved_nid
                    elif sv.get('base_name') and sv['base_name'] in base_to_nid:
                        target_nid = base_to_nid[sv['base_name']]
                    if target_nid:
                        self.sync_values('h', target_nid, int(sv.get('h', 0)), respect_selection=False, redraw=False)
                        self.sync_values('t', target_nid, int(sv.get('t', 0)), respect_selection=False, redraw=False)
                        self.sync_values('a', target_nid, int(sv.get('a', 0)), respect_selection=False, redraw=False)
                        restored += 1

                if voi_state and restored == 0:
                    QtWidgets.QMessageBox.warning(self, "Import",
                        "Vui long SCAN voi truoc, roi import lai\n"
                        "(Khong tim thay voi nao khop voi du lieu da luu)")
                else:
                    rt.redrawViews()

            # FIX 3: Restore keyframes from keyframe_data
            keyframe_data = data.get('keyframe_data', {})
            keys_restored = 0
            for saved_nid, kd in keyframe_data.items():
                target_nid = None
                if saved_nid in self.voi_widgets:
                    target_nid = saved_nid
                elif kd.get('sp_name'):
                    for nid, d in self.voi_widgets.items():
                        if rt.isValidNode(d['sp']) and d['sp'].name == kd['sp_name']:
                            target_nid = nid
                            break
                if not target_nid:
                    continue
                sp = self.voi_widgets[target_nid]['sp']
                sp_name = sp.name
                for fr_str, knots in kd['frames'].items():
                    fr = int(fr_str)
                    k1, k2, k3 = knots
                    mxs = (
                        '(local sp = getNodeByName "{n}";'
                        ' if sp != undefined do ('
                        '   with animate on at time {f}f ('
                        '     setKnotPoint sp 1 1 [{k1x},{k1y},{k1z}];'
                        '     setKnotPoint sp 1 2 [{k2x},{k2y},{k2z}];'
                        '     setKnotPoint sp 1 3 [{k3x},{k3y},{k3z}];'
                        '     updateShape sp'
                        '   )'
                        ' ))'
                    ).format(n=sp_name, f=fr, k1x=k1[0], k1y=k1[1], k1z=k1[2],
                             k2x=k2[0], k2y=k2[1], k2z=k2[2], k3x=k3[0], k3y=k3[1], k3z=k3[2])
                    rt.execute(mxs)
                    keys_restored += 1

            QtWidgets.QMessageBox.information(
                self, "Import", "Da import {} preset(s), {} nhom(s), {} voi(s), {} keyframe(s) tu:\n{}".format(
                    len(imported_presets), len(imported_groups), restored, keys_restored, path))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Import Error", str(e))

    def force_keyframe(self):
        f = self._get_current_frame()
        sc = self.get_u_scale()
        with pymxs.undo(True, "Force Keyframe"):
            for nid, d in self.voi_widgets.items():
                if not rt.isValidNode(d['sp']):
                    continue
                rad = math.radians(d['a'])
                bp = rt.getProperty(d['base'], 'pos')
                tip_x = bp.x + d['t'] * sc * math.cos(rad)
                tip_y = bp.y + d['t'] * sc * math.sin(rad)
                tip_z = bp.z + d['h'] * sc
                arr_x = tip_x + 15 * sc * math.cos(rad)
                arr_y = tip_y + 15 * sc * math.sin(rad)
                arr_z = tip_z

                sp_name = d['sp'].name
                mxs = (
                    '(local sp = getNodeByName "{sp_name}";'
                    ' if sp != undefined do ('
                    '   with animate on at time {f}f ('
                    '     setKnotPoint sp 1 1 [{k1x},{k1y},{k1z}];'
                    '     setKnotPoint sp 1 2 [{k2x},{k2y},{k2z}];'
                    '     setKnotPoint sp 1 3 [{k3x},{k3y},{k3z}];'
                    '     updateShape sp'
                    '   );'
                    '   try ('
                    '     local bo = sp.baseObject;'
                    '     if bo != undefined and bo.numsubs > 0 do ('
                    '       for si = 1 to bo.numsubs do ('
                    '         local sa = getSubAnim bo si;'
                    '         if sa != undefined and sa.controller != undefined do ('
                    '           try (addNewKey sa.controller {f}f) catch()'
                    '         )'
                    '       )'
                    '     )'
                    '   ) catch();'
                    '   try ('
                    '     with animate on at time {f}f ('
                    '       sp.pos = sp.pos'
                    '     )'
                    '   ) catch()'
                    ' ))'
                ).format(
                    sp_name=sp_name, f=f,
                    k1x=bp.x, k1y=bp.y, k1z=bp.z,
                    k2x=tip_x, k2y=tip_y, k2z=tip_z,
                    k3x=arr_x, k3y=arr_y, k3z=arr_z,
                )
                rt.execute(mxs)

                self._key_phoenix_velocity(d)

    def reset_keyframes(self):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        targets = [nid for nid, d in self.voi_widgets.items()
                   if d['base'].name in sel_names or d['sp'].name in sel_names]
        if not targets:
            targets = list(self.voi_widgets.keys())

        count = 0
        with pymxs.undo(True, "Reset Keyframes"):
            for nid in targets:
                d = self.voi_widgets[nid]
                if rt.isValidNode(d['sp']):
                    sp_name = d['sp'].name
                    mxs = (
                        '(local sp = getNodeByName "{sp}";'
                        ' if sp != undefined do ('
                        '   fn deleteKeysRecursive obj = ('
                        '     try (deleteKeys obj #allKeys) catch();'
                        '     for i = 1 to obj.numsubs do ('
                        '       local sa = getSubAnim obj i;'
                        '       if sa != undefined do ('
                        '         try (deleteKeys sa #allKeys) catch();'
                        '         if sa.controller != undefined do'
                        '           try (deleteKeys sa.controller #allKeys) catch();'
                        '         deleteKeysRecursive sa'
                        '       )'
                        '     )'
                        '   );'
                        '   deleteKeysRecursive sp;'
                        '   try (deleteKeysRecursive sp.baseObject) catch()'
                        ' ))'
                    ).format(sp=sp_name)
                    rt.execute(mxs)
                    count += 1

                if self.chk_phoenix.isChecked():
                    idx = d['sp'].name.split("_")[-1] if rt.isValidNode(d['sp']) else ""
                    sn = "PHX_LiquidSrc_" + idx
                    mxs_phx = (
                        '(local src = getNodeByName "{sn}";'
                        ' if src != undefined do ('
                        '   fn deleteKeysRecursive obj = ('
                        '     try (deleteKeys obj #allKeys) catch();'
                        '     for i = 1 to obj.numsubs do ('
                        '       local sa = getSubAnim obj i;'
                        '       if sa != undefined do ('
                        '         try (deleteKeys sa #allKeys) catch();'
                        '         if sa.controller != undefined do'
                        '           try (deleteKeys sa.controller #allKeys) catch();'
                        '         deleteKeysRecursive sa'
                        '       )'
                        '     )'
                        '   );'
                        '   deleteKeysRecursive src;'
                        '   try (deleteKeysRecursive src.baseObject) catch()'
                        ' ))'
                    ).format(sn=sn)
                    rt.execute(mxs_phx)

        if count > 0:
            rt.redrawViews()

    def _build_keyframe_timeline(self):
        grp = QtWidgets.QGroupBox("KEYFRAME TIMELINE")
        grp.setStyleSheet(
            "QGroupBox { color: #64b5f6; font-weight: bold; font-size: 11px;"
            " border: 1px solid #1a237e; margin-top: 16px; padding-top: 16px;"
            " border-radius: 6px; background-color: #0a0a14; }"
            "QGroupBox::title { subcontrol-origin: margin;"
            " subcontrol-position: top left; left: 10px; padding: 0 6px; }"
        )
        lay = QtWidgets.QVBoxLayout(grp)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        # FIX 2b: Step row ABOVE timeline ruler
        step_row = QtWidgets.QHBoxLayout()
        step_row.addWidget(QtWidgets.QLabel("BUOC:"))
        self.spin_frame_step = QtWidgets.QSpinBox()
        self.spin_frame_step.setRange(1, 1000)
        self.spin_frame_step.setValue(10)
        self.spin_frame_step.setFixedWidth(60)
        step_row.addWidget(self.spin_frame_step)
        btn_prev_n = QtWidgets.QPushButton("◀ -N")
        btn_prev_n.setFixedWidth(70)
        btn_prev_n.setStyleSheet("color:#64b5f6;font-weight:bold;")
        btn_prev_n.clicked.connect(self._step_frame_back)
        btn_next_n = QtWidgets.QPushButton("+N ▶")
        btn_next_n.setFixedWidth(70)
        btn_next_n.setStyleSheet("color:#64b5f6;font-weight:bold;")
        btn_next_n.clicked.connect(self._step_frame_forward)
        step_row.addWidget(btn_prev_n)
        step_row.addWidget(btn_next_n)
        step_row.addStretch()
        lay.addLayout(step_row)

        filt_row = QtWidgets.QHBoxLayout()
        self.cmb_tl_filter = QtWidgets.QComboBox()
        self.cmb_tl_filter.addItems(["TAT CA", "DANG CHON", "NHOM"])
        self.cmb_tl_filter.setFixedWidth(100)
        self.cmb_tl_filter.currentIndexChanged.connect(self._refresh_timeline)
        filt_row.addWidget(QtWidgets.QLabel("Hien thi:"))
        filt_row.addWidget(self.cmb_tl_filter)
        self.btn_tl_refresh = QtWidgets.QPushButton("⟳ LAM MOI")
        self.btn_tl_refresh.setFixedWidth(90)
        self.btn_tl_refresh.clicked.connect(self._refresh_timeline)
        filt_row.addWidget(self.btn_tl_refresh)

        self.btn_goto_key = QtWidgets.QPushButton("→ DI TOI KEY")
        self.btn_goto_key.setFixedWidth(100)
        self.btn_goto_key.setStyleSheet("color:#4fc3f7;font-weight:bold;")
        self.btn_goto_key.clicked.connect(self._goto_selected_key)
        filt_row.addWidget(self.btn_goto_key)

        # NÚT XOÁ KEY DÀNH CHO KEYFRAME ĐANG ĐƯỢC CHỌN
        self.btn_del_key = QtWidgets.QPushButton("✕ XOA KEY")
        self.btn_del_key.setStyleSheet("color:#ef5350;font-weight:bold;")
        self.btn_del_key.clicked.connect(self._ui_delete_specific_key)
        self.btn_del_key.setToolTip("Xoa Keyframe dang duoc chon tren Timeline (phim tat: Delete)")
        filt_row.addWidget(self.btn_del_key)

        filt_row.addStretch()
        lay.addLayout(filt_row)

        self.tl_widget_main = KeyframeTimelineWidget()
        self.tl_widget_main.key_deleted.connect(self._delete_specific_key)
        self.tl_widget_main.setMinimumHeight(60)
        # FIX 2c: Auto-scale to actual 3ds Max timeline range
        start_f, end_f = self._get_animation_range_frames()
        self.tl_widget_main.set_frame_range(start_f, end_f)
        self.tl_widget_main._visible_range = (start_f, end_f)
        self.tl_widget_main.set_current_frame(self._last_frame or 0)
        lay.addWidget(self.tl_widget_main, stretch=1)

        self._tl_grp = grp
        return grp

    def _ui_delete_specific_key(self):
        if self.tl_widget_main._selected_key:
            nid, frame = self.tl_widget_main._selected_key
            self._delete_specific_key(nid, frame)
            self.tl_widget_main._selected_key = None

    # HÀM XÓA CHÍNH XÁC 1 KEYFRAME TRÊN MAX (DO USER CHỌN TỪ TIMELINE PLUGIN)
    def _delete_specific_key(self, nid, frame):
        d = self.voi_widgets.get(nid)
        if not d:
            return

        with pymxs.undo(True, "Delete Specific Key"):
            # Xóa key của node Spilne (Helper)
            if rt.isValidNode(d['sp']):
                sp_name = d['sp'].name
                mxs = (
                    '(local obj = getNodeByName "{name}";'
                    ' if obj != undefined do ('
                    '   fn deleteKeyAtFrame o f_time = ('
                    '     for i = 1 to o.numsubs do ('
                    '       local sa = getSubAnim o i;'
                    '       if sa != undefined do ('
                    '         if sa.controller != undefined and sa.controller.keys != undefined do ('
                    '           for k = sa.controller.keys.count to 1 by -1 do ('
                    '             local ft = (sa.controller.keys[k].time as integer) / ticksPerFrame;'
                    '             if ft == f_time do deleteKey sa.controller k;'
                    '           )'
                    '         );'
                    '         deleteKeyAtFrame sa f_time;'
                    '       )'
                    '     )'
                    '   );'
                    '   deleteKeyAtFrame obj {f};'
                    '   if obj.baseObject != undefined do deleteKeyAtFrame obj.baseObject {f};'
                    ' ))'
                ).format(name=sp_name, f=frame)
                rt.execute(mxs)

            # Xóa key của Phoenix Source
            idx = sp_name.split("_")[-1] if rt.isValidNode(d['sp']) else ""
            sn = "PHX_LiquidSrc_" + idx
            mxs_phx = (
                '(local obj = getNodeByName "{name}";'
                ' if obj != undefined do ('
                '   fn deleteKeyAtFrame o f_time = ('
                '     for i = 1 to o.numsubs do ('
                '       local sa = getSubAnim o i;'
                '       if sa != undefined do ('
                '         if sa.controller != undefined and sa.controller.keys != undefined do ('
                '           for k = sa.controller.keys.count to 1 by -1 do ('
                '             local ft = (sa.controller.keys[k].time as integer) / ticksPerFrame;'
                '             if ft == f_time do deleteKey sa.controller k;'
                '           )'
                '         );'
                '         deleteKeyAtFrame sa f_time;'
                '       )'
                '     )'
                '   );'
                '   deleteKeyAtFrame obj {f};'
                '   if obj.baseObject != undefined do deleteKeyAtFrame obj.baseObject {f};'
                ' ))'
            ).format(name=sn, f=frame)
            rt.execute(mxs_phx)

        self._refresh_timeline()
        rt.redrawViews()

    def _step_frame_forward(self):
        try:
            self._set_current_frame(self._get_current_frame() + self.spin_frame_step.value())
            rt.redrawViews()
        except Exception:
            pass

    def _step_frame_back(self):
        try:
            self._set_current_frame(max(0, self._get_current_frame() - self.spin_frame_step.value()))
            rt.redrawViews()
        except Exception:
            pass

    def _get_key_frames_for_node(self, node_name):
        mxs = (
            '(local nd = getNodeByName "{n}";'
            ' local result = #();'
            ' if nd != undefined do ('
            '   fn collectKeysRecursive obj = ('
            '     for i = 1 to obj.numsubs do ('
            '       local sa = getSubAnim obj i;'
            '       if sa != undefined do ('
            '         try ('
            '           if sa.controller != undefined and sa.controller.keys != undefined do ('
            '             for k = 1 to sa.controller.keys.count do ('
            '               local ft = (sa.controller.keys[k].time as integer) / ticksPerFrame;'
            '               appendIfUnique result ft'
            '             )'
            '           )'
            '         ) catch();'
            '         collectKeysRecursive sa'
            '       )'
            '     )'
            '   );'
            '   collectKeysRecursive nd;'
            '   try ('
            '     if nd.baseObject != undefined do collectKeysRecursive nd.baseObject'
            '   ) catch()'
            ' ); sort result; result)'
        ).format(n=node_name)
        try:
            result = rt.execute(mxs)
            if result is not None:
                return [int(f) for f in result]
        except Exception:
            pass
        return []

    def _get_key_frames_for_phx(self, sn):
        mxs = (
            '(local src = getNodeByName "{sn}";'
            ' local result = #();'
            ' if src != undefined do ('
            '   fn collectKeysRecursive obj = ('
            '     for i = 1 to obj.numsubs do ('
            '       local sa = getSubAnim obj i;'
            '       if sa != undefined do ('
            '         try ('
            '           if sa.controller != undefined and sa.controller.keys != undefined do ('
            '             for k = 1 to sa.controller.keys.count do ('
            '               local ft = (sa.controller.keys[k].time as integer) / ticksPerFrame;'
            '               appendIfUnique result ft'
            '             )'
            '           )'
            '         ) catch();'
            '         collectKeysRecursive sa'
            '       )'
            '     )'
            '   );'
            '   collectKeysRecursive src;'
            '   try ('
            '     if src.baseObject != undefined do collectKeysRecursive src.baseObject'
            '   ) catch()'
            ' ); sort result; result)'
        ).format(sn=sn)
        try:
            result = rt.execute(mxs)
            if result is not None:
                return [int(f) for f in result]
        except Exception:
            pass
        return []

    def _refresh_timeline(self):
        start_f, end_f = self._get_animation_range_frames()

        if hasattr(self, 'tl_widget_main'):
            self.tl_widget_main.set_frame_range(start_f, end_f)
            self.tl_widget_main._visible_range = (start_f, end_f)

        filt = self.cmb_tl_filter.currentText()
        targets = []
        if filt == "DANG CHON":
            sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
            targets = [(nid, d) for nid, d in self.voi_widgets.items()
                       if d['base'].name in sel_names or d['sp'].name in sel_names]
        elif filt == "NHOM":
            for gn, names in self.groups_log.items():
                for nid, d in self.voi_widgets.items():
                    if d['base'].name in names or d['sp'].name in names:
                        if (nid, d) not in targets:
                            targets.append((nid, d))
        else:
            targets = list(self.voi_widgets.items())

        if not targets:
            if hasattr(self, 'tl_widget_main'):
                self.tl_widget_main.set_keys({})
            return

        key_data = {}
        for nid, d in targets:
            sp_keys = []
            phx_keys = []
            if rt.isValidNode(d['sp']):
                sp_keys = self._get_key_frames_for_node(d['sp'].name)
                idx = d['sp'].name.split("_")[-1]
                sn = "PHX_LiquidSrc_" + idx
                phx_keys = self._get_key_frames_for_phx(sn)

            all_keys = sorted(set(sp_keys + phx_keys))
            short_name = nid.split("_")[-1] if "_" in nid else nid[-4:]
            rgb = d.get('color', [100, 180, 255])
            
            # Cấu trúc dictionary pass qua tl_widget_main để có name rõ ràng
            key_data[nid] = {
                'name': short_name,
                'keys': all_keys,
                'color': (rgb[0], rgb[1], rgb[2]),
            }

        if hasattr(self, 'tl_widget_main'):
            self.tl_widget_main.set_keys(key_data)

    def _goto_frame(self, f):
        try:
            self._set_current_frame(f)
            rt.redrawViews()
        except Exception:
            pass

    def _goto_selected_key(self):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        cur = self._get_current_frame()
        next_keys = []
        for nid, d in self.voi_widgets.items():
            if d['base'].name in sel_names or d['sp'].name in sel_names:
                if rt.isValidNode(d['sp']):
                    sp_keys = self._get_key_frames_for_node(d['sp'].name)
                    idx = d['sp'].name.split("_")[-1]
                    phx_keys = self._get_key_frames_for_phx("PHX_LiquidSrc_" + idx)
                    for k in sorted(set(sp_keys + phx_keys)):
                        if k > cur:
                            next_keys.append(k)
                            break
        if next_keys:
            self._goto_frame(min(next_keys))

    def auto_map_from_3d(self):
        if not self.voi_widgets:
            return
        xs, ys = [], []
        for d in self.voi_widgets.values():
            if rt.isValidNode(d['base']):
                p = rt.getProperty(d['base'], 'pos')
                xs.append(p.x)
                ys.append(p.y)
        if not xs:
            return
        mn_x, mx_x = min(xs), max(xs)
        mn_y, mx_y = min(ys), max(ys)
        sp_x = mx_x - mn_x if mx_x != mn_x else 1.0
        sp_y = mx_y - mn_y if mx_y != mn_y else 1.0
        for nid, d in self.voi_widgets.items():
            if rt.isValidNode(d['base']) and 'proxy' in d:
                p = rt.getProperty(d['base'], 'pos')
                px = ((p.x - mn_x) / sp_x) * 1200
                py = (1.0 - (p.y - mn_y) / sp_y) * 800
                d['proxy'].setPos(px, py)

    def sync_selection_from_max(self):
        if self.syncing_selection:
            return
        try:
            self.syncing_selection = True
            sn = set(o.name for o in rt.selection if rt.isValidNode(o))
            if sn == self._last_sel_names:
                return
            self._last_sel_names = sn

            for gn, names in self.groups_log.items():
                btn = self.findChild(QtWidgets.QPushButton, "BTN_" + gn)
                if btn:
                    act = all(n in sn for n in names) if names else False
                    if getattr(btn, '_act', None) != act:
                        btn._act = act
                        clr = "#00e676" if act else "#333346"
                        txt = "#00e676" if act else "#ffa726"
                        btn.setStyleSheet("border:2px solid {};color:{};".format(clr, txt))

            self.scene.blockSignals(True)
            for nid, d in self.voi_widgets.items():
                if 'proxy' not in d:
                    continue
                act = ((rt.isValidNode(d['base']) and d['base'].name in sn) or
                       (rt.isValidNode(d['sp']) and d['sp'].name in sn))
                if getattr(d['box'], '_act', None) != act:
                    d['box']._act = act
                    d['proxy'].setSelected(act)
                    rgb = d['color']
                    if act:
                        d['box'].setStyleSheet(
                            "QFrame { background: rgba(10,20,35,240);"
                            "border: 2px solid #4fc3f7;"
                            "border-radius: 10px; padding: 4px; }"
                        )
                        for lbl in d['box'].findChildren(QtWidgets.QLabel):
                            if not hasattr(lbl, '_orig_style'):
                                lbl._orig_style = lbl.styleSheet()
                            cur = lbl.styleSheet()
                            import re
                            cur_clean = re.sub(r'color\s*:\s*[^;]+;?', '', cur)
                            lbl.setStyleSheet("color: white; " + cur_clean)
                    else:
                        rgb = d['color']
                        d['box'].setStyleSheet(
                            "QFrame {{ background: rgba(15,17,26,220);"
                            "border: 1.5px solid rgba({r},{g},{b},180);"
                            "border-radius: 10px; padding: 4px; }}".format(r=rgb[0], g=rgb[1], b=rgb[2])
                        )
                        for lbl in d['box'].findChildren(QtWidgets.QLabel):
                            if hasattr(lbl, '_orig_style'):
                                lbl.setStyleSheet(lbl._orig_style)
            self.scene.blockSignals(False)
        except Exception:
            pass
        finally:
            self.syncing_selection = False

    def focus_selected_vois(self):
        sel_names = [o.name for o in rt.selection if rt.isValidNode(o)]
        rects = []
        for nid, d in self.voi_widgets.items():
            if 'proxy' in d:
                if d['base'].name in sel_names or d['sp'].name in sel_names:
                    rects.append(d['proxy'].sceneBoundingRect())
        if rects:
            union = rects[0]
            for r in rects[1:]:
                union = union.united(r)
            self.view.fitInView(union, QtCore.Qt.KeepAspectRatio)

    def _key_single_voi(self, nid):
        d = self.voi_widgets.get(nid)
        if not d:
            return
        f = self._get_current_frame()
        sc = self.get_u_scale()
        if not rt.isValidNode(d['sp']):
            return
        rad = math.radians(d['a'])
        bp = rt.getProperty(d['base'], 'pos')
        tip_x = bp.x + d['t'] * sc * math.cos(rad)
        tip_y = bp.y + d['t'] * sc * math.sin(rad)
        tip_z = bp.z + d['h'] * sc
        arr_x = tip_x + 15 * sc * math.cos(rad)
        arr_y = tip_y + 15 * sc * math.sin(rad)
        arr_z = tip_z

        sp_name = d['sp'].name
        with pymxs.undo(True, "Key Single Voi"):
            mxs = (
                '(local sp = getNodeByName "{sp_name}";'
                ' if sp != undefined do ('
                '   with animate on at time {f}f ('
                '     setKnotPoint sp 1 1 [{k1x},{k1y},{k1z}];'
                '     setKnotPoint sp 1 2 [{k2x},{k2y},{k2z}];'
                '     setKnotPoint sp 1 3 [{k3x},{k3y},{k3z}];'
                '     updateShape sp'
                '   )'
                ' ))'
            ).format(
                sp_name=sp_name, f=f,
                k1x=bp.x, k1y=bp.y, k1z=bp.z,
                k2x=tip_x, k2y=tip_y, k2z=tip_z,
                k3x=arr_x, k3y=arr_y, k3z=arr_z,
            )
            rt.execute(mxs)

            mxs2 = (
                '(local sp = getNodeByName "{sp_name}";'
                ' if sp != undefined do ('
                '   local bo = sp.baseObject;'
                '   if bo != undefined do ('
                '     fn keyAllSubAnims obj t = ('
                '       for i = 1 to obj.numsubs do ('
                '         local sa = getSubAnim obj i;'
                '         if sa != undefined do ('
                '           if sa.controller != undefined do ('
                '             try (addNewKey sa.controller t) catch()'
                '           );'
                '           keyAllSubAnims sa t'
                '         )'
                '       )'
                '     );'
                '     keyAllSubAnims bo ({f}f);'
                '     try ('
                '       local mpc = sp.baseObject[#Master_Point_Controller];'
                '       if mpc != undefined do (keyAllSubAnims mpc ({f}f))'
                '     ) catch()'
                '   )'
                ' ))'
            ).format(sp_name=sp_name, f=f)
            rt.execute(mxs2)

            self._key_phoenix_velocity(d)
        rt.redrawViews()

    def push_outgoing_to_phoenix(self):
        for nid, d in self.voi_widgets.items():
            self._key_phoenix_velocity(d)

    def toggle_realtime_preview(self, state):
        if state == QtCore.Qt.Checked:
            self._frame_timer.setInterval(100) 
        else:
            self._frame_timer.setInterval(200)

    def update_3d_render(self, d, sc, _from_readback=False, _respect_autokey=False):
        if not rt.isValidNode(d['sp']) or not rt.isValidNode(d['base']):
            return
        rad = math.radians(d['a'])
        bp = rt.getProperty(d['base'], 'pos')
        tip = rt.point3(
            bp.x + d['t'] * sc * math.cos(rad),
            bp.y + d['t'] * sc * math.sin(rad),
            bp.z + d['h'] * sc,
        )
        arr = rt.point3(
            tip.x + 15 * sc * math.cos(rad),
            tip.y + 15 * sc * math.sin(rad),
            tip.z,
        )
        if _respect_autokey and rt.animButtonState:
            f = self._get_current_frame()
            mxs = (
                '(local sp = getNodeByName "{sp_name}";'
                ' if sp != undefined do ('
                '   with animate on at time {f}f ('
                '     sp.transform = (matrix3 1);'
                '     setKnotPoint sp 1 1 [{k1x},{k1y},{k1z}];'
                '     setKnotPoint sp 1 2 [{k2x},{k2y},{k2z}];'
                '     setKnotPoint sp 1 3 [{k3x},{k3y},{k3z}];'
                '     updateShape sp'
                '   )'
                ' ))'
            ).format(
                sp_name=d['sp'].name,
                f=f,
                k1x=bp.x, k1y=bp.y, k1z=bp.z,
                k2x=tip.x, k2y=tip.y, k2z=tip.z,
                k3x=arr.x, k3y=arr.y, k3z=arr.z,
            )
            rt.execute(mxs)
        else:
            rt.setProperty(d['sp'], 'transform', rt.matrix3(1))
            rt.setKnotPoint(d['sp'], 1, 1, bp)
            rt.setKnotPoint(d['sp'], 1, 2, tip)
            rt.setKnotPoint(d['sp'], 1, 3, arr)
            rt.updateShape(d['sp'])

        if not _from_readback and self.chk_phoenix.isChecked():
            dv = rt.point3(tip.x - bp.x, tip.y - bp.y, tip.z - bp.z)
            dist = math.sqrt(dv.x ** 2 + dv.y ** 2 + dv.z ** 2)
            if dist > 0.0001:
                nv = rt.normalize(dv)
                if _respect_autokey and rt.animButtonState:
                    with pymxs.animate(True):
                        rt.setProperty(d['base'], 'dir', nv)
                else:
                    rt.setProperty(d['base'], 'dir', nv)

    def reset_all(self):
        for d in self.voi_widgets.values():
            if rt.isValidNode(d['base']):
                try:
                    rt.setProperty(d['base'], 'scale', rt.point3(1, 1, 1))
                except Exception:
                    pass
                try:
                    rt.setProperty(d['base'], 'dir', rt.point3(0, 0, 1))
                except Exception:
                    pass
        rt.execute("delete $PHX_*")
        rt.execute("delete $DB9_Voi_Helper_*")
        self.voi_widgets = {}
        self.groups_log = {}
        self._last_sel_names = set()
        self.refresh_group_ui()
        self.scene.clear()
        rt.redrawViews()

    def closeEvent(self, event):
        try:
            self._frame_timer.stop()
        except Exception:
            pass
        try:
            self._sel_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)


# ==============================================================================
# LAUNCH
# ==============================================================================
global db9_fountain_ui
try:
    db9_fountain_ui.close()
except Exception:
    pass

_splash = SplashScreen()
_splash.show()
QtCore.QCoreApplication.processEvents()

db9_fountain_ui = DB9FountainV102(QtWidgets.QWidget.find(rt.windows.getMAXHWnd()))
db9_fountain_ui.show()
db9_fountain_ui.statusBar().showMessage("\u26f2 DB9 Fountain Pro v104 — Ready")
db9_fountain_ui._refresh_preset_tags()

QtCore.QTimer.singleShot(2000, _splash.close)
