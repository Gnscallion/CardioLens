"""CardioLens 桌面版程序入口。

启动流程：
    初始化 Qt → 创建用户数据目录 → 初始化数据库 → 显示主窗口
    → 后台加载模型 / 指标 / 心电数据 → 侧栏显示「系统就绪」

全程不启动任何服务器，不监听任何端口，不依赖网络。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许以 `python desktop/main.py` 直接运行（把项目根目录加入模块搜索路径）
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QMessageBox      # noqa: E402

from desktop import theme                                    # noqa: E402
from desktop.app import MainWindow, install_excepthook        # noqa: E402
from desktop.services import history_service as HS            # noqa: E402
from desktop.services import resource_service as RS           # noqa: E402
from desktop.services.analysis_service import ModelWarmupWorker  # noqa: E402
from src import config as C                                   # noqa: E402


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName(C.APP_NAME)
    application.setApplicationDisplayName(C.APP_NAME)
    application.setOrganizationName(C.APP_NAME)

    theme.apply(application)
    install_excepthook()

    # -------- 可写数据目录与日志（必须在任何数据库操作之前）
    RS.setup_logging()
    RS.ensure_user_dirs()
    RS.log_info(f"{C.APP_NAME} 启动，数据目录 {RS.user_data_dir()}")

    # -------- 数据库：沿用既有 schema，首次运行时自动建表
    db_error = ""
    try:
        HS.init_db()
    except Exception as exc:      # noqa: BLE001 - 启动阶段兜底
        RS.log_exception("初始化数据库失败", exc)
        db_error = str(exc).splitlines()[0]

    # -------- 主窗口
    window = MainWindow()
    window.set_status("正在加载模型……", True)
    window.show()

    if db_error:
        window.set_status("历史记录不可用", False)
        QMessageBox.warning(
            window, "历史记录不可用",
            "无法初始化历史记录数据库，本次仍可正常分析，但结果无法保存。\n"
            f"数据目录：{RS.user_data_dir()}\n\n{db_error}"
        )

    # -------- 就绪检查：缺文件时如实告知，不阻断界面
    readiness = RS.check_readiness()
    if not readiness.ok:
        RS.log_info("就绪检查未通过：" + "；".join(readiness.missing))
        window.set_status("安装文件不完整", False)
        QMessageBox.critical(
            window, "安装文件不完整",
            "缺少以下文件，相关功能将无法使用：\n  · "
            + "\n  · ".join(readiness.missing)
            + "\n\n请重新获取完整的安装包。"
        )

    # -------- 后台加载模型与数据，界面在此期间保持可交互
    warmup = ModelWarmupWorker(window)

    def _on_ready(_message: str) -> None:
        RS.log_info("模型与数据加载完成，系统就绪")
        window.set_status("系统就绪", True)

    def _on_failed(message: str) -> None:
        window.set_status("模型加载失败", False)
        QMessageBox.critical(
            window, "模型加载失败",
            f"{message}\n\n日志目录：{RS.log_dir()}"
        )

    warmup.ready.connect(_on_ready)
    warmup.failed.connect(_on_failed)
    warmup.start()

    try:
        return application.exec()
    finally:
        warmup.cancel()
        warmup.wait(5000)


if __name__ == "__main__":
    sys.exit(main())
