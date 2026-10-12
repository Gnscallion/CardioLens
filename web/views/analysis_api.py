"""波形预览与逐搏分析接口。

两个接口都要经过并发槽位（见 guard.analysis_slot）：推理引擎内部那把锁
保证计算不会串，槽位限制的则是"同时在排队的人有多少"，过载时快速返回 503
而不是把请求无限堆积。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src import db
from src.inference import AnalysisError, get_analyzer

from ..guard import analysis_slot, rate_limit, require_json_body
from ..session import owner_of_request

analysis_bp = Blueprint("analysis_api", __name__, url_prefix="/api")

# 标题长度上限（字符）
MAX_TITLE_LEN = 120


@analysis_bp.get("/preview")
def preview():
    rate_limit("preview")
    try:
        with analysis_slot():
            result = get_analyzer().preview_window(
                request.args.get("record_id", ""),
                request.args.get("start", 0),
                request.args.get("duration", 10),
            )
    except AnalysisError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@analysis_bp.post("/analyze")
def analyze():
    require_json_body()
    rate_limit("analyze")

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "请求体必须是 JSON 对象"}), 400

    record_id = body.get("record_id")
    if not record_id:
        return jsonify({"ok": False, "error": "缺少必填参数 record_id"}), 400

    try:
        with analysis_slot():
            result = get_analyzer().analyze_window(
                record_id,
                body.get("start_sec", 0),
                body.get("duration_sec", 10),
                with_cam=bool(body.get("with_cam", True)),
            )
    except AnalysisError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    if body.get("save"):
        title = body.get("title")
        if title is not None and not isinstance(title, str):
            return jsonify({"ok": False, "error": "title 必须是字符串"}), 400
        if title and len(title) > MAX_TITLE_LEN:
            return jsonify({
                "ok": False,
                "error": f"标题过长（上限 {MAX_TITLE_LEN} 字）",
            }), 400
        # 归属当前会话。owner 不会出现在任何响应里。
        result["saved_id"] = db.save_analysis(
            result, title, owner=owner_of_request()
        )

    return jsonify({"ok": True, **result})
