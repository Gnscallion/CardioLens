"""资源与运行环境：就绪检查、用户数据目录、日志、指标/元信息加载。

路径解析统一由 src.config 负责（开发时指向项目根，打包后指向解压目录），
本模块只做上层的组织与错误处理，不重复定义路径。
"""
from __future__ import annotations

import json
import logging
import platform
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src import config as C

_LOG_READY = False


# ---------------------------------------------------------------- 目录
def resource_root() -> Path:
    """只读资源根目录。"""
    return C.ROOT


def user_data_dir() -> Path:
    """用户可写数据目录（%LOCALAPPDATA%\\CardioLens 或开发时的 store/）。"""
    return C.STORE_DIR


def log_dir() -> Path:
    return C.LOG_DIR


def ensure_user_dirs() -> Path:
    """首次启动时创建用户目录，失败不应导致程序无法启动。"""
    for d in (C.STORE_DIR, C.LOG_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return C.STORE_DIR


# ---------------------------------------------------------------- 日志
def setup_logging() -> Path | None:
    """把详细异常写入用户目录下的日志文件，供开发排查。"""
    global _LOG_READY
    ensure_user_dirs()
    path = C.LOG_DIR / "cardiolens.log"
    if _LOG_READY:
        return path
    try:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        ))
        root = logging.getLogger("cardiolens")
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        root.propagate = False
        _LOG_READY = True
    except OSError:
        return None
    return path


def log_exception(context: str, exc: BaseException) -> None:
    """记录完整堆栈——只进日志文件，不给普通用户看。"""
    logger = logging.getLogger("cardiolens")
    logger.error("%s: %s\n%s", context, exc, "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    ))


def log_info(message: str) -> None:
    logging.getLogger("cardiolens").info(message)


# ---------------------------------------------------------------- 就绪检查
@dataclass
class Readiness:
    ok: bool
    message: str
    missing: list[str] = field(default_factory=list)


def check_readiness() -> Readiness:
    """桌面端自己的就绪判断。

    注意：这里刻意不检查 data/processed/beats.npz —— 该文件是训练用的
    心搏样本集，桌面端推理实际只读取 signals/ 与 annots/，把它打进 EXE
    会白白增加约 91 MB，因此不随包分发。
    """
    missing: list[str] = []
    if not C.RECORD_META.exists():
        missing.append("记录元信息 data/processed/record_meta.json")
    if not C.SIGNAL_DIR.is_dir():
        missing.append("心电信号目录 data/processed/signals/")
    if not (C.DATA_PROCESSED / "annots").is_dir():
        missing.append("心搏标注目录 data/processed/annots/")
    if not C.MODEL_PATH.exists():
        missing.append("模型权重 models/ecg_cnn.pt")

    if missing:
        return Readiness(False, "安装文件不完整", missing)
    return Readiness(True, "系统就绪", [])


# ---------------------------------------------------------------- 只读配置
def load_metrics() -> dict | None:
    """模型评估指标；缺失或损坏时返回 None，由界面降级显示。"""
    if not C.METRICS_PATH.exists():
        return None
    try:
        return json.loads(C.METRICS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log_exception("读取 metrics.json 失败", exc)
        return None


def load_meta() -> dict | None:
    """数据集元信息（记录清单、类别统计等）。"""
    if not C.RECORD_META.exists():
        return None
    try:
        return json.loads(C.RECORD_META.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log_exception("读取 record_meta.json 失败", exc)
        return None


# ---------------------------------------------------------------- 运行环境
def environment_info() -> dict[str, str]:
    """About 页展示用；全部为本地信息，不需要联网。"""
    def _ver(name: str) -> str:
        try:
            import importlib.metadata as md
            return md.version(name)
        except Exception:
            return "未知"

    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "torch": _ver("torch"),
        "numpy": _ver("numpy"),
        "pyside6": _ver("PySide6"),
        "platform": f"{platform.system()} {platform.release()}",
        # 这一项会直接显示在"运行方式：___"后面，所以取值必须是名词短语，
        # 不能是"是/否"——否则会读成"运行方式：否"。
        "packaged": "独立 EXE" if getattr(sys, "frozen", False) else "源码运行",
        "data_dir": str(C.STORE_DIR),
    }


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
