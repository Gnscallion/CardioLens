"""状态与元信息接口。"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from src import config as C
from src import db

from ..readiness import check, load_meta, load_metrics
from ..session import owner_of_request

meta_bp = Blueprint("meta_api", __name__, url_prefix="/api")


@meta_bp.get("/health")
def health():
    """探活接口：不碰数据库、不碰模型。

    与 /api/status 分开是刻意的——监控系统会高频轮询，
    如果它走 /api/status，既会触发限流，也会在数据库出问题时
    误判为整个进程已死。
    """
    return jsonify({"ok": True, "app": C.APP_NAME})


@meta_bp.get("/status")
def status():
    ready = check()
    return jsonify({
        "ok": True,
        "ready": ready.ok,
        "message": ready.message,
        "missing": ready.missing,
        "has_model": C.MODEL_PATH.exists(),
        "has_data": C.RECORD_META.exists(),
        # 统计口径是本会话的：每个人只看自己的
        "history": db.stats(owner=owner_of_request()),
    })


@meta_bp.get("/records")
def records():
    ready = check()
    if not ready.ok:
        return jsonify({"ok": False, "error": ready.message}), 503

    from src.inference import get_analyzer
    return jsonify({"ok": True, "records": get_analyzer().list_records()})


@meta_bp.get("/metrics")
def metrics():
    m = load_metrics()
    if m is None:
        return jsonify({"ok": False, "error": "模型指标不存在，请先训练模型"}), 404
    return jsonify({"ok": True, **m})


def build_bootstrap_payload() -> dict:
    """首屏所需数据的聚合体。

    被两处复用：SPA 壳在服务端渲染时内联进页面（深链不白屏），
    以及 /api/bootstrap 供前端后续刷新。
    """
    ready = check()
    meta = load_meta() or {}

    from src.inference import get_analyzer
    records = get_analyzer().list_records() if ready.ok else []

    return {
        "ok": True,
        "brand": {
            "name": C.APP_NAME,
            "name_zh": C.APP_NAME_ZH,
            "name_en": C.APP_NAME_EN,
            "tagline": C.APP_TAGLINE,
        },
        "disclaimer": C.DISCLAIMER,
        "ready": ready.ok,
        "ready_message": ready.message,
        "missing": ready.missing,
        "classes": [
            {"code": code, "name": C.CLASS_NAMES_ZH[code], "desc": C.CLASS_DESC[code]}
            for code in C.AAMI_CLASSES
        ],
        "records": records,
        "metrics": load_metrics(),
        "meta": {
            "n_records": len(meta.get("records", [])),
            "total_beats": meta.get("total_beats"),
            "class_totals": meta.get("class_totals"),
            "n_train": meta.get("n_train"),
            "n_test": meta.get("n_test"),
            "source": meta.get("source"),
        },
        "history": db.stats(owner=owner_of_request()),
    }


@meta_bp.get("/bootstrap")
def bootstrap():
    """首屏一次性拿齐所需数据，省掉 3~4 次往返。

    SPA 首屏原本要依次请求 status / records / metrics / history，
    合并成一个接口后，白屏时间明显缩短。
    """
    return jsonify(build_bootstrap_payload())


@meta_bp.get("/whoami")
def whoami():
    """回显访问者自己的会话标识。

    用途是让运维把自己浏览器的标识抄出来，交给
    `scripts/migrate_owner.py --adopt` 认领迁移前的遗留记录。
    生产环境默认关闭（见 config.ENABLE_WHOAMI）：它会把一份凭据经网络回显，
    没有必要长期暴露。
    """
    if not current_app.config.get("ENABLE_WHOAMI"):
        return jsonify({"ok": False, "error": "接口不存在"}), 404

    owner = owner_of_request()
    return jsonify({
        "ok": True,
        "owner": owner,
        "hint": "把 owner 交给 scripts/migrate_owner.py --adopt 可认领遗留记录。"
                "该值等同于访问你自己历史记录的凭据，请勿公开。",
    })
