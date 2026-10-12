"""桌面端视觉规范：配色、字体与全局样式表。

设计基调沿用原 Web 版的临床医疗风格——浅色工作区 + 品牌蓝，心电绘图区
单独采用深色监护仪底色，保证波形与热力叠加的可读性。
"""
from __future__ import annotations

import sys

# ---------------------------------------------------------------- 品牌色
BRAND = "#1e6fd9"
BRAND_DARK = "#14509e"
BRAND_SOFT = "#eaf2fe"
ACCENT = "#0ea5a4"

BG = "#f4f7fb"
SURFACE = "#ffffff"
SURFACE_ALT = "#f8fafc"
BORDER = "#e3e9f2"
BORDER_SOFT = "#eef2f8"

TEXT = "#16202e"
TEXT_MID = "#4a5768"
TEXT_SOFT = "#7b8798"

OK = "#059669"
WARN = "#d97706"
DANGER = "#dc2626"
PURPLE = "#7c3aed"
SLATE = "#64748b"

# 侧边导航（深色）
NAV_BG = "#0f1b2d"
NAV_BG2 = "#16273f"
NAV_TEXT = "#9fb3cc"
NAV_TEXT_ACTIVE = "#ffffff"
NAV_HOVER = "rgba(255,255,255,0.07)"
# 深色导航栏上的状态文字需要提亮，否则 OK/DANGER 在深底上看不清
NAV_OK = "#7ee2b8"
NAV_DANGER = "#f0a6a6"

# 心电绘图区（深色监护仪风格，沿用原 Web 版 canvas 配色）
PLOT_BG = "#0d1b2e"
PLOT_GRID = "rgba(90,130,190,0.16)"
PLOT_GRID_MAJOR = "rgba(110,155,215,0.30)"
PLOT_AXIS = "rgba(150,180,220,0.45)"
PLOT_TEXT = "#8ea8c8"
PLOT_SIGNAL = "#3ddc97"
PLOT_CAM = "#f59e0b"

# AAMI 五类配色（与 Web 版、文档保持一致）
CLASS_COLOR = {
    "N": "#059669",
    "S": "#d97706",
    "V": "#dc2626",
    "F": "#7c3aed",
    "Q": "#64748b",
}

# 风险等级配色
RISK_COLOR = {"high": DANGER, "medium": WARN, "low": OK}


def font_family() -> str:
    """挑选一款系统里可用的中文字体。"""
    if sys.platform == "win32":
        return "Microsoft YaHei UI"
    return "Sans Serif"


