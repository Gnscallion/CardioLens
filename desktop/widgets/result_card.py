"""分析结果相关组件：逐搏明细表、五类概率条、单搏详情。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QLabel, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from src import config as C

from .. import theme
from .common import Badge, fmt_f

BEAT_HEADERS = ["序号", "位置 (s)", "预测类别", "置信度", "专家标注", "一致"]


class BeatTable(QTableWidget):
    """逐搏结果表；点击某行会发出 beatSelected(下标)。"""

    beatSelected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(BEAT_HEADERS), parent)
        self.setHorizontalHeaderLabels(BEAT_HEADERS)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setShowGrid(False)
        hh = self.horizontalHeader()
        for c in range(len(BEAT_HEADERS)):
            hh.setSectionResizeMode(c, QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        self.setColumnWidth(0, 54)
        self._loading = False
        self.itemSelectionChanged.connect(self._on_selection)

    def load(self, beats: list[dict]) -> None:
        self._loading = True
        self.setRowCount(0)
        for b in beats:
            r = self.rowCount()
            self.insertRow(r)
            cells = [
                (str(b.get("index", r + 1)), Qt.AlignCenter),
                (fmt_f(b.get("time_sec"), 2), Qt.AlignCenter),
                (b.get("pred_name", ""), Qt.AlignCenter),
                (fmt_f(b.get("confidence"), 3), Qt.AlignCenter),
                (b.get("expert_name", ""), Qt.AlignCenter),
                ("✓" if b.get("agree") else "✗", Qt.AlignCenter),
            ]
            for c, (text, align) in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                if c == 2:
                    item.setForeground(QColor(
                        theme.CLASS_COLOR.get(b.get("pred", ""), theme.TEXT)))
                    f = QFont()
                    f.setBold(True)
                    item.setFont(f)
                if c == 5:
                    item.setForeground(QColor(theme.OK if b.get("agree") else theme.DANGER))
                self.setItem(r, c, item)
        self._loading = False
        self.resizeRowsToContents()

    def select_index(self, index: int) -> None:
        if 0 <= index < self.rowCount():
            self._loading = True
            self.selectRow(index)
            self.scrollToItem(self.item(index, 0))
            self._loading = False

    def _on_selection(self) -> None:
        if self._loading:
            return
        rows = self.selectionModel().selectedRows()
        if rows:
            self.beatSelected.emit(rows[0].row())


class ProbabilityBars(QWidget):
    """五类概率横向条。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(5 * 24 + 8)
        self._probs: dict[str, float] = {}
        self._pred: str = ""

    def set_probs(self, probs: dict, pred: str = "") -> None:
        self._probs = dict(probs or {})
        self._pred = pred
        self.update()

    def paintEvent(self, _event) -> None:      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        row_h, gap = 17, 7
        label_w, value_w = 96, 52
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)

        for i, code in enumerate(C.AAMI_CLASSES):
            y = i * (row_h + gap)
            val = float(self._probs.get(code, 0.0) or 0.0)
            col = QColor(theme.CLASS_COLOR.get(code, theme.SLATE))

            p.setPen(QColor(theme.TEXT_MID))
            p.drawText(QRectF(0, y, label_w, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{code} · {C.CLASS_NAMES_ZH.get(code, '')}")

            track = QRectF(label_w + 6, y + 4, max(self.width() - label_w - value_w - 14, 20),
                           row_h - 8)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#eef2f8"))
            p.drawRoundedRect(track, 4, 4)

            if val > 0:
                w = max(track.width() * min(val, 1.0), 3.0)
                p.setBrush(col)
                p.drawRoundedRect(QRectF(track.left(), track.top(), w, track.height()), 4, 4)

            p.setPen(col if code == self._pred else QColor(theme.TEXT_SOFT))
            bold = QFont(f)
            bold.setBold(code == self._pred)
            p.setFont(bold)
            p.drawText(QRectF(self.width() - value_w, y, value_w - 4, row_h),
                       Qt.AlignRight | Qt.AlignVCenter, f"{val * 100:.1f}%")
            p.setFont(f)
        p.end()


class BeatDetail(QWidget):
    """单搏详情：类别、置信度、专家标注，以及前后 RR 节律特征。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.badge = Badge("N")
        self.title = QLabel("—")
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        self.title.setFont(f)
        head.addWidget(self.badge)
        head.addWidget(self.title)
        head.addStretch(1)
        self.conf = QLabel("—")
        self.conf.setObjectName("Mono")
        head.addWidget(self.conf)
        lay.addLayout(head)

        self.bars = ProbabilityBars()
        lay.addWidget(self.bars)

        self.rhythm = QLabel("—")
        self.rhythm.setObjectName("Muted")
        self.rhythm.setWordWrap(True)
        # RR 说明在窄卡片里会折成多行；不预留高度的话，它会被上面的概率条挤掉，
        # Qt 在空间不足时会让两者重叠。
        self.rhythm.setMinimumHeight(52)
        lay.addWidget(self.rhythm)
        lay.addStretch(1)
        self.setMinimumHeight(240)

    def clear(self) -> None:
        self.badge.setText("—")
        self.title.setText("选择左侧某个心搏查看详情")
        self.conf.setText("")
        self.rhythm.setText("")
        self.bars.set_probs({})

    def show_beat(self, b: dict) -> None:
        code = b.get("pred", "")
        self.badge.setText(code)
        col = QColor(theme.CLASS_COLOR.get(code, theme.SLATE))
        soft = QColor(col)
        soft.setAlpha(30)
        self.badge.setStyleSheet(
            f"color:{col.name()}; background:rgba({soft.red()},{soft.green()},{soft.blue()},0.14);"
            f"border:1px solid rgba({soft.red()},{soft.green()},{soft.blue()},0.35);"
            "border-radius:6px; font-weight:700; font-size:11px;"
        )
        self.title.setText(
            f"第 {b.get('index', '—')} 搏 · {b.get('pred_name', '')}"
            f"   （{fmt_f(b.get('time_sec'), 2)} s）"
        )
        self.conf.setText(f"置信度 {fmt_f(b.get('confidence'), 3)}")
        self.bars.set_probs(b.get("probs", {}), code)

        agree = "与专家标注一致" if b.get("agree") else \
            f"与专家标注不一致（专家：{b.get('expert_name', '—')}）"
        self.rhythm.setText(
            f"前 RR {fmt_f(b.get('rr_prev_sec'), 3)} s"
            f"（相对基线 {fmt_f(b.get('rr_prev_ratio'), 2)}×）　"
            f"后 RR {fmt_f(b.get('rr_next_sec'), 3)} s"
            f"（{fmt_f(b.get('rr_next_ratio'), 2)}×）　"
            f"本记录 RR 基线 {fmt_f(b.get('rr_baseline_sec'), 3)} s\n{agree}"
        )
