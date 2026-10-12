"""历史记录持久化：SQLite。

每次分析保存一条完整结果（含逐搏明细的 JSON），便于"历史记录"页回看与
导出。SQLite 无需额外服务，符合项目"开箱即用"的要求。

**多用户隔离**：Web 版允许多人同时使用，每个人的历史记录必须互不可见。
因此每条记录带一个 `owner` 字段（浏览器签名 Cookie 里的随机标识），
所有读写接口都**强制**按 owner 过滤。

`owner` 被设计成 keyword-only 的必填参数（而非可选默认值），是刻意的：
任何漏改的调用点会在调用瞬间抛 TypeError，而不是静默地变成跨用户越权查询。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config as C

# 迁移前遗留记录（以及一切非 Web 会话写入的行）的 owner。
# 迁移后老记录全部落到这个取值上，任何真实会话都查不到它们——
# 这是默认的安全姿态：宁可不显示，也不误把 A 的历史给 B 看。
# 需要认领时用 scripts/migrate_owner.py。
LEGACY_OWNER = ""

# owner 刻意排在 id 之后、title 之前。ALTER TABLE ADD COLUMN 只能追加到末尾，
# 那会让"新建库"与"迁移库"的列序不一致；因此迁移采用重建表的方式（见 _migrate），
# 保证两条路径产出完全相同的 schema。
SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    owner          TEXT    NOT NULL DEFAULT '',
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
"""

# 索引单独建，且在迁移之后执行：重建表时旧索引会跟随旧表被 DROP，
# 必须重新创建。
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_owner   ON analyses(owner, id DESC);
"""

# 展示与列表查询返回的列。显式列出而非 SELECT *，
# 避免新增字段（尤其是 owner 这种凭据）被顺带吐给前端。
_LIST_COLUMNS = (
    "id, title, record_id, start_sec, duration_sec, n_beats, "
    "abnormal_count, abnormal_ratio, risk_code, risk_label, "
    "agreement, mean_conf, counts_json, created_at"
)


@contextmanager
def connect():
    C.STORE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(C.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL 让读与写不再互相阻塞（多人同时看历史 + 保存新报告时不会
    # 偶发 "database is locked"）；busy_timeout 让写冲突排队等待而非立刻报错。
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> datetime:
    """当前时间（带配置时区）。写入与解析共用，保证两侧时区一致。"""
    return datetime.now(ZoneInfo(C.TZ_NAME))


def _to_epoch(text: str) -> int | None:
    """把 created_at 字符串按配置时区解析成 epoch 秒；解析失败返回 None。"""
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=ZoneInfo(C.TZ_NAME)
        )
    except (ValueError, TypeError):
        return None
    return int(dt.timestamp())


def _migrate(conn: sqlite3.Connection) -> None:
    """把旧 schema（无 owner 列）就地升级为新 schema。

    采用「重建表」而非 ALTER TABLE ADD COLUMN：后者只能把新列追加到末尾，
    会让迁移库与新建库的列序不同。本项目的数据量很小（演示场景），重建成本可忽略。
    原有数据一行不删，全部落到 LEGACY_OWNER 上。
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(analyses)")]
    if not cols or "owner" in cols:
        return                                  # 全新库或已迁移过

    conn.executescript(
        """
        ALTER TABLE analyses RENAME TO analyses_old;
        """
        + SCHEMA
        + """
        INSERT INTO analyses
            (id, owner, title, record_id, start_sec, duration_sec, n_beats,
             abnormal_count, abnormal_ratio, risk_code, risk_label, agreement,
             mean_conf, counts_json, payload_json, created_at)
        SELECT
             id, '', title, record_id, start_sec, duration_sec, n_beats,
             abnormal_count, abnormal_ratio, risk_code, risk_label, agreement,
             mean_conf, counts_json, payload_json, created_at
          FROM analyses_old;
        DROP TABLE analyses_old;
        """
    )


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.executescript(INDEXES)


