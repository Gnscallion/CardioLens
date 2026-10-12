"""分析历史页：本地数据库中的报告列表，支持查看、删除与清空。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem)

from .. import theme
from ..services import history_service as HS
from ..widgets.common import Card, StatCard, fmt_int, fmt_pct, stat_row
from .base import BasePage

HEADERS = ["编号", "记录", "时间窗", "心搏数", "异常占比", "提示等级", "一致率", "分析时间"]


class HistoryPage(BasePage):
    openRequested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__("分析历史",
                         "所有报告保存在本机数据库中，卸载软件前均可随时回看",
                         parent=parent)

        self.stats_holder, self.stats_grid = stat_row(columns=4)
        for i, key in enumerate(["累计分析次数", "累计分析心搏",
                                 "平均异常搏动占比", "平均与专家标注一致率"]):
            self.stats_grid.addWidget(StatCard(key), 0, i)
        self.content.addWidget(self.stats_holder)

        self.card = Card("报告列表", "双击任意一行查看完整报告")
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        for c, w in [(0, 62), (1, 82), (3, 82), (4, 96), (6, 88)]:
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            self.table.setColumnWidth(c, w)
        self.table.doubleClicked.connect(lambda _i: self._open())
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.card.add(self.table)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.open_btn = QPushButton("查看详情")
        self.open_btn.setObjectName("Primary")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self._open)
        actions.addWidget(self.open_btn)

        self.delete_btn = QPushButton("删除所选")
        self.delete_btn.setObjectName("Danger")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._delete_selected)
        actions.addWidget(self.delete_btn)

        self.clear_btn = QPushButton("清空全部")
        self.clear_btn.setObjectName("Danger")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_all)
        actions.addWidget(self.clear_btn)

        refresh = QPushButton("刷新")
        refresh.setObjectName("Ghost")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)

        actions.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        actions.addWidget(self.status_label)
        self.card.add_layout(actions)

        self.content.addWidget(self.card)
        self.refresh()

    # ------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        error = ""
        try:
            rows = HS.list_analyses()
        except HS.HistoryError as exc:
            error = f"✗ {str(exc).splitlines()[0]}"
            rows = []
        self._fill_table(rows)

        st = HS.stats()
        for i, (value, unit) in enumerate([
            (fmt_int(st["total_analyses"]), "次"),
            (fmt_int(st["total_beats"]), "搏"),
            (fmt_pct(st["avg_abnormal_ratio"]), ""),
            (fmt_pct(st["avg_agreement"]), ""),
        ]):
            card = self.stats_grid.itemAtPosition(0, i).widget()
            card.set_value(value, unit)

        # 提示语必须跟着行数一起刷新：只在"没有记录"时设置文字的话，
        # 删空再重新保存一次，提示语就会跟表格内容对不上。
        if error:
            self.status_label.setStyleSheet(f"color:{theme.DANGER};")
            self.status_label.setText(error)
        elif rows:
            self.status_label.setStyleSheet("")
            self.status_label.setText(
                f"共 {len(rows)} 条报告，双击任意一行即可查看完整报告。")
        else:
            self.status_label.setStyleSheet("")
            self.status_label.setText(
                "暂无历史报告。在「ECG 分析」中完成分析后可保存到此处。")
        self._sync_buttons()

    def _fill_table(self, rows: list[dict]) -> None:
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            window = f"{r.get('start_sec', 0):.1f}s 起 {r.get('duration_sec', 0):.0f}s"
            cells = [
                (str(r.get("id", "")), Qt.AlignCenter, None),
                (str(r.get("record_id", "")), Qt.AlignCenter, None),
                (window, Qt.AlignCenter, None),
                (fmt_int(r.get("n_beats")), Qt.AlignCenter, None),
                (fmt_pct(r.get("abnormal_ratio")), Qt.AlignCenter, None),
                (str(r.get("risk_label", "") or "—"), Qt.AlignCenter, None),
                (fmt_pct(r.get("agreement")), Qt.AlignCenter, None),
                (str(r.get("created_at", "")), Qt.AlignCenter, theme.TEXT_SOFT),
            ]
            for c, (text, align, color) in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                if color:
                    item.setForeground(QColor(color))
                self.table.setItem(i, c, item)
        self.table.resizeRowsToContents()

    # ------------------------------------------------------------ 操作
    def _selected_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return int(item.text()) if item else None

    def _sync_buttons(self) -> None:
        has = self._selected_id() is not None
        self.open_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.clear_btn.setEnabled(self.table.rowCount() > 0)

    def _open(self) -> None:
        rid = self._selected_id()
        if rid is not None:
            self.openRequested.emit(rid)

    def _delete_selected(self) -> None:
        rid = self._selected_id()
        if rid is None:
            return
        if not self._confirm("删除确认", "确定要删除这条分析报告吗？",
                             "删除后无法恢复。", "删除"):
            return
        try:
            HS.delete_analysis(rid)
        except HS.HistoryError as exc:
            self._fail(str(exc))
            return
        self._ok(f"✓ 已删除报告 {rid}")
        self.refresh()

    def _clear_all(self) -> None:
        n = self.table.rowCount()
        if n <= 0:
            return
        if not self._confirm("清空确认", f"确定要清空全部 {n} 条分析报告吗？",
                             "此操作不可撤销，所有已保存的报告都会被删除。", "清空全部"):
            return
        try:
            removed = HS.clear_all()
        except HS.HistoryError as exc:
            self._fail(str(exc))
            return
        self._ok(f"✓ 已清空 {removed} 条报告")
        self.refresh()

    # ------------------------------------------------------------ 小工具
    def _confirm(self, title: str, text: str, info: str, ok_text: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Warning)
        box.setText(text)
        box.setInformativeText(info)
        ok = box.addButton(ok_text, QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        return box.clickedButton() is ok

    def _ok(self, message: str) -> None:
        self.status_label.setStyleSheet(f"color:{theme.OK};")
        self.status_label.setText(message)

    def _fail(self, message: str) -> None:
        self.status_label.setStyleSheet(f"color:{theme.DANGER};")
        self.status_label.setText(f"✗ {message.splitlines()[0]}")
