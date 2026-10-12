"""关于页：软件说明、数据来源、模型与训练设置、性能、可解释性与免责声明。

本页内容全部来自项目本地的 models/metrics.json、data/processed/record_meta.json
与已训练好的模型文件，不联网、不调用任何外部服务。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src import config as C
from src.model import CAM_LAYER_NAME

from .. import theme
from ..services import resource_service as RS
from ..widgets.common import (Card, StatCard, hline, fmt_int, fmt_pct, kv_row)
from ..widgets.metric_card import PerClassTable
from .base import BasePage

IMG_WIDTH = 620


class AboutPage(BasePage):
    def __init__(self, parent=None) -> None:
        super().__init__(C.APP_NAME, f"{C.APP_NAME_ZH} · 版本与技术说明", parent=parent)

        self._build_intro()
        self._build_dataset()
        self._build_classes()
        self._build_model()
        self._build_training()
        self._build_performance()
        self._build_explainability()
        self._build_notes()
        self.content.addStretch(1)

    # ------------------------------------------------------------ 1 简介
    def _build_intro(self) -> None:
        card = Card("1 · 软件简介")
        text = QLabel(
            f"{C.APP_NAME}（{C.APP_NAME_ZH}）是一款面向心电节律分析的"
            "<b>原生 Windows 桌面软件</b>。选取任意一段心电记录并指定时间窗后，"
            "软件会逐搏定位心搏位置、判别其 AAMI 类型、给出五类概率分布，"
            "并通过 Grad-CAM 展示模型判断时所关注的波形区间，"
            "最终生成可保存、可回溯的结构化分析报告。"
            "<br><br>"
            "软件完全在本机离线运行：不需要网络连接，不需要安装任何运行环境，"
            "所有计算（含深度学习推理）都在本机 CPU 上完成。"
            "分析记录保存在本机数据库中，不会上传到任何服务器。"
        )
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:13px;")
        card.add(text)
        self.content.addWidget(card)

    # ------------------------------------------------------------ 2 数据
    def _build_dataset(self) -> None:
        meta = RS.load_meta() or {}
        card = Card("2 · 数据来源")
        text = QLabel(
            "本软件使用 <b>MIT-BIH Arrhythmia Database</b>（PhysioNet 公开数据集）"
            "中的真实临床心电记录，采用国际通行的 <b>AAMI EC57</b> 五分类标准进行标注。"
        )
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:13px;")
        card.add(text)

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        for key, value in [
            ("心电记录数", fmt_int(len(meta.get("records", [])))),
            ("心搏样本总数", fmt_int(meta.get("total_beats"))),
            ("采样率", f"{C.FS}"),
            ("单搏窗口", f"{C.BEAT_LEN}"),
        ]:
            unit = {"采样率": "Hz", "单搏窗口": "采样点"}.get(key, "")
            lay.addWidget(StatCard(key, value, unit))
        card.add(row)

        card.add(kv_row("数据来源", str(meta.get("source", "—"))))
        card.add(hline())

        # 通道说明：MIT-BIH 各记录的两个导联并不统一，不能笼统说通道 0 就是 MLII
        note = QLabel(
            "<b>关于导联通道：</b>MIT-BIH 各条记录实际使用的两个导联并不统一，"
            "通道 0 并不总是 MLII（常见的还有 V1、V5、MLI 等组合）。"
            f"本软件统一读取<b>通道 0</b>，并在该通道上完成全部逐搏分析，"
            "因此不同记录之间的波形形态差异属于数据本身的导联差异，并非处理错误。"
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{theme.TEXT_MID}; background:{theme.BRAND_SOFT};"
            "border-radius:8px; padding:9px 12px; font-size:12px;"
        )
        card.add(note)

        split = QLabel(
            f"划分方式：采用 <b>inter-patient</b> 方案（de Chazal DS1/DS2），"
            f"训练集 {fmt_int(meta.get('n_train'))} 搏、测试集 {fmt_int(meta.get('n_test'))} 搏，"
            "两者患者完全不重叠，指标更接近跨患者的真实使用场景。"
        )
        split.setWordWrap(True)
        split.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
        card.add(split)
        self.content.addWidget(card)

    # ------------------------------------------------------------ 3 五分类
    def _build_classes(self) -> None:
        card = Card("3 · AAMI 五分类定义")
        for code in C.AAMI_CLASSES:
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            tag = QLabel(code)
            tag.setAlignment(Qt.AlignCenter)
            tag.setFixedSize(30, 22)
            tag.setStyleSheet(
                f"color:#ffffff; background:{theme.CLASS_COLOR.get(code, theme.SLATE)};"
                "border-radius:6px; font-weight:700;"
            )
            lay.addWidget(tag)
            name = QLabel(C.CLASS_NAMES_ZH[code])
            name.setFixedWidth(120)
            name.setStyleSheet("font-weight:600;")
            lay.addWidget(name)
            desc = QLabel(C.CLASS_DESC[code])
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
            lay.addWidget(desc, 1)
            card.add(row)

        note = QLabel(
            "说明：另有 AAMI 中并不属于上述五类的「未分类/起搏」以外的杂类搏动，"
            "以及部分记录中以 <b>Q</b> 归入的起搏与无法归类的搏动。"
            "Q 类样本在整个数据集中仅有 15 个，任何模型都无法在该类上学到稳定规律，"
            "本软件如实显示其预测结果，不做任何隐瞒或美化。"
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        card.add(note)
        self.content.addWidget(card)

    # ------------------------------------------------------------ 4 模型结构
    def _build_model(self) -> None:
        metrics = RS.load_metrics() or {}
        card = Card("4 · 模型结构")
        text = QLabel(
            "模型采用<b>双分支</b>结构：一路以单搏波形（252 个采样点）为输入的"
            "<b>一维卷积神经网络</b>，用于学习 QRS 形态特征；另一路以该搏的"
            "<b>RR 间期特征</b>为输入的小型多层感知机，用于刻画节律信息；"
            "两路特征在分类头前拼接后共同决定最终类别。"
        )
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:13px;")
        card.add(text)

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(StatCard("模型参数量", fmt_int(metrics.get("n_params")), "个"))
        lay.addWidget(StatCard("波形输入", f"{C.BEAT_LEN}", "采样点"))
        lay.addWidget(StatCard("单搏窗口", f"{C.PRE_SAMPLES}+{C.POST_SAMPLES}", "采样点"))
        lay.addWidget(StatCard("RR 特征维度", f"{C.RR_DIM}", "维"))
        card.add(row)

        structure = QLabel(
            "<b>波形分支：</b>4 个卷积块逐级提取形态特征，每个卷积块由一维卷积、"
            "批归一化与 ReLU 组成，并在其间进行最大池化；经全局池化后得到波形特征向量。"
            "<br><b>节律分支：</b>RR 间期特征先经一层 4 → 16 维的小型多层感知机映射，"
            "再与波形特征向量<b>拼接</b>后送入全连接分类头。"
            "<br><b>Grad-CAM 目标层：</b>波形分支的最后一个卷积块 "
            f"<code>{CAM_LAYER_NAME}</code>，因此热力图只解释波形分支的注意力，"
            "不反映 RR 分支的贡献。"
        )
        structure.setWordWrap(True)
        structure.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
        card.add(structure)
        self.content.addWidget(card)

    # ------------------------------------------------------------ 5 训练设置
    def _build_training(self) -> None:
        metrics = RS.load_metrics() or {}
        card = Card("5 · 训练设置")
        secs = float(metrics.get("train_seconds", 0) or 0)
        card.add(kv_row("优化器", "AdamW"))
        card.add(kv_row("学习率", f"{metrics.get('lr', '—')}"))
        card.add(kv_row(
            "权重衰减",
            f"{metrics.get('weight_decay', '—')}"
            "（AdamW 常规量级，未做额外加强）",
        ))
        card.add(kv_row("Dropout", f"{metrics.get('dropout', '—')}"))
        card.add(kv_row(
            "数据增强",
            "启用" if metrics.get("use_augment") else "未启用",
        ))
        card.add(kv_row("训练轮数", f"{len((metrics.get('history') or {}).get('epoch', []))} 轮"))
        card.add(kv_row("最优轮次", f"第 {metrics.get('best_epoch', '—')} 轮"))
        card.add(kv_row("模型选择依据", str(metrics.get("main_metric", "—"))))
        card.add(kv_row(
            "训练耗时",
            f"{secs / 60:.1f} 分钟（{secs:.0f} 秒，纯 CPU 训练）",
        ))
        card.add(kv_row("验证集记录",
                        "、".join(str(x) for x in metrics.get("val_records", [])) or "—"))

        # 训练过程的如实描述：验证损失并非单调上升，而是波动并伴随后期过拟合倾向
        hist = (metrics.get("history") or {}).get("val_loss") or []
        if hist:
            best_ep = int(metrics.get("best_epoch") or 1)
            early = hist[0]
            late = sum(hist[max(best_ep - 1, 0):]) / max(len(hist) - max(best_ep - 1, 0), 1)
            loss_note = QLabel(
                f"<b>关于验证损失：</b>第 1 轮验证损失约 {early:.3f}，"
                f"整体呈<b>波动</b>状态而非单调变化；从第 {best_ep} 轮（最优轮次）之后，"
                f"验证损失平均水平抬升到约 {late:.3f}，同时验证准确率不再提升，"
                "呈现出典型的<b>后期过拟合趋势</b>。"
                f"模型参数取自第 {best_ep} 轮（验证集 Macro-F1 最优），"
                "而非训练末轮。"
            )
            loss_note.setWordWrap(True)
            loss_note.setStyleSheet(
                f"color:{theme.TEXT_MID}; background:{theme.BRAND_SOFT};"
                "border-radius:8px; padding:9px 12px; font-size:12px;"
            )
            card.add(loss_note)
        self.content.addWidget(card)

    # ------------------------------------------------------------ 6 性能
    def _build_performance(self) -> None:
        metrics = RS.load_metrics() or {}
        card = Card("6 · 测试集性能",
                    "测试集与训练集患者完全不重叠（inter-patient）")

        test = metrics.get("test", {}) or {}
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(StatCard("整体准确率", fmt_pct(test.get("accuracy"), 2), accent=theme.BRAND))
        lay.addWidget(StatCard("四类 Macro-F1", f"{float(test.get('macro_f1', 0)):.4f}",
                               accent=theme.ACCENT))
        lay.addWidget(StatCard("五类 Macro-F1", f"{float(test.get('macro_f1_5class', 0)):.4f}"))
        lay.addWidget(StatCard("测试集样本数", fmt_int(metrics.get("n_test")), "搏"))
        card.add(row)

        table = PerClassTable()
        table.load(metrics)
        table.setMinimumHeight(180)
        card.add(table)

        explain = QLabel(
            "表中列出 <b>N/S/V/F 四类</b>的精确率、召回率与 F1，与「四类 Macro-F1」对应；"
            "Q 类在测试集中仅有极少数样本，其指标会被 0 值主导，"
            "因此不单独展示，仅作为五个类别之一计入「五类 Macro-F1」的平均。"
            "<br>准确率看似很高，主要是因为 N 类（正常搏动）占比接近九成；"
            "少数类（尤其 S 类）的召回率明显偏低，四类 Macro-F1 因此只有约 0.50，"
            "这才是更值得参考的真实水平。"
        )
        explain.setWordWrap(True)
        explain.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
        card.add(explain)
        self.content.addWidget(card)

        self._build_plots()

    def _build_plots(self) -> None:
        has_matrix = self._add_image(
            "混淆矩阵", "models/confusion_matrix.png",
            "纵轴为专家标注类别，横轴为模型预测类别；对角线越深表示判别越准确，"
            "非对角线的深色格子即为主要混淆方向。")
        if not has_matrix:
            RS.log_info("未找到 models/confusion_matrix.png，关于页跳过该图")

        has_curve = self._add_image(
            "训练曲线", "models/training_curve.png",
            "训练损失持续下降，而验证损失在中后期波动并抬升、验证指标不再提升，"
            "是典型的过拟合信号，模型最终取验证集最优轮次的参数。")
        if not has_curve:
            RS.log_info("未找到 models/training_curve.png，关于页跳过该图")

    def _add_image(self, title: str, rel_path: str, caption: str) -> bool:
        path = RS.resource_root() / rel_path
        if not path.exists():
            return False
        pix = QPixmap(str(path))
        if pix.isNull():
            return False

        card = Card(title)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setPixmap(pix.scaledToWidth(IMG_WIDTH, Qt.SmoothTransformation))
        card.add(label)
        note = QLabel(caption)
        note.setWordWrap(True)
        note.setObjectName("Muted")
        card.add(note)
        self.content.addWidget(card)
        return True

    # ------------------------------------------------------------ 7 可解释性
    def _build_explainability(self) -> None:
        card = Card("7 · 可解释性（Grad-CAM）")
        text = QLabel(
            "对每一次逐搏预测，软件都会计算该搏的 Grad-CAM 归因。"
            "做法是取波形分支最后一个卷积块（"
            f"<code>{CAM_LAYER_NAME}</code>）的特征图，用目标类别的梯度加权求和，"
            "得到 31 个时间步的权重序列，再上采样到单搏窗口的 252 个采样点，"
            "与心搏波形一一对齐后叠加显示。"
            "<br><br>"
            "<b>使用时的两点注意：</b>"
            "<br>· 热力图暖色越深，表示模型在做出该预测时越依赖这一小段波形；"
            "它反映的是模型的“关注点”，而不是医学上的“病灶位置”。"
            "<br>· Grad-CAM 只解释波形分支，不会反映 RR 节律分支的贡献；"
            "因此当模型主要依据节律信息做出判断时，热力图可能并不明显。"
            "<br>· Grad-CAM 只用于展示，<b>不会参与、也不会影响</b>模型的推理结果。"
        )
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:13px;")
        card.add(text)
        self.content.addWidget(card)

    # ------------------------------------------------------------ 8 说明
    def _build_notes(self) -> None:
        card = Card("8 · 已知限制与使用说明")
        limits = QLabel(
            "· <b>不是医疗器械</b>：本软件是软件工程课程作业的演示项目，"
            "未经任何医疗器械注册与临床验证，不得用于诊断、治疗或任何临床决策。"
            "<br>· <b>少数类识别能力有限</b>：S 类（室上性早搏）的召回率明显偏低，"
            "V 类相对可用，Q 类几乎无法识别，这与数据集本身的类别极不平衡直接相关。"
            "<br>· <b>数据规模有限</b>：仅使用 MIT-BIH 的 44 条记录，"
            "不同记录之间的导联与个体差异都会影响表现，跨数据集泛化能力未经验证。"
            "<br>· <b>训练集记录的展示需谨慎</b>：分析属于训练集（DS1）的记录时，"
            "模型见过这些数据，界面会明确提示，其“与专家标注一致率”不代表模型真实水平。"
            "<br>· <b>分析结果依赖时间窗选择</b>：窗口内有效心搏过少时结果不具代表性，"
            "建议选择不少于 10 秒的窗口。"
        )
        limits.setWordWrap(True)
        limits.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
        card.add(limits)

        card.add(self._env_block())
        self.content.addWidget(card)

        dis = Card()
        title = QLabel("⚠ 免责声明")
        title.setStyleSheet(f"color:{theme.DANGER}; font-weight:700;")
        dis.add(title)
        text = QLabel(C.DISCLAIMER)
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{theme.TEXT_MID}; font-size:12px;")
        dis.add(text)
        self.content.addWidget(dis)

    def _env_block(self) -> QWidget:
        """运行环境概览（全部为本地信息，不联网获取）。"""
        env = RS.environment_info()
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        for key, value in [
            ("运行方式", env.get("packaged", "—")),
            ("PyTorch", env.get("torch", "—")),
            ("Python", env.get("python", "—")),
            ("界面框架", f"PySide6 {env.get('pyside6', '')}"),
            ("操作系统", env.get("platform", "—")),
        ]:
            lay.addWidget(StatCard(key, value))
        return holder
