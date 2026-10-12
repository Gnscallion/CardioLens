"""模型评估指标展示组件（数据来自 models/metrics.json）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QTableWidget,
                               QTableWidgetItem)

from src import config as C

from .. import theme
from .common import fmt_f, fmt_int

HEADERS = ["类别", "类型名称", "精确率 PPV", "召回率 Se", "F1", "测试样本数"]


class PerClassTable(QTableWidget):
    """逐类指标表。"""

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(HEADERS), parent)
        self.setHorizontalHeaderLabels(HEADERS)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, len(HEADERS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.setColumnWidth(0, 56)

    def load(self, metrics: dict | None) -> None:
        self.setRowCount(0)
        if not metrics:
            return
        per_class = (metrics.get("test") or {}).get("per_class") or {}
        names = metrics.get("class_names") or {}
        for code in C.AAMI_CLASSES:
            m = per_class.get(code)
            if not m:
                continue
            r = self.rowCount()
            self.insertRow(r)
            cells = [
                (code, None),
                (names.get(code, C.CLASS_NAMES_ZH.get(code, "")), None),
                (fmt_f(m.get("precision")), Qt.AlignRight | Qt.AlignVCenter),
                (fmt_f(m.get("recall")), Qt.AlignRight | Qt.AlignVCenter),
                (fmt_f(m.get("f1")), Qt.AlignRight | Qt.AlignVCenter),
                (fmt_int(m.get("support")), Qt.AlignRight | Qt.AlignVCenter),
            ]
            for c, (text, align) in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if align:
                    item.setTextAlignment(align)
                if c == 0:
                    item.setForeground(QColor("#ffffff"))
                    item.setBackground(QColor(theme.CLASS_COLOR.get(code, theme.SLATE)))
                    item.setTextAlignment(Qt.AlignCenter)
                if c == 4:
                    item.setForeground(QColor("#16202e"))
                self.setItem(r, c, item)
        self.resizeRowsToContents()