# ================================================================ 写入
def save_analysis(payload: dict, title: str | None = None, *, owner: str) -> int:
    s = payload["summary"]
    default_title = (
        f"记录 {payload['record_id']} · {payload['start_sec']:.1f}s 起 "
        f"{payload['duration_sec']:.0f} 秒"
    )
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO analyses
               (owner, title, record_id, start_sec, duration_sec, n_beats,
                abnormal_count, abnormal_ratio, risk_code, risk_label, agreement,
                mean_conf, counts_json, payload_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                owner,
                (title or "").strip() or default_title,
                payload["record_id"], payload["start_sec"], payload["duration_sec"],
                s["n_beats"], s["abnormal_count"], s["abnormal_ratio"],
                s["risk_level"]["code"], s["risk_level"]["label"],
                s["agreement"], s["mean_confidence"],
                json.dumps(s["counts"], ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                _now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        return int(cur.lastrowid)


# ================================================================ 读取
def _decorate(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["counts"] = json.loads(d.pop("counts_json"))
    d["created_at_ts"] = _to_epoch(d.get("created_at", ""))
    return d


def list_analyses(limit: int = 100, *, owner: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT {_LIST_COLUMNS}
                  FROM analyses
                 WHERE owner = ?
                 ORDER BY id DESC
                 LIMIT ?""",
            (owner, int(limit)),
        ).fetchall()
    return [_decorate(r) for r in rows]


def get_analysis(analysis_id: int, *, owner: str) -> dict | None:
    """读取单条报告。不属于该 owner 时返回 None（接口层转为 404）。

    返回 None 而不是抛"无权限"，是为了不泄露"这个 id 存在"这一信息。
    """
    with connect() as conn:
        row = conn.execute(
            f"""SELECT {_LIST_COLUMNS}, payload_json
                  FROM analyses
                 WHERE id = ? AND owner = ?""",
            (int(analysis_id), owner),
        ).fetchone()
    if row is None:
        return None
    d = _decorate(row)
    d["payload"] = json.loads(d.pop("payload_json"))
    return d


# ================================================================ 删除
def delete_analysis(analysis_id: int, *, owner: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM analyses WHERE id = ? AND owner = ?",
            (int(analysis_id), owner),
        )
        return cur.rowcount > 0


def clear_all(*, owner: str) -> int:
    """只清空该 owner 自己的记录。"""
    with connect() as conn:
        cur = conn.execute("DELETE FROM analyses WHERE owner = ?", (owner,))
        return cur.rowcount


# ================================================================ 统计
def stats(*, owner: str) -> dict:
    """单个 owner 的统计。"""
    with connect() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM(n_beats), 0) AS beats,
                      COALESCE(AVG(abnormal_ratio), 0) AS avg_abn,
                      COALESCE(AVG(agreement), 0) AS avg_agree
                 FROM analyses
                WHERE owner = ?""",
            (owner,),
        ).fetchone()
    return {
        "total_analyses": int(row["n"]),
        "total_beats": int(row["beats"]),
        "avg_abnormal_ratio": round(float(row["avg_abn"]), 4),
        "avg_agreement": round(float(row["avg_agree"]), 4),
    }


def global_stats() -> dict:
    """全站聚合口径（运维用）。

    刻意只返回计数，不含任何记录内容——避免把别家数据暴露给运维接口。
    """
    with connect() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS n,
                      COUNT(DISTINCT owner) AS owners,
                      COALESCE(SUM(n_beats), 0) AS beats
                 FROM analyses"""
        ).fetchone()
        orphans = conn.execute(
            "SELECT COUNT(*) AS n FROM analyses WHERE owner = ?", (LEGACY_OWNER,)
        ).fetchone()["n"]
    return {
        "total_analyses": int(row["n"]),
        "total_beats": int(row["beats"]),
        "distinct_owners": int(row["owners"]),
        "orphan_analyses": int(orphans),
    }


# ================================================================ 遗留数据认领
def count_orphans() -> int:
    """统计没有归属的历史记录（迁移前遗留，谁都看不见）。"""
    with connect() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM analyses WHERE owner = ?", (LEGACY_OWNER,)
            ).fetchone()["n"]
        )


def adopt_orphans(owner: str) -> int:
    """把遗留记录划归指定 owner，返回认领条数。"""
    if not owner:
        raise ValueError("owner 不能为空")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE analyses SET owner = ? WHERE owner = ?", (owner, LEGACY_OWNER)
        )
        return cur.rowcount


def purge_orphans() -> int:
    """删除遗留记录，返回删除条数。破坏性操作，调用方必须二次确认。"""
    with connect() as conn:
        cur = conn.execute("DELETE FROM analyses WHERE owner = ?", (LEGACY_OWNER,))
        return cur.rowcount
