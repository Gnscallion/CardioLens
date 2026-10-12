"""通用界面组件：卡片、统计块、类别徽标、构成条。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import theme


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(x, nd: int = 1) -> str:
    try:
        return f"{float(x) * 100:.{nd}f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_f(x, nd: int = 3) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


class Card(QFrame):
    """带标题与副标题的白底卡片容器。"""

    def __init__(self, title: str = "", subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(18, 16, 18, 16)
        self._outer.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        self._title_box = QVBoxLayout()
        self._title_box.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        self.sub_label = QLabel(subtitle)
        self.sub_label.setObjectName("CardSub")
        self._title_box.addWidget(self.title_label)
        self._title_box.addWidget(self.sub_label)
        head.addLayout(self._title_box, 1)
        self.head = head
        self._outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self._outer.addLayout(self.body, 1)

        if not title:
            self.title_label.hide()
        if not subtitle:
            self.sub_label.hide()

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)

    def set_subtitle(self, text: str) -> None:
        self.sub_label.setText(text)
        self.sub_label.setVisible(bool(text))


class StatCard(QFrame):
    """指标卡：上方小字标题，下方大号数值 + 单位。"""

    def __init__(self, key: str, value: str = "—", unit: str = "",
                 accent: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(3)

        self.key_label = QLabel(key)
        self.key_label.setObjectName("StatKey")
        lay.addWidget(self.key_label)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        row.addWidget(self.value_label)
        self.unit_label = QLabel(unit)
        self.unit_label.setObjectName("StatUnit")
        row.addWidget(self.unit_label)
        row.addStretch(1)
        lay.addLayout(row)

        if accent:
            self.setStyleSheet(f"QFrame#StatCard {{ border-left: 3px solid {accent}; }}")

    def set_value(self, value: str, unit: str | None = None) -> None:
        self.value_label.setText(value)
        if unit is not None:
            self.unit_label.setText(unit)


class Badge(QLabel):
    """类别徽标（AAMI 代码）。"""

    def __init__(self, code: str, parent=None) -> None:
        super().__init__(code, parent)
        col = QColor(theme.CLASS_COLOR.get(code, theme.SLATE))
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(26, 20)
        soft = QColor(col)
        soft.setAlpha(30)
        self.setStyleSheet(
            f"color:{col.name()}; background:rgba({soft.red()},{soft.green()},{soft.blue()},0.14);"
            f"border:1px solid rgba({soft.red()},{soft.green()},{soft.blue()},0.35);"
            "border-radius:6px; font-weight:700; font-size:11px;"
        )


class Tag(QLabel):
    """浅色状态标签。"""

    def __init__(self, text: str, color: str = theme.BRAND, parent=None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        """按语义色重新着色（就绪/警告/危险等状态标签会动态切换）。"""
        col = QColor(color)
        self.setStyleSheet(
            f"color:{col.name()}; background:rgba({col.red()},{col.green()},{col.blue()},0.10);"
            f"border:1px solid rgba({col.red()},{col.green()},{col.blue()},0.28);"
            "border-radius:7px; padding:2px 9px; font-size:11px; font-weight:600;"
        )


class ClassStackBar(QWidget):
    """AAMI 五类样本构成条（按数量等比横向堆叠）。"""

    COLORS = theme.CLASS_COLOR

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._counts: dict[str, int] = {}
        self._order = ["N", "S", "V", "F", "Q"]

    def set_counts(self, counts: dict) -> None:
        self._counts = {k: int(counts.get(k, 0) or 0) for k in self._order}
        self.setToolTip("\n".join(
            f"{k}: {self._counts[k]:,}" for k in self._order if self._counts[k] > 0
        ))
        self.update()

    def paintEvent(self, _event) -> None:      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        total = sum(self._counts.values())
        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)

        if total <= 0:
            p.setBrush(QColor("#eef2f8"))
            p.drawRoundedRect(rect, 6, 6)
            p.end()
            return

        x = 0.0
        for code in self._order:
            n = self._counts.get(code, 0)
            if n <= 0:
                continue
            w = rect.width() * n / total
            p.setBrush(QColor(self.COLORS.get(code, theme.SLATE)))
            p.drawRect(QRectF(x, 0, w, rect.height()))
            if w > 26:
                p.setPen(QColor("#ffffff"))
                f = QFont(self.font())
                f.setPointSizeF(8.0)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRectF(x, 0, w, rect.height()), Qt.AlignCenter, code)
                p.setPen(Qt.NoPen)
            x += w
        p.end()


class ClassLegend(QWidget):
    """五类图例：色点 + 中文名 + 数量。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(16)
        self._lay.addStretch(1)

    def set_items(self, items: list[tuple[str, str, str]]) -> None:
        """items: [(code, 名称, 数量文字), ...]"""
        clear_layout(self._lay)
        for code, name, count in items:
            holder = QWidget()
            h = QHBoxLayout(holder)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            dot = QLabel()
            dot.setFixedSize(9, 9)
            dot.setStyleSheet(
                f"background:{theme.CLASS_COLOR.get(code, theme.SLATE)}; border-radius:4px;"
            )
            h.addWidget(dot)
            h.addWidget(QLabel(name))
            c = QLabel(count)
            c.setObjectName("Mono")
            h.addWidget(c)
            self._lay.addWidget(holder)
        self._lay.addStretch(1)


def clear_layout(layout) -> None:
    """清空布局里的全部控件。

    必须"先 setParent(None) 再 deleteLater()"：deleteLater() 只是投递一个
    DeferredDelete 事件，而 DeferredDelete 要等事件循环回到主层级才会派发。
    只调 deleteLater() 的话，旧控件在派发之前依然是父控件的子控件、依然会
    被绘制——反复刷新（切换记录、反复分析）时，新旧控件就会叠在一起。
    """
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{theme.BORDER_SOFT}; border:none;")
    return line


def stat_row(parent=None, columns: int = 4) -> tuple[QWidget, QGridLayout]:
    holder = QWidget(parent)
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(10)
    for c in range(columns):
        grid.setColumnStretch(c, 1)
    return holder, grid


def kv_row(key: str, value: str) -> QWidget:
    """一行「标签 —— 值」，用于信息面板。"""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    k = QLabel(key)
    k.setObjectName("Muted")
    k.setFixedWidth(96)
    v = QLabel(value)
    v.setWordWrap(True)
    lay.addWidget(k)
    lay.addWidget(v, 1)
    return w
