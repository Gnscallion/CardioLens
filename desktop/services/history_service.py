"""历史记录服务：包装 src.db，把数据库异常翻译成用户可读提示。

数据库 schema 完全沿用 src/db.py，桌面端不新增、不修改任何表结构。
"""
from __future__ import annotations

import sqlite3

from src import db

from . import resource_service as RS


class HistoryError(Exception):
    """历史记录操作失败，消息可直接展示给用户。"""


def _guard(action: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except sqlite3.Error as exc:
        RS.log_exception(f"历史记录{action}失败", exc)
        raise HistoryError(
            f"历史记录{action}失败，数据库可能被占用或损坏。\n"
            f"数据目录：{RS.user_data_dir()}"
        ) from exc
    except OSError as exc:
        RS.log_exception(f"历史记录{action}失败", exc)
        raise HistoryError(f"历史记录{action}失败，无法访问数据目录。") from exc


def init_db() -> None:
    _guard("初始化", db.init_db)


def save_analysis(payload: dict, title: str | None = None) -> int:
    return _guard("保存", db.save_analysis, payload, title)


def list_analyses(limit: int = 200) -> list[dict]:
    return _guard("读取", db.list_analyses, limit)


def get_analysis(analysis_id: int) -> dict | None:
    return _guard("读取", db.get_analysis, analysis_id)


def delete_analysis(analysis_id: int) -> bool:
    return _guard("删除", db.delete_analysis, analysis_id)


def clear_all() -> int:
    return _guard("清空", db.clear_all)


def stats() -> dict:
    try:
        return db.stats()
    except sqlite3.Error as exc:
        RS.log_exception("历史统计失败", exc)
        # 统计失败不该让首页崩掉，返回零值降级显示
        return {"total_analyses": 0, "total_beats": 0,
                "avg_abnormal_ratio": 0.0, "avg_agreement": 0.0}
