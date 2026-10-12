"""心电智能分析平台 —— Flask 入口。

启动：python app.py
    本机访问     http://127.0.0.1:5000
    局域网访问   http://<本机局域网IP>:5000   （同一局域网内的其他电脑）
"""
from __future__ import annotations

import json
import traceback

from flask import Flask, jsonify, render_template, request, send_from_directory

from src import config as C
from src import db
from src.inference import AnalysisError, get_analyzer

app = Flask(__name__)
app.json.ensure_ascii = False          # 接口直接返回可读中文
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024


@app.context_processor
def inject_brand():
    """把项目名称注入所有模板，模板里不再写死字面量。"""
    return {
        "app_name": C.APP_NAME,
        "app_name_zh": C.APP_NAME_ZH,
        "app_name_en": C.APP_NAME_EN,
        "app_tagline": C.APP_TAGLINE,
    }


def load_metrics() -> dict | None:
    if C.METRICS_PATH.exists():
        try:
            return json.loads(C.METRICS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def load_meta() -> dict | None:
    if C.RECORD_META.exists():
        try:
            return json.loads(C.RECORD_META.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


# ================================================================ 页面
@app.route("/")
def page_index():
    ready, ready_msg = get_analyzer().is_ready()
    return render_template(
        "index.html",
        active="home",
        ready=ready,
        ready_msg=ready_msg,
        metrics=load_metrics(),
        meta=load_meta(),
        hist=db.stats(),
        disclaimer=C.DISCLAIMER,
    )


@app.route("/analyze")
def page_analyze():
    ready, ready_msg = get_analyzer().is_ready()
    records = get_analyzer().list_records() if ready else []
    return render_template(
        "analyze.html",
        active="analyze",
        ready=ready,
        ready_msg=ready_msg,
        records=records,
        meta=load_meta(),
        disclaimer=C.DISCLAIMER,
    )


@app.route("/history")
def page_history():
    return render_template(
        "history.html",
        active="history",
        items=db.list_analyses(200),
        stats=db.stats(),
        disclaimer=C.DISCLAIMER,
    )


@app.route("/history/<int:analysis_id>")
def page_history_detail(analysis_id: int):
    item = db.get_analysis(analysis_id)
    return render_template(
        "history_detail.html",
        active="history",
        item=item,
        disclaimer=C.DISCLAIMER,
    ), (200 if item else 404)


@app.route("/about")
def page_about():
    return render_template(
        "about.html",
        active="about",
        metrics=load_metrics(),
        meta=load_meta(),
        disclaimer=C.DISCLAIMER,
    )


# ================================================================ 静态资源
@app.get("/media/<path:filename>")
def media(filename: str):
    """对外提供训练产出的图表（混淆矩阵、训练曲线等）。"""
    return send_from_directory(C.MODEL_DIR, filename)


# ================================================================ 接口
@app.get("/api/status")
def api_status():
    analyzer = get_analyzer()
    ready, msg = analyzer.is_ready()
    return jsonify({
        "ok": True, "ready": ready, "message": msg,
        "has_model": C.MODEL_PATH.exists(),
        "has_data": C.BEATS_NPZ.exists(),
        "history": db.stats(),
    })


@app.get("/api/records")
def api_records():
    analyzer = get_analyzer()
    ready, msg = analyzer.is_ready()
    if not ready:
        return jsonify({"ok": False, "error": msg}), 503
    return jsonify({"ok": True, "records": analyzer.list_records()})


@app.get("/api/preview")
def api_preview():
    try:
        result = get_analyzer().preview_window(
            request.args.get("record_id", ""),
            request.args.get("start", 0),
            request.args.get("duration", 10),
        )
        return jsonify({"ok": True, **result})
    except AnalysisError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.post("/api/analyze")
def api_analyze():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "请求体必须是 JSON 对象"}), 400

    record_id = body.get("record_id")
    if not record_id:
        return jsonify({"ok": False, "error": "缺少必填参数 record_id"}), 400

    try:
        result = get_analyzer().analyze_window(
            record_id,
            body.get("start_sec", 0),
            body.get("duration_sec", 10),
            with_cam=bool(body.get("with_cam", True)),
        )
    except AnalysisError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    saved_id = None
    if body.get("save"):
        title = body.get("title")
        if title is not None and not isinstance(title, str):
            return jsonify({"ok": False, "error": "title 必须是字符串"}), 400
        if title and len(title) > 120:
            return jsonify({"ok": False, "error": "标题过长（上限 120 字）"}), 400
        saved_id = db.save_analysis(result, title)
        result["saved_id"] = saved_id

    return jsonify({"ok": True, **result})


@app.get("/api/history")
def api_history():
    return jsonify({"ok": True, "items": db.list_analyses(200), "stats": db.stats()})


@app.get("/api/history/<int:analysis_id>")
def api_history_detail(analysis_id: int):
    item = db.get_analysis(analysis_id)
    if item is None:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    return jsonify({"ok": True, **item})


@app.delete("/api/history/<int:analysis_id>")
def api_history_delete(analysis_id: int):
    if not db.delete_analysis(analysis_id):
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    return jsonify({"ok": True, "stats": db.stats()})


@app.post("/api/history/clear")
def api_history_clear():
    n = db.clear_all()
    return jsonify({"ok": True, "deleted": n, "stats": db.stats()})


@app.get("/api/metrics")
def api_metrics():
    m = load_metrics()
    if m is None:
        return jsonify({"ok": False, "error": "模型指标不存在，请先训练模型"}), 404
    return jsonify({"ok": True, **m})


# ================================================================ 异常处理
@app.errorhandler(AnalysisError)
def handle_analysis_error(e):
    return jsonify({"ok": False, "error": str(e)}), 400


@app.errorhandler(404)
def handle_404(_e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "接口不存在"}), 404
    return render_template("error.html", code=404, message="页面不存在",
                           disclaimer=C.DISCLAIMER), 404


@app.errorhandler(413)
def handle_413(_e):
    return jsonify({"ok": False, "error": "请求体过大"}), 413


@app.errorhandler(500)
def handle_500(e):
    traceback.print_exception(type(e), e, e.__traceback__)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "服务器内部错误，请查看后端日志"}), 500
    return render_template("error.html", code=500, message="服务器内部错误",
                           disclaimer=C.DISCLAIMER), 500


def bootstrap() -> None:
    """启动前确保目录与数据库就绪，缺数据/模型时给出明确提示而不崩溃。"""
    C.force_utf8_stdout()
    db.init_db()
    analyzer = get_analyzer()
    ready, msg = analyzer.is_ready()
    print("=" * 62)
    print(f"  {C.APP_NAME}  {C.APP_NAME_ZH}")
    print(f"  {C.APP_NAME_EN}")
    print("=" * 62)
    print(f"  状态：{msg}")
    if not ready:
        print("  提示：请依次执行")
        print("        python -m src.prepare_data")
        print("        python -m src.train")
    print("  本机访问：http://127.0.0.1:5000")
    print("  局域网访问：http://<本机局域网IP>:5000")
    print("=" * 62)


if __name__ == "__main__":
    bootstrap()
    # host="0.0.0.0" 表示监听本机所有网络接口，使同一局域网内的其他电脑
    # 可通过 http://<本机局域网IP>:5000 访问；本机仍可用 127.0.0.1 访问。
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
