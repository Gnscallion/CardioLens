"""CardioLens Web 版：Flask 应用工厂。

分层：浏览器（Vue SPA）→ WSGI → 本层（会话 / 限流 / 并发门 / 蓝图）
→ src/ 推理引擎与 SQLite。

**推理引擎与界面解耦**是这次从桌面版迁移到 Web 版的基础：`src/` 中的
模型、Grad-CAM、信号处理、训练脚本一行未改，只替换了表现层。
"""
from __future__ import annotations

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import bootstrap
from .config import load_config
from .session import bind_owner


def create_app(config_object=None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    config_cls = config_object or load_config()
    if isinstance(config_cls, str):
        config_cls = load_config(config_cls)
    app.config.from_object(config_cls)

    # 接口直接返回可读中文，而不是 \uXXXX 转义
    app.json.ensure_ascii = False

    # 部署在 nginx 后面时，真实的协议与来源 IP 在 X-Forwarded-* 头里。
    # 不装这个中间件的话，SESSION_COOKIE_SECURE 会因为 Flask 以为请求是
    # http 而出问题，限流按来源 IP 退化时也会把所有人算成同一个 IP。
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.before_request
    def _attach_owner():
        # 静态资源请求不需要会话，避免给每个 js/css 都回一个 Set-Cookie
        if request.endpoint == "static":
            return
        bind_owner()

    _register_blueprints(app)
    _register_error_handlers(app)

    # 启动装配（日志、线程数、数据库、模型热身）。
    # 测试环境下跳过模型热身：它会拖慢每个用例，且用例自己会按需加载。
    if not app.config.get("TESTING"):
        bootstrap.startup(app, config_cls)

    return app


def _register_blueprints(app: Flask) -> None:
    from .views.analysis_api import analysis_bp
    from .views.history_api import history_bp
    from .views.media import media_bp
    from .views.meta_api import meta_bp
    from .views.pages import page_bp

    app.register_blueprint(meta_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(media_bp)
    # 页面蓝图带 catch-all，必须最后注册，否则会吞掉 /api/* 的 404
    app.register_blueprint(page_bp)


def _register_error_handlers(app: Flask) -> None:
    from .errors import register_error_handlers
    register_error_handlers(app)
