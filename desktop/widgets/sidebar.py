"""左侧固定导航栏。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from src import config as C

from .. import theme

NAV_ITEMS = [
    ("home", "⌂", "首页"),
    ("analyze", "♡", "ECG 分析"),
    ("history", "▣", "分析历史"),
    ("about", "ℹ", "关于"),
]


class Sidebar(QFrame):
    navigated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(212)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 22, 0, 16)
        lay.setSpacing(0)

        # -------- 品牌区
        brand = QWidget()
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(20, 0, 18, 22)
        bl.setSpacing(3)
        name = QLabel(C.APP_NAME)
        name.setObjectName("BrandName")
        sub = QLabel(C.APP_NAME_ZH)
        sub.setObjectName("BrandSub")
        sub.setWordWrap(True)
        bl.addWidget(name)
        bl.addWidget(sub)
        lay.addWidget(brand)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:rgba(255,255,255,0.09); border:none;")
        lay.addWidget(line)
        lay.addSpacing(12)

        # -------- 导航按钮
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, icon, text in NAV_ITEMS:
            btn = QPushButton(f"  {icon}   {text}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(42)
            btn.clicked.connect(lambda _=False, k=key: self.navigated.emit(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            lay.addWidget(btn)

        lay.addStretch(1)

        # -------- 底部状态
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(20, 0, 18, 0)
        fl.setSpacing(4)
        self.status_label = QLabel("正在初始化…")
        self.status_label.setObjectName("NavFooter")
        self.status_label.setWordWrap(True)
        fl.addWidget(self.status_label)
        ver = QLabel(f"{C.APP_NAME_EN}")
        ver.setObjectName("NavFooter")
        ver.setWordWrap(True)
        fl.addWidget(ver)
        lay.addWidget(foot)

        self.set_active("home")

    # ------------------------------------------------------------ 接口
    def set_active(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)

    def set_status(self, text: str, ok: bool = True) -> None:
        color = theme.NAV_OK if ok else theme.NAV_DANGER
        self.status_label.setStyleSheet(f"color:{color}; font-size:11px;")
        self.status_label.setText(text)
