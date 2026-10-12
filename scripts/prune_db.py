"""历史记录清理工具：控制 SQLite 文件的增长。

一个 30 秒窗口的报告约 0.16 MB（含整段波形与逐搏 Grad-CAM）。若不清理，
100 个会话各存 20 条就会让数据库涨到约 320 MB。本脚本提供两种清理口径：

    python scripts/prune_db.py --status                    查看各会话占用
    python scripts/prune_db.py --keep 50                   每会话只保留最近 50 条
    python scripts/prune_db.py --before 2026-01-01 --yes   删除该日期之前的记录
    python scripts/prune_db.py --owner <owner> --keep 10   只处理某个会话

`--before` 是破坏性操作，需要 --yes 二次确认；`--keep` 会先打印将要删除的
条数并要求确认，除非同时给出 --yes。建议定期执行，或做成 cron / 计划任务。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config as C          # noqa: E402
from src import db                   # noqa: E402


def _db_size() -> str:
    if not C.DB_PATH.exists():
        return "（不存在）"
    n = C.DB_PATH.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def show_status() -> int:
    C.force_utf8_stdout()
    print("=" * 62)
    print(f"  数据库：{C.DB_PATH}")
    print(f"  文件大小：{_db_size()}")
    print("=" * 62)

    if not C.DB_PATH.exists():
        print("  数据库不存在。启动一次服务会自动创建。")
        return 0

    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM analyses").fetchone()["n"]
        rows = conn.execute(
            """SELECT owner,
                      COUNT(*)          AS n,
                      SUM(LENGTH(payload_json)) AS bytes
                 FROM analyses
               GROUP BY owner
               ORDER BY n DESC"""
        ).fetchall()

    print(f"  记录总数：{total}")
    print()
    print(f"  {'会话（前 8 位）':<18}{'条数':>6}{'占用':>12}")
    print("  " + "-" * 34)
    for r in rows:
        label = (r["owner"][:8] + "…") if r["owner"] else "（无归属）"
        mb = (r["bytes"] or 0) / 1024 / 1024
        print(f"  {label:<18}{r['n']:>6}{mb:>10.1f} MB")
    print("=" * 62)
    print("  清理：--keep N 每会话保留最近 N 条 / --before YYYY-MM-DD 按时间删")
    return 0


def _count_before(cutoff: str, owner: str | None) -> int:
    sql = "SELECT COUNT(*) AS n FROM analyses WHERE created_at < ?"
    params: list = [cutoff]
    if owner is not None:
        sql += " AND owner = ?"
        params.append(owner)
    with db.connect() as conn:
        return int(conn.execute(sql, params).fetchone()["n"])


def prune_before(cutoff: str, owner: str | None, confirmed: bool) -> int:
    C.force_utf8_stdout()
    try:
        datetime.strptime(cutoff, "%Y-%m-%d")
    except ValueError:
        print(f"错误：日期格式应为 YYYY-MM-DD，收到 {cutoff!r}")
        return 2

    n = _count_before(cutoff, owner)
    if n == 0:
        print(f"没有早于 {cutoff} 的记录，无需清理。")
        return 0

    if not confirmed:
        print(f"将要删除 {n} 条早于 {cutoff} 的历史记录。这是不可逆操作。")
        print("确认请加 --yes。")
        return 1

    sql = "DELETE FROM analyses WHERE created_at < ?"
    params: list = [cutoff]
    if owner is not None:
        sql += " AND owner = ?"
        params.append(owner)
    with db.connect() as conn:
        cur = conn.execute(sql, params)
        deleted = cur.rowcount
    print(f"已删除 {deleted} 条记录。当前文件大小：{_db_size()}")
    return 0


def prune_keep(keep: int, owner: str | None, confirmed: bool) -> int:
    C.force_utf8_stdout()
    if keep < 0:
        print("错误：--keep 不能为负数。")
        return 2

    with db.connect() as conn:
        if owner is None:
            owners = [
                r["owner"] for r in conn.execute(
                    "SELECT DISTINCT owner FROM analyses"
                ).fetchall()
            ]
        else:
            owners = [owner]

        victims: list[int] = []
        for oid in owners:
            # 每个会话保留 id 最大的 keep 条（id 单调递增，等价于最近 keep 条）
            ids = [
                r["id"] for r in conn.execute(
                    """SELECT id FROM analyses WHERE owner = ?
                        ORDER BY id DESC LIMIT -1 OFFSET ?""",
                    (oid, keep),
                ).fetchall()
            ]
            victims.extend(ids)

        if not victims:
            print(f"每个会话都不超过 {keep} 条，无需清理。")
            return 0

        if not confirmed:
            print(f"将要删除 {len(victims)} 条记录（每个会话只保留最近 {keep} 条）。"
                  "这是不可逆操作。")
            print("确认请加 --yes。")
            return 1

        conn.executemany("DELETE FROM analyses WHERE id = ?", [(i,) for i in victims])

    print(f"已删除 {len(victims)} 条记录。当前文件大小：{_db_size()}")
    print("提示：SQLite 删除后文件不会自动缩小，可执行 VACUUM 回收空间。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="历史记录清理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="查看各会话占用情况")
    group.add_argument("--keep", type=int, metavar="N", help="每会话只保留最近 N 条")
    group.add_argument("--before", metavar="YYYY-MM-DD", help="删除该日期之前的记录")
    parser.add_argument("--owner", help="只处理指定的 owner（默认处理全部会话）")
    parser.add_argument("--yes", action="store_true", help="对破坏性操作二次确认")

    args = parser.parse_args()

    if args.status:
        return show_status()
    if args.keep is not None:
        return prune_keep(args.keep, args.owner, args.yes)
    return prune_before(args.before, args.owner, args.yes)


if __name__ == "__main__":
    sys.exit(main())