def stylesheet() -> str:
    """全局 QSS。"""
    return f"""
* {{
    font-family: "{font_family()}", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}

QWidget#Root, QMainWindow {{
    background: {BG};
}}

/* ------------------------------------------------------------ 侧边导航 */
QFrame#Sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {NAV_BG}, stop:1 {NAV_BG2});
    border: none;
}}
QLabel#BrandName {{
    color: #ffffff;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: .5px;
}}
QLabel#BrandSub {{
    color: {NAV_TEXT};
    font-size: 11px;
}}
QLabel#NavSection {{
    color: #5d7a99;
    font-size: 11px;
}}
QPushButton#NavButton {{
    color: {NAV_TEXT};
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    padding: 11px 16px;
    text-align: left;
    font-size: 14px;
}}
QPushButton#NavButton:hover {{
    background: {NAV_HOVER};
    color: #dce8f7;
}}
QPushButton#NavButton:checked {{
    background: rgba(56,132,255,0.16);
    border-left: 3px solid {BRAND};
    color: {NAV_TEXT_ACTIVE};
    font-weight: 600;
}}
QLabel#NavFooter {{
    color: #6b7f99;
    font-size: 11px;
}}

/* ------------------------------------------------------------ 卡片 */
QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#StatCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-left: 3px solid {BRAND};
    border-radius: 10px;
}}
QLabel#StatKey {{
    color: {TEXT_SOFT};
    font-size: 12px;
}}
QLabel#StatValue {{
    color: {TEXT};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#StatUnit {{
    color: {TEXT_SOFT};
    font-size: 12px;
    font-weight: 400;
}}
QLabel#CardTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#CardSub {{
    color: {TEXT_SOFT};
    font-size: 12px;
}}
QLabel#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#PageSub {{
    color: {TEXT_SOFT};
    font-size: 13px;
}}
QLabel#SectionTitle {{
    font-size: 13px;
    font-weight: 700;
    color: {TEXT_MID};
}}
QLabel#Muted {{
    color: {TEXT_SOFT};
}}
QLabel#Mono {{
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    font-size: 12px;
    color: {TEXT_MID};
}}

/* ------------------------------------------------------------ 按钮 */
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
    color: {TEXT_MID};
}}
QPushButton:hover {{
    border-color: {BRAND};
    color: {BRAND};
}}
QPushButton:disabled {{
    color: #b6c0cd;
    border-color: {BORDER_SOFT};
    background: {SURFACE_ALT};
}}
QPushButton#Primary {{
    background: {BRAND};
    border: 1px solid {BRAND};
    color: #ffffff;
    font-weight: 600;
    padding: 10px 20px;
}}
QPushButton#Primary:hover {{ background: {BRAND_DARK}; border-color: {BRAND_DARK}; }}
QPushButton#Primary:disabled {{ background: #a9c4e8; border-color: #a9c4e8; color: #eef4fd; }}
QPushButton#Danger {{
    background: {SURFACE};
    border: 1px solid #f2c4c4;
    color: {DANGER};
}}
QPushButton#Danger:hover {{ background: #fef2f2; border-color: {DANGER}; }}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid {BORDER};
    color: {TEXT_MID};
}}
QPushButton#Ghost:hover {{ border-color: {BRAND}; color: {BRAND}; background: {BRAND_SOFT}; }}

/* ------------------------------------------------------------ 表单 */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {BRAND};
}}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{
    border-color: {BRAND};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {BRAND_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {BRAND};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #ffffff;
    border: 2px solid {BRAND};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 8px;
}}
QCheckBox {{ spacing: 7px; color: {TEXT_MID}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {BRAND};
    border-color: {BRAND};
}}

/* ------------------------------------------------------------ 表格 */
QTableWidget, QTableView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER_SOFT};
    selection-background-color: {BRAND_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QTableWidget::item, QTableView::item {{ padding: 7px 8px; }}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_SOFT};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 9px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_ALT}; border: none; }}

/* ------------------------------------------------------------ 进度条 */
QProgressBar {{
    background: {BORDER_SOFT};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 {BRAND}, stop:1 {ACCENT});
    border-radius: 5px;
}}

/* ------------------------------------------------------------ 其它 */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #cbd5e1; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #94a3b8; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: #cbd5e1; border-radius: 5px; min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QToolTip {{
    background: #1f2937;
    color: #f1f5f9;
    border: none;
    border-radius: 6px;
    padding: 6px 9px;
}}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; font-size: 13px; }}
"""


def light_palette() -> "QPalette":
    """显式的浅色调色板。

    样式表只覆盖写了选择器的控件；滚动区的 viewport、纯容器 QWidget 这类
    "没有选择器命中"的控件走的是调色板。Windows 若处于深色模式，Qt 会把
    系统深色调色板交给它们，于是页面底色变成近黑色（#1e1e1e），在卡片
    之间的间隙里露出来，看起来像一条条黑边。所以除了样式表，还必须把
    调色板钉死成浅色。
    """
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    p.setColor(QPalette.Window, QColor(BG))
    p.setColor(QPalette.WindowText, QColor(TEXT))
    p.setColor(QPalette.Base, QColor(SURFACE))
    p.setColor(QPalette.AlternateBase, QColor(SURFACE_ALT))
    p.setColor(QPalette.Text, QColor(TEXT))
    p.setColor(QPalette.Button, QColor(SURFACE))
    p.setColor(QPalette.ButtonText, QColor(TEXT))
    p.setColor(QPalette.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ToolTipBase, QColor(SURFACE))
    p.setColor(QPalette.ToolTipText, QColor(TEXT))
    p.setColor(QPalette.PlaceholderText, QColor(TEXT_SOFT))
    p.setColor(QPalette.Highlight, QColor(BRAND))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(TEXT_SOFT))
    p.setColor(QPalette.Disabled, QPalette.Base, QColor(SURFACE_ALT))
    return p


def apply(app) -> None:
    """把调色板与样式表挂到 QApplication 上。"""
    app.setPalette(light_palette())
    app.setStyleSheet(stylesheet())
