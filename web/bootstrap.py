"""启动装配：日志、数据库、线程数、模型热身。

顺序有讲究：日志最先（后续任何一步出问题都能记下来），数据库次之
（要跑 owner 迁移），最后才是模型热身（最慢，且失败不应阻断启动）。
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from src import config as C
from src import db

from .readiness import check

log = logging.getLogger("cardiolens")


def configure_threads() -> int:
    """限制 PyTorch 的 intra-op 线程数，避免 CPU 超订。

    默认情况下每个请求的前向计算都会拉起 `cpu_count` 个线程；几个请求并发时
    这些线程互相抢核，实测反而比单线程更慢。串行化已经由引擎内部那把锁保证了，
    因此这里把每个算子限制为单线程。
    """
    n = int(os.environ.get("CARDIOLENS_TORCH_THREADS", "1"))
    try:
        import torch
        torch.set_num_threads(max(1, n))
    except Exception as exc:                            # noqa: BLE001 - 非致命
        log.warning("设置 torch 线程数失败：%s", exc)
    return n


def setup_logging() -> None:
    """日志同时写控制台与 rolling 文件。"""
    # Windows 控制台默认 GBK，直接打印中文与符号会抛 UnicodeEncodeError
    C.force_utf8_stdout()
    C.LOG_DIR.mkdir(parents=True, exist_ok=True)

    log.setLevel(logging.INFO)
    log.propagate = False
    if log.handlers:
        return                                          # 避免重复添加

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    log.addHandler(stream)

    file_handler = RotatingFileHandler(
        C.LOG_DIR / "cardiolens.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    log.addHandler(file_handler)


def init_database() -> None:
    """建库并跑 schema 迁移。

    迁移失败不抛出：接口层会各自处理数据库异常，让服务还能提供
    "分析但不保存"的降级能力，而不是整个站点起不来。
    """
    try:
        db.init_db()
        orphans = db.count_orphans()
        if orphans:
            log.info("检测到 %d 条无归属的历史记录（迁移前遗留，界面上不可见）。"
                     "处理方式见 scripts/migrate_owner.py --status", orphans)
    except Exception as exc:                            # noqa: BLE001 - 启动兜底
        log.exception("初始化数据库失败：%s", exc)


def warmup() -> None:
    """提前把模型加载进内存。

    不预热的话，第一个访问者的分析请求要额外承担约 3 秒的
    `import torch` 与权重加载。预热失败只记日志——缺文件时
    应该在界面上如实告知（就绪检查会报出来），而不是让进程起不来。
    """
    ready = check()
    if not ready.ok:
        log.warning("就绪检查未通过：%s", ready.message)
        return
    try:
        from src.inference import get_analyzer
        get_analyzer().model                        # 触发加载
        log.info("模型加载完成")
    except Exception as exc:                            # noqa: BLE001 - 非致命
        log.exception("模型预热失败：%s", exc)


def _warn_if_exposed(host: str, app_env: str) -> None:
    """监听在所有网卡上时给出明确警告。

    **应用监听地址与公网暴露方式必须分开**：
    本应用是设计成只监听回环、由 nginx 对外提供 HTTPS 的——
    TLS 终止、静态资源直出、请求体上限、真实来源 IP 都依赖这一层。
    一旦直接监听 0.0.0.0，就等于把 Flask 的裸 HTTP 端口摆到公网上：
    没有 TLS，Cookie 的 Secure 属性形同虚设，限流也会退化成按容器/网关 IP 计数。

    默认值是 127.0.0.1，所以正常部署不会走到这里；这条日志是防"显式改错"。
    """
    if host not in ("0.0.0.0", "::", "*", ""):
        return

    if app_env == "production":
        log.warning(
            "⚠️  正在监听 %s（所有网卡）。生产环境不应这样部署：\n"
            "     · 应用将绕过反向代理直接对外，没有 TLS\n"
            "     · SESSION_COOKIE_SECURE 的 Cookie 在明文 HTTP 下无法送达\n"
            "     · 限流按来源 IP 统计时会退化（所有请求都来自网关）\n"
            "    正确做法：CARDIOLENS_HOST=127.0.0.1，由 nginx 终止 TLS 并反向代理。\n"
            "    若这确实是刻意的（如容器内由前置代理转发），请忽略本提示。",
            host,
        )
    else:
        log.info("提示：正在监听 %s（所有网卡），局域网内其他机器可访问。"
                 "生产部署请改为 127.0.0.1 + 反向代理。", host)


def startup(app, config_cls=None) -> None:
    """按顺序完成启动装配。"""
    setup_logging()
    configure_threads()

    host = os.environ.get("CARDIOLENS_HOST", "127.0.0.1")
    port = os.environ.get("CARDIOLENS_PORT", "5000")
    log.info("=" * 58)
    log.info("%s · %s", C.APP_NAME, C.APP_NAME_ZH)
    log.info("运行环境：%s    数据目录：%s", app.config.get("APP_ENV"), C.STORE_DIR)
    log.info("监听：http://%s:%s", host, port)
    log.info("=" * 58)

    _warn_if_exposed(host, app.config.get("APP_ENV"))

    # 延迟到日志就绪后再报告配置问题，保证警告一定被记下来
    warn = getattr(config_cls, "warn_if_default", None)
    if callable(warn):
        warn()

    init_database()
    warmup()
