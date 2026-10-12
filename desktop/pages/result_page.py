"""分析报告页：波形 + Grad-CAM、逐搏明细、单搏详情与报告保存。

同一个类同时服务两个入口：
  * readonly=False —— 刚完成一次分析，可保存报告；
  * readonly=True  —— 从历史记录打开既有报告，只读并可删除。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QSplitter, QWidget)

from src import config as C

from .. import theme
from ..services import history_service as HS
from ..widgets.common import (Card, ClassLegend, ClassStackBar, StatCard, Tag,
                              fmt_int, fmt_pct, stat_row)
from ..widgets.ecg_plot import ECGPlotWidget
from ..widgets.result_card import BeatDetail, BeatTable
from .base import BasePage

CAM_SPAN = (C.PRE_SAMPLES, C.POST_SAMPLES)


class ResultPage(BasePage):
    deleteRequested = Signal(int)      # 只读模式下请求删除该条历史记录

    def __init__(self, readonly: bool = False, parent=None) -> None:
        super().__init__(
            "分析报告" if not readonly else "历史报告详情",
            "逐搏判别结果、模型可解释性热力图与节律特征" if not readonly
            else "以下为已保存报告的只读回放",
            scroll=True, parent=parent)
        self.readonly = readonly
        self._payload: dict | None = None
        self._analysis_id: int | None = None

        self.stats_holder, self.stats_grid = stat_row(columns=4)
        # 统计卡片只建一次，之后按需刷新数值。若每次装载报告都往网格里重新
        # addWidget，旧卡片会脱离布局但仍留在界面上，反复分析后会互相叠住。
        self._stat_cards = []
        for i, key in enumerate(["分析心搏数", "平均置信度",
                                 "异常搏动数", "异常搏动占比"]):
            card = StatCard(key)
            self.stats_grid.addWidget(card, 0, i)
            self._stat_cards.append(card)
        self.content.addWidget(self.stats_holder)

        # 波形区与明细区各自的"最小可用高度"是硬要求：五类概率条、RR 节律说明
        # 这些控件都有固定高度，一旦被压到最小值以下，Qt 会让它们互相重叠。
        # 因此这里给分割器一个不小于两者之和的最小高度，窗口不够高时整页滚动，
        # 而不是把内容压扁。
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_waveform())
        splitter.addWidget(self._build_detail_area())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([360, 280])
        splitter.setMinimumHeight(660)
        self.content.addWidget(splitter, 1)

        self.content.addWidget(self._build_actions())
        self.content.addWidget(self._build_disclaimer())

    # ------------------------------------------------------------ 上：波形
    def _build_waveform(self) -> QWidget:
        card = Card("心电波形与 Grad-CAM")
        card.setMinimumHeight(340)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.risk_tag = Tag("—", theme.TEXT_SOFT)
        self.agree_tag = Tag("—", theme.BRAND)
        head.addWidget(self.risk_tag)
        head.addWidget(self.agree_tag)
        head.addStretch(1)
        self.cam_hint = QLabel("点击波形上的心搏标记，查看该搏的 Grad-CAM 归因区间")
        self.cam_hint.setObjectName("Muted")
        head.addWidget(self.cam_hint)
        card.add_layout(head)

        self.plot = ECGPlotWidget()
        self.plot.setMinimumHeight(180)
        self.plot.beatClicked.connect(self._select_beat)
        card.add(self.plot)

        self.stack = ClassStackBar()
        card.add(self.stack)
        self.legend = ClassLegend()
        card.add(self.legend)
        return card

    # ------------------------------------------------------------ 下：明细
    def _build_detail_area(self) -> QWidget:
        holder = QWidget()
        holder.setMinimumHeight(300)
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        detail_card = Card("单搏详情", "选中心搏的类别概率与 RR 节律特征")
        detail_card.setMinimumHeight(300)
        detail_card.setMinimumWidth(320)
        detail_card.setMaximumWidth(430)
        self.detail = BeatDetail()
        detail_card.add(self.detail)
        lay.addWidget(detail_card)

        table_card = Card("逐搏分析结果", "点击任意一行可联动上方波形与该搏详情")
        self.table = BeatTable()
        self.table.beatSelected.connect(self._select_beat)
        table_card.add(self.table)
        lay.addWidget(table_card, 1)
        return holder

    # ------------------------------------------------------------ 操作区
    def _build_actions(self) -> QWidget:
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        if self.readonly:
            self.back_btn = QPushButton("← 返回历史记录")
            self.back_btn.setObjectName("Ghost")
            self.back_btn.setCursor(Qt.PointingHandCursor)
            self.back_btn.clicked.connect(
                lambda: self.navigateRequested.emit("history"))
            lay.addWidget(self.back_btn)

            self.delete_btn = QPushButton("删除此报告")
            self.delete_btn.setObjectName("Danger")
            self.delete_btn.setCursor(Qt.PointingHandCursor)
            self.delete_btn.clicked.connect(self._confirm_delete)
            lay.addWidget(self.delete_btn)
        else:
            self.save_btn = QPushButton("保存报告到历史记录")
            self.save_btn.setObjectName("Primary")
            self.save_btn.setCursor(Qt.PointingHandCursor)
            self.save_btn.clicked.connect(self._save)
            lay.addWidget(self.save_btn)

            back = QPushButton("← 返回分析工作台")
            back.setObjectName("Ghost")
            back.setCursor(Qt.PointingHandCursor)
            back.clicked.connect(lambda: self.navigateRequested.emit("analyze"))
            lay.addWidget(back)

        lay.addStretch(1)
        self.action_status = QLabel("")
        self.action_status.setObjectName("Muted")
        lay.addWidget(self.action_status)
        return holder

    def _build_disclaimer(self) -> QWidget:
        card = Card()
        text = QLabel("⚠ " + C.DISCLAIMER)
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
        card.add(text)
        return card

    # ------------------------------------------------------------ 数据装载
    def set_payload(self, payload: dict, analysis_id: int | None = None,
                    saved_at: str = "") -> None:
        self._payload = payload
        self._analysis_id = analysis_id
        s = payload.get("summary", {}) or {}

        for card, value in zip(self._stat_cards, [
            fmt_int(s.get("n_beats")),
            fmt_pct(s.get("mean_confidence"), 1),
            fmt_int(s.get("abnormal_count")),
            fmt_pct(s.get("abnormal_ratio"), 1),
        ]):
            card.set_value(value)

        if self.readonly:
            title = f"记录 {payload.get('record_id')} · {payload.get('start_sec')} s 起 " \
                    f"{payload.get('duration_sec')} s"
            if saved_at:
                title += f" · 保存于 {saved_at}"
            self.sub_label.setText(title)
            self.sub_label.setVisible(True)

        risk = s.get("risk_level", {}) or {}
        self.risk_tag.setText(f"提示等级：{risk.get('label', '—')}")
        self.risk_tag.set_color(risk.get("color", theme.TEXT_SOFT))
        self.agree_tag.setText(f"与专家标注一致率 {fmt_pct(s.get('agreement'), 1)}")

        counts = s.get("counts", {}) or {}
        self.stack.set_counts(counts)
        self.legend.set_items([
            (code, C.CLASS_NAMES_ZH[code], fmt_int(counts.get(code, 0)))
            for code in C.AAMI_CLASSES
        ])

        beats = payload.get("beats", []) or []
        marks = [{"sample": int(b["sample"]), "label": b.get("pred", "N"),
                  "name": b.get("pred_name", "")} for b in beats]
        self.plot.set_data(payload.get("signal", []), payload.get("fs", C.FS),
                           marks, start_sec=float(payload.get("start_sec", 0)))
        self._set_plot_title(payload)

        self.table.load(beats)
        self.detail.clear()
        if beats:
            self._select_beat(0)
        if self.readonly:
            self.action_status.setText("")
        else:
            self.action_status.setText("")
            self.save_btn.setEnabled(True)
            self.save_btn.setToolTip("")

    def _set_plot_title(self, payload: dict) -> None:
        if payload.get("in_training_set"):
            split_note = "　·　该记录属于训练集（DS1），一致率不代表泛化能力"
        else:
            split_note = "　·　该记录属于测试集（DS2）" if payload.get("split") else ""
        self.plot.set_title(
            f"记录 {payload.get('record_id')} · 起始 {payload.get('start_sec')} s · "
            f"{payload.get('duration_sec')} s{split_note}"
        )

    # ------------------------------------------------------------ 选中联动
    def _select_beat(self, index: int) -> None:
        beats = (self._payload or {}).get("beats", []) or []
        if not (0 <= index < len(beats)):
            return
        beat = beats[index]

        # 选中表格行时 Qt 会请求"把该项滚动到可见"，这个请求会一路上传到
        # 整页的滚动区，表现为点一下心搏、页面就往下跳一格，统计卡片被顶出
        # 视野。这里先记下滚动位置，联动做完再原样还原。
        bar = self._scroll.verticalScrollBar() if self._scroll is not None else None
        pos = bar.value() if bar is not None else 0

        self.plot.set_selected(index)
        cam = beat.get("cam")
        if cam:
            self.plot.set_cam(cam, CAM_SPAN)
            self.cam_hint.setText(
                f"Grad-CAM：第 {beat.get('index')} 搏（{beat.get('pred_name', '')}）"
                f"的模型关注区间，长度 {len(cam)} 采样点"
            )
        else:
            self.plot.set_cam(None)
            self.cam_hint.setText("本次分析未生成 Grad-CAM（分析时未勾选该选项）")
        self.detail.show_beat(beat)
        self.table.select_index(index)

        if bar is not None:
            bar.setValue(pos)

    # ------------------------------------------------------------ 保存 / 删除
    def _save(self) -> None:
        if not self._payload:
            return
        try:
            rid = HS.save_analysis(self._payload)
        except HS.HistoryError as exc:
            self.action_status.setText(f"✗ {str(exc).splitlines()[0]}")
            self.action_status.setStyleSheet(f"color:{theme.DANGER};")
            return
        self._analysis_id = int(rid)
        self.save_btn.setEnabled(False)
        self.save_btn.setText("已保存")
        self.action_status.setStyleSheet(f"color:{theme.OK};")
        self.action_status.setText(f"✓ 已保存到历史记录（编号 {rid}）")

    def _confirm_delete(self) -> None:
        if self._analysis_id is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除确认")
        box.setIcon(QMessageBox.Warning)
        box.setText("确定要删除这条分析报告吗？")
        box.setInformativeText("删除后无法恢复。")
        yes = box.addButton("删除", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        if box.clickedButton() is yes:
            self.deleteRequested.emit(int(self._analysis_id))

    # ------------------------------------------------------------ 外部接口
    def show_save_error(self, message: str) -> None:
        self.action_status.setStyleSheet(f"color:{theme.DANGER};")
        self.action_status.setText(f"✗ {message}")

    def show_delete_result(self, ok: bool, message: str = "") -> None:
        if ok:
            self.action_status.setStyleSheet(f"color:{theme.OK};")
            self.action_status.setText("✓ 已删除该报告")
            self.navigateRequested.emit("history")
        else:
            self.show_save_error(message or "删除失败")
