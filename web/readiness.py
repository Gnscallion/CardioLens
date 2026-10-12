"""就绪检查与只读资源加载。

**为什么不用 `analyzer.is_ready()`**：它要求 `data/processed/beats.npz` 存在，
那是约 91 MB 的训练样本集（训练才需要）。而推理链路实际只读
`signals/` + `annots/` + `record_meta.json` + 模型权重。

如果沿用 `is_ready()`，服务器上只部署运行最小集（约 115 MB，不含 beats.npz）时，
`/api/status` 会返回 not ready、`/api/records` 直接 503 —— 整个应用看起来彻底坏掉，
而给出的提示还是让运维去跑一个根本不该在服务器上跑的脚本。

桌面版早就发现了这一点（`resource_service.check_readiness()` 的注释写明
"刻意不检查 beats.npz"），Web 版沿用同样的口径。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from src import config as C


@dataclass
class Readiness:
    ok: bool
    message: str
    missing: list[str] = field(default_factory=list)


def check() -> Readiness:
    """检查推理链路所需的全部文件是否齐备。"""
    missing: list[str] = []

    if not C.RECORD_META.exists():
        missing.append("data/processed/record_meta.json")
    if not C.SIGNAL_DIR.is_dir():
        missing.append("data/processed/signals/")
    if not (C.DATA_PROCESSED / "annots").is_dir():
        missing.append("data/processed/annots/")
    if not C.MODEL_PATH.exists():
        missing.append("models/ecg_cnn.pt")

    if missing:
        return Readiness(False, "缺少：" + "、".join(missing), missing)
    return Readiness(True, "就绪", [])


def _load_json(path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_metrics() -> dict | None:
    """测试集指标（models/metrics.json）。"""
    return _load_json(C.METRICS_PATH)


def load_meta() -> dict | None:
    """数据集元信息（data/processed/record_meta.json）。"""
    return _load_json(C.RECORD_META)
