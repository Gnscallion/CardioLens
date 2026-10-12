"""历史记录接口。

**每一条查询都按 owner 过滤**，这是多用户隔离的落点。
访问不属于自己的记录一律返回 404 而不是 403——403 会泄露"这个 id 存在"
这一信息，让人可以探测别的会话有多少条记录。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src import db

from ..guard import rate_limit, require_json_body
from ..session import owner_of_request

history_bp = Blueprint("history_api", __name__, url_prefix="/api")

# 列表返回条数上限
MAX_LIST = 200


@history_bp.get("/history")
def history_list():
    owner = owner_of_request()
    return jsonify({
        "ok": True,
        "items": db.list_analyses(MAX_LIST, owner=owner),
        "stats": db.stats(owner=owner),
    })


@history_bp.get("/history/<int:analysis_id>")
def history_detail(analysis_id: int):
    item = db.get_analysis(analysis_id, owner=owner_of_request())
    if item is None:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    return jsonify({"ok": True, **item})


@history_bp.delete("/history/<int:analysis_id>")
def history_delete(analysis_id: int):
    rate_limit("write")
    owner = owner_of_request()
    if not db.delete_analysis(analysis_id, owner=owner):
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    return jsonify({"ok": True, "stats": db.stats(owner=owner)})


@history_bp.post("/history/clear")
def history_clear():
    require_json_body()
    rate_limit("write")
    owner = owner_of_request()
    # 只清自己的；别人的记录一条都不动
    deleted = db.clear_all(owner=owner)
    return jsonify({"ok": True, "deleted": deleted, "stats": db.stats(owner=owner)})
