"""历史记录持久化：SQLite。

每次分析保存一条完整结果（含逐搏明细的 JSON），便于"历史记录"页回看与
导出。SQLite 无需额外服务，符合项目"开箱即用"的要求。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT    NOT NULL,
    record_id      TEXT    NOT NULL,
    start_sec      REAL    NOT NULL,
    duration_sec   REAL    NOT NULL,
    n_beats        INTEGER NOT NULL,
    abnormal_count INTEGER NOT NULL,
    abnormal_ratio REAL    NOT NULL,
    risk_code      TEXT    NOT NULL,
    risk_label     TEXT    NOT NULL,
    agreement      REAL    NOT NULL,
    mean_conf      REAL    NOT NULL,
    counts_json    TEXT    NOT NULL,
    payload_json   TEXT    NOT NULL,
    created_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
"""


@contextmanager
def connect():
    C.STORE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(C.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_analysis(payload: dict, title: str | None = None) -> int:
    s = payload["summary"]
    default_title = (
        f"记录 {payload['record_id']} · {payload['start_sec']:.1f}s 起 "
        f"{payload['duration_sec']:.0f} 秒"
    )
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO analyses
               (title, record_id, start_sec, duration_sec, n_beats, abnormal_count,
                abnormal_ratio, risk_code, risk_label, agreement, mean_conf,
                counts_json, payload_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                (title or "").strip() or default_title,
                payload["record_id"], payload["start_sec"], payload["duration_sec"],
                s["n_beats"], s["abnormal_count"], s["abnormal_ratio"],
                s["risk_level"]["code"], s["risk_level"]["label"],
                s["agreement"], s["mean_confidence"],
                json.dumps(s["counts"], ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        return int(cur.lastrowid)


def list_analyses(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, title, record_id, start_sec, duration_sec, n_beats,
                      abnormal_count, abnormal_ratio, risk_code, risk_label,
                      agreement, mean_conf, counts_json, created_at
               FROM analyses ORDER BY id DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["counts"] = json.loads(d.pop("counts_json"))
        out.append(d)
    return out


def get_analysis(analysis_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (int(analysis_id),)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json"))
    d.pop("counts_json", None)
    return d


def delete_analysis(analysis_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM analyses WHERE id = ?", (int(analysis_id),))
        return cur.rowcount > 0


def clear_all() -> int:
    with connect() as conn:
        cur = conn.execute("DELETE FROM analyses")
        return cur.rowcount


def stats() -> dict:
    with connect() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM(n_beats), 0) AS beats,
                      COALESCE(AVG(abnormal_ratio), 0) AS avg_abn,
                      COALESCE(AVG(agreement), 0) AS avg_agree
               FROM analyses"""
        ).fetchone()
    return {
        "total_analyses": int(row["n"]),
        "total_beats": int(row["beats"]),
        "avg_abnormal_ratio": round(float(row["avg_abn"]), 4),
        "avg_agreement": round(float(row["avg_agree"]), 4),
    }
