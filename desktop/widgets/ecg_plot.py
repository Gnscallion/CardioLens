"""心电波形绘制控件（纯 QPainter 自绘，不依赖任何浏览器或绘图库）。

绘制内容与交互沿用原 Web 版 canvas 的设计：
  * 深色监护仪底色 + 时间/幅度网格与刻度
  * 心电信号折线
  * 逐搏标记，按 AAMI 五类着色
  * 异常搏动的淡色区间提示，选中搏动的高亮
  * 选中搏动的 Grad-CAM 热力叠加
  * 滚轮缩放、拖拽平移、悬停十字线读数、点击选中搏动
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen, QPolygonF)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme

PAD_L, PAD_R, PAD_T, PAD_B = 56, 16, 30, 30


def _color(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


class ECGPlotWidget(QWidget):
    """一块可缩放/平移的心电波形画布。"""

    beatClicked = Signal(int)          # 参数为搏动在 beats 列表中的下标

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._signal: list[float] = []
        self._fs: int = 360
        self._start_sec: float = 0.0
        self._beats: list[dict] = []
        self._selected: int = -1
        self._cam: list[float] | None = None
        self._cam_span: tuple[int, int] = (90, 162)
        self._title: str = ""
        self._hint: str = ""

        self._view: tuple[float, float] = (0.0, 0.0)   # 视图范围（采样点下标，浮点）
        self._drag_from: QPointF | None = None
        self._drag_view: tuple[float, float] | None = None
        self._hover_x: float | None = None

    # ------------------------------------------------------------ 数据接口
    def clear(self, message: str = "暂无波形数据") -> None:
        self._signal = []
        self._beats = []
        self._selected = -1
        self._cam = None
        self._hint = message
        self._view = (0.0, 0.0)
        self.update()

    def set_data(self, signal, fs: int, beats=None, start_sec: float = 0.0) -> None:
        """装入一段波形。

        signal : 幅度序列（对应分析窗口内的采样点）
        beats  : [{"sample": 窗口内下标, "label": AAMI 代码, "name": 中文名}, ...]
        """
        self._signal = [float(v) for v in signal]
        self._fs = int(fs) or 360
        self._start_sec = float(start_sec)
        self._beats = list(beats or [])
        self._selected = -1
        self._cam = None
        self._hint = ""
        self.reset_view()

    def set_selected(self, index: int) -> None:
        self._selected = int(index)
        self.update()

    def set_cam(self, cam: list[float] | None, span: tuple[int, int] | None = None) -> None:
        """设置选中搏动的 Grad-CAM 曲线（长度与窗口采样点一致）。"""
        self._cam = [float(v) for v in cam] if cam else None
        if span:
            self._cam_span = span
        self.update()

    def set_title(self, text: str) -> None:
        self._title = text
        self.update()

    def set_hint(self, text: str) -> None:
        self._hint = text
        self.update()

    def reset_view(self) -> None:
        n = len(self._signal)
        self._view = (0.0, float(n)) if n else (0.0, 0.0)
        self.update()

    def zoom_to_beat(self, index: int) -> None:
        """把视图聚焦到某个搏动附近，便于观察形态。"""
        if not (0 <= index < len(self._beats)):
            return
        center = float(self._beats[index]["sample"])
        half = max(float(self._cam_span[0] + self._cam_span[1]) * 3.0, 400.0)
        self._set_view(center - half, center + half)

    # ------------------------------------------------------------ 内部工具
    def _plot_rect(self) -> QRectF:
        return QRectF(PAD_L, PAD_T,
                      max(self.width() - PAD_L - PAD_R, 10),
                      max(self.height() - PAD_T - PAD_B, 10))

    def _set_view(self, a: float, b: float) -> None:
        n = len(self._signal)
        if n <= 0:
            return
        span = b - a
        min_span = max(60.0, n / 200.0)
        max_span = float(n)
        span = min(max(span, min_span), max_span)
        a = max(0.0, min(a, n - span))
        self._view = (a, a + span)
        self.update()

    def _x_of(self, idx: float) -> float:
        r = self._plot_rect()
        a, b = self._view
        if b <= a:
            return r.left()
        return r.left() + (idx - a) / (b - a) * r.width()

    def _idx_of(self, x: float) -> float:
        r = self._plot_rect()
        a, b = self._view
        if r.width() <= 0:
            return a
        return a + (x - r.left()) / r.width() * (b - a)

    def _view_bounds(self) -> tuple[float, float]:
        """可见区间的幅度上下界（带 8% 余量）。"""
        n = len(self._signal)
        if n == 0:
            return -1.0, 1.0
        a, b = self._view
        i0 = max(0, int(a))
        i1 = min(n, int(b) + 1)
        chunk = self._signal[i0:i1] or self._signal
        lo, hi = min(chunk), max(chunk)
        if hi - lo < 1e-9:
            hi, lo = lo + 1.0, lo - 1.0
        pad = (hi - lo) * 0.08
        return lo - pad, hi + pad

    @staticmethod
    def _nice_step(span: float, target: int) -> float:
        """取一个"好看"的刻度间隔（1/2/5×10^n）。"""
        import math
        if span <= 0 or target <= 0:
            return 1.0
        raw = span / target
        mag = 10 ** math.floor(math.log10(raw))
        norm = raw / mag
        step = 1 if norm <= 1 else 2 if norm <= 2 else 5 if norm <= 5 else 10
        return step * mag

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, _event) -> None:      # noqa: N802 - Qt 命名
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        full = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(Qt.NoPen)
        p.setBrush(_color(theme.PLOT_BG))
        p.drawRoundedRect(full, 10, 10)

        if not self._signal:
            p.setPen(_color(theme.PLOT_TEXT))
            p.drawText(full, Qt.AlignCenter, self._hint or "暂无波形数据")
            p.end()
            return

        rect = self._plot_rect()
        lo, hi = self._view_bounds()

        self._draw_grid(p, rect, lo, hi)
        self._draw_beat_bands(p, rect, lo, hi)
        self._draw_cam(p, rect, lo, hi)
        self._draw_signal(p, rect, lo, hi)
        self._draw_beat_marks(p, rect, lo, hi)
        self._draw_crosshair(p, rect, lo, hi)
        self._draw_title(p)
        p.end()

    def _draw_grid(self, p: QPainter, rect: QRectF, lo: float, hi: float) -> None:
        a, b = self._view
        total_sec = (b - a) / self._fs
        sec_step = self._nice_step(total_sec, 10)

        minor = QPen(_color("#5a82be", 40))
        minor.setWidthF(1.0)
        major = QPen(_color("#6e9bd7", 76))
        major.setWidthF(1.0)

        t = 0.0
        first = (a / self._fs) // sec_step * sec_step
        t = first
        while t <= b / self._fs + sec_step:
            x = self._x_of(t * self._fs)
            if rect.left() - 1 <= x <= rect.right() + 1:
                idx = round(t / sec_step)
                p.setPen(major if idx % 5 == 0 else minor)
                p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            t += sec_step

        mv_step = self._nice_step(hi - lo, 5)
        v = (lo // mv_step) * mv_step
        while v <= hi + mv_step:
            if lo <= v <= hi:
                y = rect.top() + (1 - (v - lo) / (hi - lo)) * rect.height()
                p.setPen(major if abs(v) < 1e-9 else minor)
                p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            v += mv_step

        p.setPen(_color("#96b4dc", 115))
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)

        t = first
        while t <= b / self._fs + sec_step:
            x = self._x_of(t * self._fs)
            if rect.left() <= x <= rect.right():
                p.drawText(QRectF(x - 26, rect.bottom() + 3, 52, 16),
                           Qt.AlignCenter, f"{t:.1f}s")
            t += sec_step

        v = (lo // mv_step) * mv_step
        while v <= hi + mv_step:
            if lo <= v <= hi:
                y = rect.top() + (1 - (v - lo) / (hi - lo)) * rect.height()
                label = "0" if abs(v) < 1e-9 else f"{v:.2f}"
                p.drawText(QRectF(0, y - 8, PAD_L - 8, 16),
                           Qt.AlignRight | Qt.AlignVCenter, label)
            v += mv_step

        p.setPen(QPen(_color("#96b4dc", 115), 1))
        p.drawRect(rect)

    def _draw_beat_bands(self, p: QPainter, rect: QRectF, lo: float, hi: float) -> None:
        """异常搏动区间淡色提示 + 选中搏动高亮。"""
        pre, post = self._cam_span
        for i, b in enumerate(self._beats):
            code = b.get("label", "N")
            if i == self._selected:
                x0 = self._x_of(b["sample"] - pre)
                x1 = self._x_of(b["sample"] + post)
                p.setPen(Qt.NoPen)
                p.setBrush(_color("#60a5fa", 40))
                p.drawRect(QRectF(max(x0, rect.left()), rect.top(),
                                  min(x1, rect.right()) - max(x0, rect.left()),
                                  rect.height()))
            elif code != "N":
                x = self._x_of(b["sample"])
                if rect.left() <= x <= rect.right():
                    p.setPen(Qt.NoPen)
                    p.setBrush(_color(theme.CLASS_COLOR.get(code, theme.SLATE), 26))
                    p.drawRect(QRectF(x - 7, rect.top(), 14, rect.height()))

    def _draw_cam(self, p: QPainter, rect: QRectF, lo: float, hi: float) -> None:
        """选中搏动的 Grad-CAM 热力叠加。"""
        if not self._cam or not (0 <= self._selected < len(self._beats)):
            return
        beat = self._beats[self._selected]
        pre, post = self._cam_span
        start = int(beat["sample"]) - pre
        end = start + len(self._cam)

        path = QPainterPath()
        path.moveTo(self._x_of(start), rect.bottom())
        for k in range(0, len(self._cam), 2):
            idx = start + k
            if idx < 0 or idx >= len(self._signal):
                continue
            x = self._x_of(idx)
            # 热力曲线以可见幅度范围的 42% 作为最大高度，避免压住波形
            h = rect.height() * 0.42 * max(0.0, min(1.0, self._cam[k]))
            path.lineTo(x, rect.bottom() - h)
        path.lineTo(self._x_of(end), rect.bottom())
        path.closeSubpath()

        p.setPen(Qt.NoPen)
        p.setBrush(_color(theme.PLOT_CAM, 62))
        p.drawPath(path)
        p.setPen(QPen(_color(theme.PLOT_CAM, 150), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _draw_signal(self, p: QPainter, rect: QRectF, lo: float, hi: float) -> None:
        a, b = self._view
        i0 = max(0, int(a))
        i1 = min(len(self._signal), int(b) + 2)
        if i1 - i0 < 2:
            return

        # 每像素跨度超过 2 个采样点时做极值抽稀，兼顾性能与毛刺保真
        step = max(1, (i1 - i0) // max(int(rect.width()) * 2, 1))
        h = hi - lo or 1.0
        path = QPainterPath()
        started = False
        for i in range(i0, i1, step):
            x = self._x_of(i)
            y = rect.top() + (1 - (self._signal[i] - lo) / h) * rect.height()
            if not started:
                path.moveTo(x, y)
                started = True
            else:
                path.lineTo(x, y)

        p.setPen(QPen(_color(theme.PLOT_SIGNAL, 45), 3.4))     # 辉光
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(QPen(_color(theme.PLOT_SIGNAL), 1.4))
        p.drawPath(path)

    def _draw_beat_marks(self, p: QPainter, rect: QRectF, lo: float, hi: float) -> None:
        h = hi - lo or 1.0
        for i, b in enumerate(self._beats):
            idx = int(b["sample"])
            if idx < 0 or idx >= len(self._signal):
                continue
            x = self._x_of(idx)
            if not (rect.left() - 20 <= x <= rect.right() + 20):
                continue
            code = b.get("label", "N")
            col = _color(theme.CLASS_COLOR.get(code, theme.SLATE))
            is_sel = i == self._selected

            p.setPen(QPen(_color(theme.CLASS_COLOR.get(code, theme.SLATE), 150 if is_sel else 90),
                          1.4 if is_sel else 1.0,
                          Qt.DashLine if is_sel else Qt.SolidLine))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

            y = rect.top() + (1 - (self._signal[idx] - lo) / h) * rect.height()
            r = 7.0 if is_sel else 5.0
            tri = QPolygonF([QPointF(x, y - r - 3), QPointF(x - r, y - r - 3 - r),
                             QPointF(x + r, y - r - 3 - r)])
            p.setPen(QPen(col, 1.2))
            p.setBrush(QBrush(col))
            p.drawPolygon(tri)

            if is_sel:
                p.setPen(QPen(col, 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(x, y), r + 3.5, r + 3.5)

    def _draw_crosshair(self, p: QPainter, rect: QRectF, lo: float, hi: float) -> None:
        if self._hover_x is None or not rect.contains(QPointF(self._hover_x, rect.center().y())):
            return
        idx = int(round(self._idx_of(self._hover_x)))
        if not (0 <= idx < len(self._signal)):
            return
        h = hi - lo or 1.0
        x = self._x_of(idx)
        y = rect.top() + (1 - (self._signal[idx] - lo) / h) * rect.height()

        p.setPen(QPen(_color("#cbd5e1", 110), 1, Qt.DashLine))
        p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        sec = self._start_sec + idx / self._fs
        text = f"{sec:.3f}s  {self._signal[idx]:.3f} mV"
        f = QFont(self.font())
        f.setPointSizeF(8.0)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(text) + 14
        bx = min(max(x + 10, rect.left()), rect.right() - w)
        by = rect.top() + 6
        p.setPen(Qt.NoPen)
        p.setBrush(_color("#1f2937", 235))
        p.drawRoundedRect(QRectF(bx, by, w, 20), 5, 5)
        p.setPen(_color("#f1f5f9"))
        p.drawText(QRectF(bx, by, w, 20), Qt.AlignCenter, text)

    def _draw_title(self, p: QPainter) -> None:
        if not self._title:
            return
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(_color("#b9cde8"))
        p.drawText(QRectF(PAD_L, 6, self.width() - PAD_L - PAD_R, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, self._title)

    # ------------------------------------------------------------ 交互
    def wheelEvent(self, event) -> None:       # noqa: N802
        if not self._signal:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        anchor = self._idx_of(event.position().x())
        a, b = self._view
        factor = 0.82 if delta > 0 else 1.0 / 0.82
        self._set_view(anchor - (anchor - a) * factor, anchor + (b - anchor) * factor)
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._signal:
            return
        if event.button() == Qt.LeftButton:
            hit = self._hit_beat(event.position().x())
            if hit >= 0:
                self._selected = hit
                self.update()
                self.beatClicked.emit(hit)
                return
            if event.position().x() >= self._plot_rect().left():
                self._drag_from = event.position()
                self._drag_view = self._view
                self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.MiddleButton:
            self.reset_view()

    def mouseMoveEvent(self, event) -> None:   # noqa: N802
        if not self._signal:
            return
        if self._drag_from is not None and self._drag_view is not None:
            rect = self._plot_rect()
            a, b = self._drag_view
            span = b - a
            dx = event.position().x() - self._drag_from.x()
            shift = -dx / max(rect.width(), 1.0) * span
            self._set_view(a + shift, b + shift)
        else:
            self._hover_x = event.position().x()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None:
            self._drag_from = None
            self._drag_view = None
            self.unsetCursor()
        self.update()

    def leaveEvent(self, event) -> None:       # noqa: N802
        self._hover_x = None
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.reset_view()

    def _hit_beat(self, x: float) -> int:
        """返回离点击处最近且在容差内的搏动下标，否则 -1。"""
        best, best_d = -1, 14.0
        for i, b in enumerate(self._beats):
            xb = self._x_of(b["sample"])
            d = abs(xb - x)
            if d < best_d:
                best, best_d = i, d
        return best
