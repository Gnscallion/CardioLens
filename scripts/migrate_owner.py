"""遗留历史记录的处理工具。

背景：数据库从「单用户」升级到「每会话隔离」时，老记录会被打上空的 owner
（`src.db.LEGACY_OWNER`）。这是刻意的安全默认值——任何真实会话都查不到它们，
不会出现"新用户一进来就看到别人历史"的情况。代价是这些记录在界面上不可见。

本脚本提供显式处理的入口：

    python scripts/migrate_owner.py --status            查看遗留记录与全站概况
    python scripts/migrate_owner.py --adopt <owner>     把遗留记录划归某个会话
    python scripts/migrate_owner.py --purge --yes       删除遗留记录（破坏性）

`--adopt` 需要的 owner 值怎么得到？打开站点，访问 `/api/whoami`，它只返回
你自己浏览器的标识。把那个值填进来即可。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config as C          # noqa: E402
from src import db                   # noqa: E402


def show_status() -> int:
    C.force_utf8_stdout()
    print("=" * 62)
    print(f"  数据库：{C.DB_PATH}")
    print("=" * 62)

    if not C.DB_PATH.exists():
        print("  数据库不存在。启动一次服务会自动创建。")
        return 0

    orphans = db.count_orphans()
    g = db.global_stats()

    print(f"  全站记录数        {g['total_analyses']}")
    print(f"  累计心搏数        {g['total_beats']}")
    print(f"  不同会话数        {g['distinct_owners']}")
    print(f"  其中遗留记录      {orphans}"
          f"{'（无归属，界面上不可见）' if orphans else ''}")
    print("=" * 62)

    if orphans:
        with db.connect() as conn:
            rows = conn.execute(
                """SELECT id, title, record_id, created_at
                     FROM analyses WHERE owner = ? ORDER BY id DESC LIMIT 20""",
                (db.LEGACY_OWNER,),
            ).fetchall()
        print("  遗留记录概览（最多 20 条）：")
        for r in rows:
            print(f"    #{r['id']:<5} 记录 {r['record_id']:>4}  {r['created_at']}  {r['title']}")
        print()
        print("  处理方式：")
        print("    python scripts/migrate_owner.py --adopt <owner>   划归自己")
        print("    python scripts/migrate_owner.py --purge --yes     删除")
    return 0


def adopt(owner: str) -> int:
    C.force_utf8_stdout()
    owner = owner.strip()
    if not owner:
        print("错误：owner 不能为空。")
        return 2

    n = db.adopt_orphans(owner)
    if n == 0:
        print("没有可认领的遗留记录。")
        return 0
    print(f"已把 {n} 条遗留记录划归 owner={owner[:8]}…（完整值不回显）。")
    print("刷新浏览器即可在「分析历史」里看到它们。")
    return 0


def purge(confirmed: bool) -> int:
    C.force_utf8_stdout()
    n = db.count_orphans()
    if n == 0:
        print("没有遗留记录，无需清理。")
        return 0

    if not confirmed:
        print(f"将要删除 {n} 条无归属的历史记录。这是不可逆操作。")
        print("确认请加 --yes：python scripts/migrate_owner.py --purge --yes")
        return 1

    deleted = db.purge_orphans()
    print(f"已删除 {deleted} 条遗留记录。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="处理无归属的遗留历史记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="查看遗留记录与全站概况")
    group.add_argument("--adopt", metavar="OWNER", help="把遗留记录划归指定 owner")
    group.add_argument("--purge", action="store_true", help="删除遗留记录（需 --yes）")
    parser.add_argument("--yes", action="store_true", help="对破坏性操作二次确认")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出 --status")

    args = parser.parse_args()

    if args.status:
        if args.json:
            C.force_utf8_stdout()
            print(json.dumps(db.global_stats(), ensure_ascii=False, indent=2))
            return 0
        return show_status()
    if args.adopt:
        return adopt(args.adopt)
    return purge(args.yes)


if __name__ == "__main__":
    sys.exit(main())
