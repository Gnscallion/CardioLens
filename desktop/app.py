"""主窗口：左侧固定导航 + 右侧页面堆栈。

这是纯 PySide6 原生桌面窗口，内部不启动任何服务、不使用任何浏览器组件。
"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QMainWindow, QMessageBox,
                               QStackedWidget, QWidget)

from src import config as C

from . import theme
from .services import history_service as HS
from .services import resource_service as RS
from .pages.about_page import AboutPage
from .pages.analyze_page import AnalyzePage
from .pages.history_page import HistoryPage
from .pages.home_page import HomePage
from .pages.result_page import ResultPage
from .widgets.sidebar import Sidebar

# 页面在堆栈中的固定下标
PAGE_HOME = 0
PAGE_ANALYZE = 1
PAGE_RESULT = 2
PAGE_HISTORY = 3
PAGE_ABOUT = 4
PAGE_DETAIL = 5          # 历史报告详情（只读复用结果页）

NAV_TO_PAGE = {
    "home": PAGE_HOME,
    "analyze": PAGE_ANALYZE,
    "result": PAGE_RESULT,
    "history": PAGE_HISTORY,
    "about": PAGE_ABOUT,
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{C.APP_NAME} · {C.APP_NAME_ZH}")
        self.resize(1200, 760)
        self.setMinimumSize(1000, 650)

        self._last_payload: dict | None = None

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigated.connect(self.goto)
        lay.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._build_pages()
        self.stack.setCurrentIndex(PAGE_HOME)
        self.sidebar.set_active("home")
        QTimer.singleShot(0, self.home.refresh)

    # ------------------------------------------------------------ 组装
    def _build_pages(self) -> None:
        self.home = HomePage()
        self.analyze = AnalyzePage()
        self.result = ResultPage(readonly=False)
        self.history = HistoryPage()
        self.about = AboutPage()
        self.detail = ResultPage(readonly=True)

        for page in (self.home, self.analyze, self.result,
                     self.history, self.about, self.detail):
            self.stack.addWidget(page)
            page.navigateRequested.connect(self.goto)

        self.analyze.analysisCompleted.connect(self._on_analysis_done)
        self.history.openRequested.connect(self._open_history_report)
        self.detail.deleteRequested.connect(self._delete_report)
        self.result.deleteRequested.connect(self._delete_report)

    # ------------------------------------------------------------ 导航
    def goto(self, key: str) -> None:
        index = NAV_TO_PAGE.get(key)
        if index is None:
            return

        if key == "result" and self._last_payload is None:
            # 还没有任何分析结果可看，留在工作台并提示
            self.stack.setCurrentIndex(PAGE_ANALYZE)
            self.sidebar.set_active("analyze")
            return

        if key == "home":
            self.home.refresh()
        elif key == "history":
            self.history.refresh()
        elif key == "analyze":
            self.analyze.reset()

        self.stack.setCurrentIndex(index)
        # 详细页不属于主导航，此时高亮「分析历史」
        self.sidebar.set_active("history" if index == PAGE_DETAIL else key)

    def _on_analysis_done(self, payload: dict) -> None:
        self._last_payload = payload
        self.result.set_payload(payload)
        self.result.save_btn.setEnabled(True)
        self.result.save_btn.setText("保存报告到历史记录")

    # ------------------------------------------------------------ 历史详情
    def _open_history_report(self, analysis_id: int) -> None:
        try:
            row = HS.get_analysis(int(analysis_id))
        except HS.HistoryError as exc:
            QMessageBox.warning(self, "读取失败", str(exc))
            return
        if not row:
            QMessageBox.information(self, "报告不存在",
                                    "该报告可能已被删除，请刷新后重试。")
            self.history.refresh()
            return

        payload = row.get("payload") or {}
        if not payload.get("beats"):
            QMessageBox.information(self, "报告内容缺失",
                                    "该报告没有可回放的明细数据。")
            return
        self.detail.set_payload(payload, analysis_id=int(analysis_id),
                                saved_at=str(row.get("created_at", "")))
        self.stack.setCurrentIndex(PAGE_DETAIL)
        self.sidebar.set_active("history")

    def _delete_report(self, analysis_id: int) -> None:
        page = self.sender()
        try:
            HS.delete_analysis(int(analysis_id))
        except HS.HistoryError as exc:
            if isinstance(page, ResultPage):
                page.show_delete_result(False, str(exc))
            else:
                QMessageBox.warning(self, "删除失败", str(exc))
            return
        if isinstance(page, ResultPage):
            page.show_delete_result(True)
        else:
            self.history.refresh()

    # ------------------------------------------------------------ 状态
    def set_status(self, text: str, ok: bool = True) -> None:
        self.sidebar.set_status(text, ok)

    def closeEvent(self, event) -> None:      # noqa: N802 - Qt 命名
        """等待后台线程收尾，避免退出瞬间的 Qt 警告。"""
        for page in (self.analyze,):
            for attr in ("_analysis_worker", "_preview_worker"):
                worker = getattr(page, attr, None)
                if worker is not None and worker.isRunning():
                    worker.cancel()
                    worker.wait(3000)
        super().closeEvent(event)


def install_excepthook() -> None:
    """任何未捕获异常都只写日志并给出友好提示，绝不把 traceback 抛给用户。"""
    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        RS.log_exception("未捕获异常", exc)
        try:
            QMessageBox.critical(
                None, "程序出现异常",
                "程序遇到一个意外问题，已记录到日志文件。\n"
                f"日志目录：{RS.log_dir()}\n\n"
                "建议保存好当前工作后重新启动软件。"
            )
        except Exception:      # noqa: BLE001 - 异常处理器本身不能再抛
            traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = _hook


def apply_theme(app) -> None:
    theme.apply(app)
