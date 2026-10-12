"""分析服务：把 ECGAnalyzer 的阻塞调用放到后台线程，保证界面不卡死。

本模块**不重新实现任何推理逻辑**，只是把 src.inference 的调用搬进
QThread，并把异常翻译成用户看得懂的提示。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from src.inference import AnalysisError, get_analyzer

from . import resource_service as RS


class _BaseWorker(QThread):
    progressed = Signal(str)      # 阶段提示文字
    failed = Signal(str)          # 面向用户的错误描述

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cancelled = False

    def cancel(self) -> None:
        """请求放弃结果（真正的计算无法中断，但结果不再回传界面）。"""
        self._cancelled = True


class ModelWarmupWorker(_BaseWorker):
    """启动时后台加载模型，避免主窗口出现后才卡顿数秒。"""

    ready = Signal(str)

    def run(self) -> None:
        try:
            analyzer = get_analyzer()
            analyzer.model            # 触发权重加载
            analyzer.meta             # 触发记录元信息加载
            if not self._cancelled:
                self.ready.emit("系统就绪")
        except AnalysisError as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))
        except Exception as exc:      # noqa: BLE001 - 兜底，避免线程崩溃
            RS.log_exception("模型加载失败", exc)
            if not self._cancelled:
                self.failed.emit("模型加载失败，请检查安装文件是否完整。")


class AnalysisWorker(_BaseWorker):
    """执行一次完整的窗口分析。"""

    succeeded = Signal(dict)

    def __init__(self, record_id: str, start_sec: float, duration_sec: float,
                 with_cam: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.record_id = str(record_id)
        self.start_sec = float(start_sec)
        self.duration_sec = float(duration_sec)
        self.with_cam = bool(with_cam)

    def run(self) -> None:
        try:
            analyzer = get_analyzer()

            self.progressed.emit("正在读取心电信号…")
            # 先把信号与标注读入缓存：首次读取大文件耗时较明显，
            # 提前读取可以让"读取"与"推理"两个阶段各自有真实的进度提示。
            analyzer.get_signal(self.record_id)
            analyzer.get_annots(self.record_id)
            if self._cancelled:
                return

            self.progressed.emit("正在执行模型推理与 Grad-CAM 分析…")
            result = analyzer.analyze_window(
                self.record_id, self.start_sec, self.duration_sec,
                with_cam=self.with_cam,
            )
            if self._cancelled:
                return

            self.progressed.emit("正在汇总分析结果…")
            self.succeeded.emit(result)

        except AnalysisError as exc:
            # 输入类问题（记录不存在、时长越界等）直接把原因告诉用户
            if not self._cancelled:
                self.failed.emit(str(exc))
        except Exception as exc:      # noqa: BLE001
            RS.log_exception(f"分析记录 {self.record_id} 失败", exc)
            if not self._cancelled:
                self.failed.emit("分析失败，请查看日志了解详情。")


class PreviewWorker(_BaseWorker):
    """读取波形与专家标注位置，用于分析前的预览。"""

    succeeded = Signal(dict)

    def __init__(self, record_id: str, start_sec: float, duration_sec: float,
                 parent=None) -> None:
        super().__init__(parent)
        self.record_id = str(record_id)
        self.start_sec = float(start_sec)
        self.duration_sec = float(duration_sec)

    def run(self) -> None:
        try:
            analyzer = get_analyzer()
            self.progressed.emit("正在读取心电信号…")
            result = analyzer.preview_window(
                self.record_id, self.start_sec, self.duration_sec
            )
            if not self._cancelled:
                self.succeeded.emit(result)
        except AnalysisError as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))
        except Exception as exc:      # noqa: BLE001
            RS.log_exception(f"预览记录 {self.record_id} 失败", exc)
            if not self._cancelled:
                self.failed.emit("波形读取失败，请查看日志了解详情。")


# ---------------------------------------------------------------- 便捷访问
def list_records() -> list[dict]:
    """可选记录列表（复用推理引擎的记录元信息组织逻辑）。"""
    return get_analyzer().list_records()


def record_duration_sec(record_id: str) -> float:
    """记录总时长（秒），供时间窗控件设定上限。"""
    from src import config as C

    analyzer = get_analyzer()
    signal = analyzer.get_signal(str(record_id))
    return len(signal) / C.FS
