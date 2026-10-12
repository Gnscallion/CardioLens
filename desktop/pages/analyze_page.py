"""ECG 分析工作台：参数选择 → 波形预览 → 后台分析 → 摘要反馈。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QSlider, QSplitter,
                               QVBoxLayout, QWidget)

from src import config as C
from src.inference import MAX_WINDOW_SEC, MIN_WINDOW_SEC

from .. import theme
from ..services import analysis_service as AS
from ..services import resource_service as RS
from ..widgets.common import (Card, ClassLegend, ClassStackBar, Tag, clear_layout,
                              fmt_int, fmt_pct, kv_row)
from ..widgets.ecg_plot import ECGPlotWidget
from .base import BasePage


class AnalyzePage(BasePage):
    analysisCompleted = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__("ECG 分析工作台",
                         "选择记录与时间窗 → 预览波形 → 逐搏分析 → 查看报告",
                         scroll=False, parent=parent)

        self._records: list[dict] = []
        self._current: dict | None = None
        self._preview_worker: AS.PreviewWorker | None = None
        self._analysis_worker: AS.AnalysisWorker | None = None

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_waveform())
        splitter.addWidget(self._build_summary())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 640, 310])
        self.content.addWidget(splitter, 1)

        self.reload_records()

    # ------------------------------------------------------------ 左：参数
    def _build_controls(self) -> QWidget:
        card = Card("分析参数")
        card.setMinimumWidth(280)
        card.setMaximumWidth(360)

        label = QLabel("心电记录")
        label.setObjectName("SectionTitle")
        card.add(label)
        self.record_combo = QComboBox()
        self.record_combo.currentIndexChanged.connect(self._on_record_changed)
        card.add(self.record_combo)

        self.record_note = QLabel("")
        self.record_note.setObjectName("Muted")
        self.record_note.setWordWrap(True)
        card.add(self.record_note)

        self.info_holder = QWidget()
        self.info_lay = QVBoxLayout(self.info_holder)
        self.info_lay.setContentsMargins(0, 0, 0, 0)
        self.info_lay.setSpacing(4)
        card.add(self.info_holder)

        title = QLabel("时间窗")
        title.setObjectName("SectionTitle")
        card.add(title)

        self.start_slider = QSlider(Qt.Horizontal)
        self.start_slider.valueChanged.connect(self._update_labels)
        card.add(self.start_slider)
        self.start_label = QLabel("起始 0.0 s")
        self.start_label.setObjectName("Mono")
        card.add(self.start_label)

        self.dur_slider = QSlider(Qt.Horizontal)
        self.dur_slider.setMinimum(int(MIN_WINDOW_SEC))
        self.dur_slider.setMaximum(int(MAX_WINDOW_SEC))
        self.dur_slider.setValue(10)
        self.dur_slider.valueChanged.connect(self._on_duration_changed)
        card.add(self.dur_slider)
        self.dur_label = QLabel("时长 10 s")
        self.dur_label.setObjectName("Mono")
        card.add(self.dur_label)

        self.cam_check = QCheckBox("显示 Grad-CAM 可解释性热力图")
        self.cam_check.setChecked(True)
        card.add(self.cam_check)

        self.preview_btn = QPushButton("预览波形")
        self.preview_btn.setObjectName("Ghost")
        self.preview_btn.setCursor(Qt.PointingHandCursor)
        self.preview_btn.clicked.connect(self.do_preview)
        card.add(self.preview_btn)

        self.analyze_btn = QPushButton("开始分析")
        self.analyze_btn.setObjectName("Primary")
        self.analyze_btn.setCursor(Qt.PointingHandCursor)
        self.analyze_btn.clicked.connect(self.do_analyze)
        card.add(self.analyze_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)          # 不确定进度：忙时滚动
        self.progress.setVisible(False)
        card.add(self.progress)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        card.add(self.status_label)

        card.body.addStretch(1)
        return card

    # ------------------------------------------------------------ 中：波形
    def _build_waveform(self) -> QWidget:
        card = Card("心电波形", "点击左侧「预览波形」加载信号")
        self.plot = ECGPlotWidget()
        self.plot.setMinimumHeight(300)
        card.add(self.plot)

        hint = QLabel("滚轮缩放 · 拖拽平移 · 双击复位 · 点击心搏标记可选中")
        hint.setObjectName("Muted")
        hint.setStyleSheet(f"color:{theme.TEXT_SOFT}; font-size:11px;")
        card.add(hint)
        card.body.addStretch(0)
        return card

    # ------------------------------------------------------------ 右：摘要
    def _build_summary(self) -> QWidget:
        card = Card("分析摘要", "完成一次分析后在此显示")
        card.setMinimumWidth(280)
        card.setMaximumWidth(370)

        self.summary_holder = QWidget()
        self.summary_lay = QVBoxLayout(self.summary_holder)
        self.summary_lay.setContentsMargins(0, 0, 0, 0)
        self.summary_lay.setSpacing(9)
        card.add(self.summary_holder)

        self.empty_hint = QLabel("尚未分析。设置好参数后点击「开始分析」。")
        self.empty_hint.setObjectName("Muted")
        self.empty_hint.setWordWrap(True)
        card.add(self.empty_hint)

        self.open_result_btn = QPushButton("查看完整报告 →")
        self.open_result_btn.setObjectName("Primary")
        self.open_result_btn.setCursor(Qt.PointingHandCursor)
        self.open_result_btn.setEnabled(False)
        self.open_result_btn.clicked.connect(
            lambda: self.navigateRequested.emit("result"))
        card.add(self.open_result_btn)

        card.body.addStretch(1)
        return card

    # ------------------------------------------------------------ 记录列表
    def reload_records(self) -> None:
        self.record_combo.blockSignals(True)
        self.record_combo.clear()
        try:
            self._records = AS.list_records()
        except Exception as exc:      # noqa: BLE001
            RS.log_exception("读取记录列表失败", exc)
            self._records = []
        for r in self._records:
            mark = "★ " if r.get("recommended") else ""
            self.record_combo.addItem(f"{mark}{r['id']} · {r.get('n_beats', 0):,} 搏")
        self.record_combo.blockSignals(False)
        if self._records:
            self.record_combo.setCurrentIndex(0)
            self._on_record_changed(0)

    def _on_record_changed(self, index: int) -> None:
        if not (0 <= index < len(self._records)):
            return
        rec = self._records[index]
        self._current = rec
        self.record_note.setText(rec.get("note", "") or "")

        total = float(rec.get("duration_sec", 0) or 0)
        max_start = max(0, int(total - MIN_WINDOW_SEC))
        self.start_slider.setRange(0, max_start)
        self.start_slider.setValue(0)
        max_dur = int(min(MAX_WINDOW_SEC, max(MIN_WINDOW_SEC, total)))
        self.dur_slider.setMaximum(max_dur)
        if self.dur_slider.value() > max_dur:
            self.dur_slider.setValue(max_dur)

        self._refresh_info(rec)
        self._update_labels()

    def _refresh_info(self, rec: dict) -> None:
        clear_layout(self.info_lay)
        counts = rec.get("class_counts", {}) or {}
        n = sum(counts.values()) or 1
        self.info_lay.addWidget(kv_row("记录编号", str(rec.get("id", "—"))))
        self.info_lay.addWidget(kv_row("总时长", f"{float(rec.get('duration_sec', 0)):.0f} s"))
        self.info_lay.addWidget(kv_row("心搏总数", fmt_int(rec.get("n_beats"))))
        self.info_lay.addWidget(kv_row("数据分组", str(rec.get("split", "—"))))
        self.info_lay.addWidget(kv_row(
            "异常占比", fmt_pct((n - counts.get("N", 0)) / n)))

        self.mini_stack = ClassStackBar()
        self.mini_stack.set_counts(counts)
        self.info_lay.addWidget(self.mini_stack)

    def _on_duration_changed(self) -> None:
        # 时长的上限随记录总长度收敛，起始位置不能越界
        total = float((self._current or {}).get("duration_sec", 0) or 0)
        dur = self.dur_slider.value()
        max_start = max(0, int(total - dur))
        self.start_slider.setRange(0, max_start)
        self._update_labels()

    def _update_labels(self) -> None:
        self.start_label.setText(f"起始 {float(self.start_slider.value()):.1f} s")
        self.dur_label.setText(f"时长 {self.dur_slider.value()} s")

    # ------------------------------------------------------------ 预览
    def do_preview(self) -> None:
        if not self._current or self._busy():
            return
        self._set_busy(True, "正在读取波形…")
        w = AS.PreviewWorker(self._current["id"], self.start_slider.value(),
                             self.dur_slider.value(), self)
        w.succeeded.connect(self._on_preview_ok)
        w.failed.connect(self._on_failed)
        w.progressed.connect(lambda t: self.status_label.setText(t))
        w.finished.connect(lambda: self._set_busy(False))
        self._preview_worker = w
        w.start()

    def _on_preview_ok(self, data: dict) -> None:
        marks = [
            {"sample": int(m["sample"]), "label": m.get("aami", "N"),
             "name": m.get("name", "")}
            for m in data.get("beat_marks", [])
        ]
        self.plot.set_data(data.get("signal", []), data.get("fs", C.FS),
                           marks, start_sec=float(data.get("start_sec", 0)))
        self.plot.set_title(
            f"记录 {data.get('record_id')} · 起始 {data.get('start_sec')} s · "
            f"{data.get('duration_sec')} s · 窗口内 {data.get('n_beats_in_window', 0)} 个心搏"
        )
        self.status_label.setText(
            f"预览完成：窗口内 {data.get('n_beats_in_window', 0)} 个心搏"
            "（标记颜色为专家标注类别）"
        )

    # ------------------------------------------------------------ 分析
    def do_analyze(self) -> None:
        if not self._current or self._busy():
            return
        self._set_busy(True, "正在准备分析…")
        self.progress.setVisible(True)
        self.analyze_btn.setText("分析中…")
        # 先把当前波形切到待分析窗口，用户能看到分析的是哪一段
        self.plot.set_cam(None)

        w = AS.AnalysisWorker(
            self._current["id"], self.start_slider.value(),
            self.dur_slider.value(), self.cam_check.isChecked(), self,
        )
        w.succeeded.connect(self._on_analysis_ok)
        w.failed.connect(self._on_failed)
        w.progressed.connect(lambda t: self.status_label.setText(t))
        w.finished.connect(self._on_analysis_finished)
        self._analysis_worker = w
        w.start()

    def _on_analysis_finished(self) -> None:
        self._set_busy(False)
        self.progress.setVisible(False)
        self.analyze_btn.setText("开始分析")

    def _on_analysis_ok(self, payload: dict) -> None:
        self._render_summary(payload)
        self.open_result_btn.setEnabled(True)
        n = payload.get("summary", {}).get("n_beats", 0)
        self.status_label.setText(f"分析完成：共 {n} 个心搏。点击右侧按钮查看完整报告。")
        self.analysisCompleted.emit(payload)

    def _render_summary(self, payload: dict) -> None:
        s = payload.get("summary", {})
        self.empty_hint.setVisible(False)
        clear_layout(self.summary_lay)

        self.summary_lay.addWidget(
            kv_row("记录", str(payload.get("record_id", "—"))))
        self.summary_lay.addWidget(
            kv_row("时间窗", f"{payload.get('start_sec')} s 起 {payload.get('duration_sec')} s"))

        for key, value in [
            ("分析心搏数", fmt_int(s.get("n_beats"))),
            ("平均置信度", fmt_pct(s.get("mean_confidence"), 1)),
            ("异常搏动数", fmt_int(s.get("abnormal_count"))),
            ("异常搏动占比", fmt_pct(s.get("abnormal_ratio"), 1)),
            ("与专家标注一致率", fmt_pct(s.get("agreement"), 1)),
        ]:
            self.summary_lay.addWidget(kv_row(key, value))

        risk = s.get("risk_level", {}) or {}
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        rl.addWidget(QLabel("提示等级"))
        rl.addWidget(Tag(risk.get("label", "—"), risk.get("color", theme.TEXT_SOFT)))
        rl.addStretch(1)
        self.summary_lay.addWidget(row)

        if payload.get("in_training_set"):
            warn = QLabel(
                "⚠ 该记录属于训练集（DS1），模型见过其数据，"
                "「与专家标注一致率」不代表泛化能力。"
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"color:{theme.WARN}; background:rgba(217,119,6,0.09);"
                "border-radius:8px; padding:8px 10px; font-size:11px;"
            )
            self.summary_lay.addWidget(warn)

        self.summary_lay.addWidget(self._section("心律类型构成"))
        stack = ClassStackBar()
        stack.set_counts(s.get("counts", {}))
        self.summary_lay.addWidget(stack)
        legend = ClassLegend()
        counts = s.get("counts", {})
        legend.set_items([(c, C.CLASS_NAMES_ZH[c], fmt_int(counts.get(c, 0)))
                          for c in C.AAMI_CLASSES])
        self.summary_lay.addWidget(legend)

    @staticmethod
    def _section(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("SectionTitle")
        return lab

    @staticmethod
    def _clear_layout(layout) -> None:
        clear_layout(layout)

    # ------------------------------------------------------------ 状态
    def _busy(self) -> bool:
        return (self._analysis_worker is not None and self._analysis_worker.isRunning()) \
            or (self._preview_worker is not None and self._preview_worker.isRunning())

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.preview_btn.setEnabled(not busy)
        self.analyze_btn.setEnabled(not busy)
        self.record_combo.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.setVisible(False)
        self.analyze_btn.setText("开始分析")
        self.status_label.setText(f"✗ {message}")
        self.status_label.setStyleSheet(f"color:{theme.DANGER};")

    def reset(self) -> None:
        """从结果页返回时重置状态提示样式。"""
        self.status_label.setStyleSheet("")
        self.progress.setVisible(False)
        self.analyze_btn.setText("开始分析")
        self._set_busy(False)
