"""请求守卫：限流、并发槽位、请求体类型检查。

这三件事都做成进程内状态（不上 Redis）。代价是**必须单进程多线程运行**——
用 gunicorn 开多个 worker 会让限额按 worker 数放大。这一点在 README 与
PROJECT_REPORT 的"已知安全边界"里如实写明。对一个课程演示项目而言，
引入 Redis 只为限流属于过度设计。
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from flask import abort, current_app, request

from .session import owner_of_request

# ---------------------------------------------------------------- 限流


class FixedWindowLimiter:
    """固定窗口计数器。

    比滑动窗口粗糙（窗口边界处可能放过约两倍的请求），但实现足够简单、
    可解释，且对本项目的用途（挡住脚本刷与误用）完全够用。
    """

    # 超过这个键数就清理一次过期项，防止被大量伪造标识撑爆内存
    _SWEEP_THRESHOLD = 4096

    def __init__(self) -> None:
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
            if now - start >= window:
                start, count = now, 0
            if count >= limit:
                return False
            self._hits[key] = (start, count + 1)

            if len(self._hits) > self._SWEEP_THRESHOLD:
                self._hits = {
                    k: v for k, v in self._hits.items() if now - v[0] < window
                }
            return True

    def reset(self) -> None:
        """测试用：清空计数。"""
        with self._lock:
            self._hits.clear()


_limiter = FixedWindowLimiter()


def rate_limit(bucket: str) -> None:
    """按配置对当前请求限流；超限抛 429。

    键优先用 owner（同一浏览器的所有请求合并计数）；拿不到 Cookie 时
    退化到来源 IP，避免匿名请求绕过限制。
    """
    limits = current_app.config.get("RATE_LIMITS", {})
    if bucket not in limits:
        return
    limit, window = limits[bucket]

    try:
        ident = owner_of_request()
    except Exception:                                   # noqa: BLE001 - 兜底
        ident = ""
    if not ident:
        ident = request.remote_addr or "unknown"

    if not _limiter.allow(f"{bucket}:{ident}", limit, window):
        abort(429, description="操作过于频繁，请稍后再试")


def reset_rate_limits() -> None:
    """测试用。"""
    _limiter.reset()


# ---------------------------------------------------------------- 并发槽位

# 有界信号量：同时最多允许这么多个请求进入推理。
# 推理引擎内部已有一把锁在串行化真正的计算，这里的槽位限制的是
# "排队的人有多少"，目的是过载时快速失败而不是无限堆积。
_ANALYZE_SLOTS: threading.BoundedSemaphore | None = None
_SLOTS_LOCK = threading.Lock()


def _slots() -> threading.BoundedSemaphore:
    """惰性创建信号量（需在 app 配置就绪后才知道上限）。"""
    global _ANALYZE_SLOTS
    with _SLOTS_LOCK:
        if _ANALYZE_SLOTS is None:
            size = int(current_app.config.get("MAX_CONCURRENT_ANALYSES", 4))
            _ANALYZE_SLOTS = threading.BoundedSemaphore(max(1, size))
        return _ANALYZE_SLOTS


def reset_slots() -> None:
    """测试用：让信号量按当前配置重建。"""
    global _ANALYZE_SLOTS
    with _SLOTS_LOCK:
        _ANALYZE_SLOTS = None


@contextmanager
def analysis_slot():
    """占一个分析槽位，超时则返回 503。

    用带超时的 acquire 而不是"满了就立刻拒绝"：偶尔的短排队用户是无感的，
    只有持续排队才说明真的过载。8 秒的上限依据实测——单次分析约 0.3 秒，
    即便 20 人同时点也只需等约 3 秒。
    """
    timeout = float(current_app.config.get("ANALYSIS_SLOT_TIMEOUT", 8.0))
    slots = _slots()
    if not slots.acquire(timeout=timeout):
        abort(503, description="当前分析请求较多，请稍后重试")
    try:
        yield
    finally:
        slots.release()


# ---------------------------------------------------------------- 请求体检查

ALLOWED_WRITE_TYPES = ("application/json",)


def require_json_body() -> None:
    """写接口必须带 application/json。

    这同时是一道 CSRF 防线：跨站表单只能发出
    application/x-www-form-urlencoded / multipart / text-plain，
    无法构造 application/json，因此配合 SameSite=Lax 即可挡住跨站写请求。
    """
    if request.mimetype not in ALLOWED_WRITE_TYPES:
        abort(415, description="请求体必须为 application/json")
