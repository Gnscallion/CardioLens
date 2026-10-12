"""页面基类：统一的标题区与内容容器。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


class BasePage(QWidget):
    """所有页面的父类。

    scroll=True 时内容放进滚动区（适合长页面）；否则由页面自行管理布局
    （适合需要分割器固定高度的分析工作台）。
    """

    navigateRequested = Signal(str)

    def __init__(self, title: str, subtitle: str = "", scroll: bool = True,
                 parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 20)
        outer.setSpacing(14)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        outer.addWidget(self.title_label)

        self.sub_label = QLabel(subtitle)
        self.sub_label.setObjectName("PageSub")
        self.sub_label.setWordWrap(True)
        outer.addWidget(self.sub_label)
        self.sub_label.setVisible(bool(subtitle))

        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            holder = QWidget()
            self.content = QVBoxLayout(holder)
            self.content.setContentsMargins(0, 0, 6, 0)
            self.content.setSpacing(14)
            area.setWidget(holder)
            outer.addWidget(area, 1)
            self._scroll = area
        else:
            self.content = QVBoxLayout()
            self.content.setSpacing(14)
            outer.addLayout(self.content, 1)
            self._scroll = None
