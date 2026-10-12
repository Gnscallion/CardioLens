"""训练产出图表的静态服务。

**必须用白名单**。更早的 Web 版写的是 `send_from_directory(C.MODEL_DIR, filename)`，
那会把整个 `models/` 目录暴露出去，公网部署时可以直接下载到：

* `ecg_cnn.pt`      —— 模型权重
* `train_run*.log`  —— 完整训练日志（含逐轮指标与类别权重）
* `archive/`        —— 历史版本的模型与指标

`send_from_directory` 本身能防目录穿越，但"这个目录整个可读"的语义是错的。
白名单只放行界面上真正要显示的两张图。
"""
from __future__ import annotations

from flask import Blueprint, abort, send_from_directory

from src import config as C

media_bp = Blueprint("media", __name__)

# 允许对外提供的文件（相对 models/ 的路径）
ALLOWED_MEDIA = frozenset({
    "confusion_matrix.png",
    "training_curve.png",
    "archive/confusion_matrix_run2.png",
    "archive/training_curve_run2.png",
})

# 缓存一天：这些图只在重新训练时才会变
MEDIA_MAX_AGE = 24 * 60 * 60


@media_bp.get("/media/<path:filename>")
def media(filename: str):
    if filename not in ALLOWED_MEDIA:
        abort(404)
    return send_from_directory(C.MODEL_DIR, filename, max_age=MEDIA_MAX_AGE)
