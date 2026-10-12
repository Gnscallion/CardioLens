"""首页：品牌、系统状态、数据集概览、模型性能与快捷入口。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src import config as C

from .. import theme
from ..services import history_service as HS
from ..services import resource_service as RS
from ..widgets.common import (Card, ClassLegend, ClassStackBar, StatCard, Tag,
                              clear_layout, fmt_int, fmt_pct, stat_row)
from ..widgets.metric_card import PerClassTable
from .base import BasePage


class HomePage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__(C.APP_NAME, C.APP_NAME_EN, parent=parent)

        self._build_hero()
        self._build_status()
        self._build_dataset()
        self._build_model()
        self._build_history()
        self._build_disclaimer()
        self.content.addStretch(1)

    # ------------------------------------------------------------ 品牌区
    def _build_hero(self) -> None:
        card = Card()
        name = QLabel(C.APP_NAME)
        name.setStyleSheet(f"font-size:30px; font-weight:800; color:{theme.BRAND};")
        card.add(name)

        zh = QLabel(C.APP_NAME_ZH)
        zh.setStyleSheet(f"font-size:16px; font-weight:600; color:{theme.TEXT};")
        card.add(zh)

        en = QLabel(C.APP_NAME_EN)
        en.setObjectName("Muted")
        card.add(en)

        intro = QLabel(
            "基于深度学习与可解释 AI 的心电节律分析软件。选取任意一段心电记录，"
            "软件将逐搏定位并判别其所属的 AAMI 五类心律类型，同时通过 Grad-CAM "
            "可视化模型做出判断时所关注的波形区间，输出可保存、可回溯的结构化分析报告。"
            "<br>全程在本机离线运行：无需联网，无需安装任何运行环境，双击即可使用。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:13px;")
        card.add(intro)

        tags = QHBoxLayout()
        tags.setSpacing(8)
        for text in ["1D-CNN 深度学习", "AAMI 五分类", "Grad-CAM 可解释性",
                     "MIT-BIH 真实临床数据", "全本地离线运行"]:
            tags.addWidget(Tag(text))
        tags.addStretch(1)
        card.add_layout(tags)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        go_analyze = QPushButton("开始 ECG 分析 →")
        go_analyze.setObjectName("Primary")
        go_analyze.setCursor(Qt.PointingHandCursor)
        go_analyze.clicked.connect(lambda: self.navigateRequested.emit("analyze"))
        go_history = QPushButton("查看分析历史")
        go_history.setObjectName("Ghost")
        go_history.setCursor(Qt.PointingHandCursor)
        go_history.clicked.connect(lambda: self.navigateRequested.emit("history"))
        actions.addWidget(go_analyze)
        actions.addWidget(go_history)
        actions.addStretch(1)
        card.add_layout(actions)

        self.content.addWidget(card)

    # ------------------------------------------------------------ 状态与统计
    def _build_status(self) -> None:
        self.status_card = Card("系统状态")
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.status_tag = Tag("检查中…", theme.TEXT_SOFT)
        self.status_text = QLabel("正在检查安装文件…")
        self.status_text.setWordWrap(True)
        self.status_text.setStyleSheet(f"color:{theme.TEXT_MID};")
        lay.addWidget(self.status_tag)
        lay.addWidget(self.status_text, 1)
        self.status_card.add(row)

        self.data_dir_label = QLabel("")
        self.data_dir_label.setObjectName("Mono")
        self.data_dir_label.setWordWrap(True)
        self.status_card.add(self.data_dir_label)
        self.content.addWidget(self.status_card)

        self.stats_holder, self.stats_grid = stat_row()
        self.content.addWidget(self.stats_holder)

    # ------------------------------------------------------------ 数据集
    def _build_dataset(self) -> None:
        self.dataset_card = Card("数据集概览",
                                 "MIT-BIH Arrhythmia Database · 真实临床心电记录")
        meta = RS.load_meta()
        if not meta:
            self.dataset_card.add(QLabel("数据元信息缺失，无法显示数据集概览。"))
            self.content.addWidget(self.dataset_card)
            return

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        for key, value in [
            ("心电记录数", fmt_int(len(meta.get("records", [])))),
            ("心搏样本总数", fmt_int(meta.get("total_beats"))),
            ("训练集心搏", fmt_int(meta.get("n_train"))),
            ("测试集心搏", fmt_int(meta.get("n_test"))),
        ]:
            lay.addWidget(StatCard(key, value))
        self.dataset_card.add(row)

        title = QLabel("AAMI 五类样本构成")
        title.setObjectName("SectionTitle")
        self.dataset_card.add(title)

        self.stack = ClassStackBar()
        self.stack.set_counts(meta.get("class_totals", {}))
        self.dataset_card.add(self.stack)

        legend = ClassLegend()
        totals = meta.get("class_totals", {})
        legend.set_items([
            (code, C.CLASS_NAMES_ZH[code], fmt_int(totals.get(code, 0)))
            for code in C.AAMI_CLASSES
        ])
        self.dataset_card.add(legend)

        note = QLabel(
            "采用 <b>inter-patient</b> 划分（de Chazal DS1/DS2）：训练集与测试集的"
            "患者完全不重叠，指标更贴近跨患者的实际场景。"
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{theme.TEXT_MID}; background:{theme.BRAND_SOFT};"
            "border-radius:8px; padding:9px 12px; font-size:12px;"
        )
        self.dataset_card.add(note)
        self.content.addWidget(self.dataset_card)

    # ------------------------------------------------------------ 模型性能
    def _build_model(self) -> None:
        self.model_card = Card("模型分类性能",
                               "测试集（DS2 患者组）上的逐类表现 · PPV 与 Se 为 AAMI 标准常用指标")
        metrics = RS.load_metrics()
        if not metrics:
            self.model_card.add(QLabel("未找到模型指标文件。"))
            self.content.addWidget(self.model_card)
            return

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        test = metrics.get("test", {})
        lay.addWidget(StatCard("测试集准确率", fmt_pct(test.get("accuracy"), 2)))
        lay.addWidget(StatCard("四类 Macro-F1", f"{float(test.get('macro_f1', 0)):.4f}",
                               accent=theme.ACCENT))
        lay.addWidget(StatCard("五类 Macro-F1",
                               f"{float(test.get('macro_f1_5class', 0)):.4f}"))
        lay.addWidget(StatCard("模型参数量", fmt_int(metrics.get("n_params"))))
        lay.addWidget(StatCard("训练耗时",
                               f"{float(metrics.get('train_seconds', 0)) / 60:.1f}", "分钟"))
        self.model_card.add(row)

        table = PerClassTable()
        table.load(metrics)
        table.setMinimumHeight(190)
        self.model_card.add(table)

        note = QLabel(
            "表中为 <b>四类</b>（N/S/V/F）的逐类指标，与「四类 Macro-F1」对应；"
            "Q 类（未分类搏动）测试样本极少，单列其指标会被 0 值主导，"
            "因此只在「五类 Macro-F1」中作为五个类别之一参与平均。"
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        self.model_card.add(note)
        self.content.addWidget(self.model_card)

    # ------------------------------------------------------------ 历史统计
    def _build_history(self) -> None:
        self.history_card = Card("我的分析记录")
        self.history_row = QWidget()
        self.history_lay = QHBoxLayout(self.history_row)
        self.history_lay.setContentsMargins(0, 0, 0, 0)
        self.history_lay.setSpacing(10)
        self.history_card.add(self.history_row)
        self.content.addWidget(self.history_card)

    # ------------------------------------------------------------ 免责声明
    def _build_disclaimer(self) -> None:
        card = Card()
        title = QLabel("⚠ 免责声明")
        title.setStyleSheet(f"color:{theme.DANGER}; font-weight:700;")
        card.add(title)
        text = QLabel(C.DISCLAIMER)
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
        card.add(text)
        self.content.addWidget(card)

    # ------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        """进入首页时刷新状态与统计。"""
        ready = RS.check_readiness()
        if ready.ok:
            self.status_tag.setText("已就绪")
            self.status_tag.set_color(theme.OK)
            self.status_text.setText("模型与心电数据均已加载，可以开始分析。")
        else:
            self.status_tag.setText("安装不完整")
            self.status_tag.set_color(theme.DANGER)
            self.status_text.setText(
                "缺少以下文件，请重新获取完整的安装包：\n  · "
                + "\n  · ".join(ready.missing)
            )
        self.data_dir_label.setText(f"数据目录：{RS.user_data_dir()}")

        # 历史统计卡
        clear_layout(self.history_lay)
        st = HS.stats()
        if st["total_analyses"]:
            for key, value, unit in [
                ("累计分析次数", fmt_int(st["total_analyses"]), "次"),
                ("累计分析心搏", fmt_int(st["total_beats"]), "搏"),
                ("平均异常搏动占比", fmt_pct(st["avg_abnormal_ratio"]), ""),
                ("平均与专家标注一致率", fmt_pct(st["avg_agreement"]), ""),
            ]:
                self.history_lay.addWidget(StatCard(key, value, unit))
        else:
            hint = QLabel("还没有保存过分析报告。完成一次分析后点击「保存报告」即可在此查看。")
            hint.setObjectName("Muted")
            self.history_lay.addWidget(hint)
            self.history_lay.addStretch(1)
