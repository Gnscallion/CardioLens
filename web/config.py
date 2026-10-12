"""Web 层配置：会话策略、并发上限、限流阈值、请求体上限。

所有可调参数都支持环境变量覆盖，便于在不同容量的服务器上重新标定，
而不必改代码。
"""
from __future__ import annotations

import os
import secrets
import sys
from datetime import timedelta

# 仅用于本地开发的固定密钥。生产必须通过环境变量注入，
# 见 ProdConfig 的说明。
_DEV_SECRET = "cardiolens-dev-only-not-for-production"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[配置] 环境变量 {name}={raw!r} 不是整数，改用默认值 {default}")
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"[配置] 环境变量 {name}={raw!r} 不是数字，改用默认值 {default}")
        return default


class BaseConfig:
    """开发、生产、测试三套配置的公共部分。"""

    APP_ENV = "base"

    # ---------------------------------------------------------- 会话 Cookie
    # 这个 Cookie 就是访问自己历史记录的凭据：拿到它就等于拿到那份历史。
    # 因此按凭据的标准来设——随机、HttpOnly、SameSite、生产走 Secure。
    SESSION_COOKIE_NAME = "cardiolens_sid"
    SESSION_COOKIE_HTTPONLY = True          # 禁止 JS 读取，降低 XSS 窃取风险
    SESSION_COOKIE_SAMESITE = "Lax"         # 跨站 POST 被浏览器拦下，构成 CSRF 第一道防线
    SESSION_COOKIE_PATH = "/"

    # 历史记录与本浏览器绑定，有效期给足，避免用户过段时间回来发现"记录没了"。
    PERMANENT_SESSION_LIFETIME = timedelta(days=180)

    # ---------------------------------------------------------- 请求体上限
    # 本站没有任何上传功能：请求体只有一个记录号与时间窗，不到 1 KB。
    # （注意 Flask 的 MAX_CONTENT_LENGTH 只限请求体，不限响应体——
    #   30 秒窗口的响应有约 0.16 MB，不受此限制影响。）
    MAX_CONTENT_LENGTH = 64 * 1024

    # ---------------------------------------------------------- 并发
    # 推理引擎内部已有互斥锁在串行化前向与 Grad-CAM，这里限制的是
    # "允许多少个请求同时在等这把锁"。用信号量而非无限制，是为了让
    # 持续过载时快速失败（503），而不是把请求越堆越多。
    MAX_CONCURRENT_ANALYSES = _env_int("CARDIOLENS_MAX_CONCURRENT", 4)
    # 等待槽位的上限（秒）。偶尔短排队用户无感；持续排队说明真的过载了。
    ANALYSIS_SLOT_TIMEOUT = _env_float("CARDIOLENS_SLOT_TIMEOUT", 8.0)

    # ---------------------------------------------------------- 限流
    # 形如 键 -> (次数上限, 时间窗秒数)。键在 guard.py 里选用。
    RATE_LIMITS = {
        "analyze": (20, 60.0),      # 单次约 0.3 秒，20 次/分对演示足够宽松
        "preview": (120, 60.0),     # 拖动滑块会密集触发，给宽一些
        "write": (30, 60.0),        # 保存 / 删除 / 清空
    }

    # 时间显示基准（与 src.config.TZ_NAME 保持一致）
    TZ_NAME = "Asia/Shanghai"

    # 是否开放 /api/whoami。该接口会回显访问者自己的会话标识，
    # 用途是让运维把自己浏览器的标识抄出来，交给
    # scripts/migrate_owner.py --adopt 认领遗留记录。
    # 生产环境默认关闭：它会经网络回显一份凭据，没必要长期暴露。
    ENABLE_WHOAMI = False


class DevConfig(BaseConfig):
    """本地开发：固定密钥，保证重启后历史记录仍能打开。"""

    APP_ENV = "development"
    DEBUG = False               # 不开 Werkzeug 调试器：它会执行任意代码
    SESSION_COOKIE_SECURE = False   # 本地是 http，设 True 会导致 Cookie 根本发不出去
    SECRET_KEY = os.environ.get("CARDIOLENS_SECRET_KEY") or _DEV_SECRET
    ENABLE_WHOAMI = True        # 开发时方便认领遗留记录

    @classmethod
    def warn_if_default(cls) -> None:
        if cls.SECRET_KEY == _DEV_SECRET:
            print("[配置] 正在使用开发用固定密钥。生产部署必须设置 "
                  "CARDIOLENS_SECRET_KEY，否则任何人都能伪造会话标识。")


class ProdConfig(BaseConfig):
    """生产：密钥必须由环境变量注入。

    缺失时由 load_config() 抛错（而不是在本类体里抛）：类体在模块导入时
    就会执行，那会让开发环境仅因为 import 了本模块就无法启动。
    校验要发生在"选中生产配置"这一刻。
    """

    APP_ENV = "production"
    DEBUG = False
    SESSION_COOKIE_SECURE = True    # 仅通过 HTTPS 发送；由 nginx 终止 TLS

    # 取值可能为 None，由 load_config() 负责校验。
    #
    # 为什么必须显式提供、且必须保持不变：SECRET_KEY 一旦每次启动随机生成，
    # 全体用户已签发的 Cookie 会立即全部失效——数据还在库里，但谁也打不开，
    # 而且没有任何报错。相比之下，宁可直接拒绝启动。
    SECRET_KEY = os.environ.get("CARDIOLENS_SECRET_KEY")


class TestConfig(BaseConfig):
    """自动化测试：固定密钥、关闭 Secure，并把限流阈值调小以便覆盖 429 分支。

    请求体上限**沿用 BaseConfig 的 64 KB**（不放宽）——这样 413 用例
    测的是线上真实生效的那个阈值，而不是一个只在测试里存在的数字。
    """

    APP_ENV = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SESSION_COOKIE_SECURE = False
    ENABLE_WHOAMI = True
    # 并发槽位保持默认；503 用例会临时把等待超时调小
    RATE_LIMITS = {
        "analyze": (3, 60.0),
        "preview": (5, 60.0),
        "write": (5, 60.0),
    }


CONFIGS = {
    "development": DevConfig,
    "production": ProdConfig,
    "testing": TestConfig,
}


def load_config(name: str | None = None):
    """按名称或环境变量 CARDIOLENS_ENV 选择配置类，并校验其完整性。"""
    key = (name or os.environ.get("CARDIOLENS_ENV") or "development").strip().lower()
    if key not in CONFIGS:
        print(f"[配置] 未知的环境 {key!r}，回退到 development", file=sys.stderr)
        key = "development"

    cls = CONFIGS[key]
    if not cls.SECRET_KEY:
        raise RuntimeError(
            f"环境 {key!r} 缺少 SECRET_KEY。请显式设置一个稳定的密钥：\n"
            f'  export CARDIOLENS_SECRET_KEY="{secrets.token_urlsafe(32)}"\n'
            "密钥必须保持不变，否则所有用户已保存的历史记录都会打不开。"
        )
    return cls
