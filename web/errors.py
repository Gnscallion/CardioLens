"""统一错误处理。

两条原则：

1. **`/api/*` 一律返回 JSON**，页面路由返回 SPA 壳或错误页。
   前端拿到一份 HTML 去 `JSON.parse` 会产生误导性的报错，排查成本很高。
2. **用户永远看不到 traceback**。完整堆栈写日志，响应里只有一句中文说明。
"""
from __future__ import annotations

from flask import jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from src.inference import AnalysisError

from .bootstrap import log

# 这些前缀下的 404 必须返回 JSON 而不是 SPA 页面
_API_PREFIXES = ("/api/", "/media/")

# 未显式给出 description 时使用的中文文案。
# Werkzeug 对每个状态码都带一段英文默认说明，直接透给用户既不友好，
# 也和其余中文界面不一致。判断方式见 _is_default_description。
CODE_MESSAGES = {
    400: "请求参数有误",
    403: "没有访问权限",
    404: "请求的资源不存在",
    405: "请求方法不被支持",
    408: "请求超时",
    413: "请求体过大",
    415: "请求体格式不被支持",
    429: "操作过于频繁，请稍后再试",
    500: "服务器内部错误，请稍后重试",
    503: "服务暂时不可用，请稍后重试",
}


def _is_default_description(exc: HTTPException) -> bool:
    """判断错误描述是不是 Werkzeug 自带的英文默认值。

    用 abort(429, description="...") 显式设置过的描述会与类属性不同，
    应当原样透出（那些都是我们自己写的中文）。
    """
    return exc.description == getattr(type(exc), "description", None)


def _wants_json() -> bool:
    return any(request.path.startswith(p) for p in _API_PREFIXES)


def _error(message: str, status: int):
    """按请求路径选择 JSON 或 HTML 错误响应。"""
    if _wants_json():
        return jsonify({"ok": False, "error": message}), status
    return render_template("error.html", code=status, message=message), status


def register_error_handlers(app) -> None:
    @app.errorhandler(AnalysisError)
    def _analysis_error(exc: AnalysisError):
        """推理层的输入校验失败——这是正常的业务错误，返回 400。"""
        return jsonify({"ok": False, "error": str(exc)}), 400

    @app.errorhandler(404)
    def _not_found(exc):
        """404 有三条出路：接口报 JSON、静态资源干脆 404、前端路由返回壳。

        SPA 使用 history 模式，合法前端路由（/analyze、/history/12 等）
        在服务端并不存在对应的视图，必须由这里返回壳交给前端渲染。
        但状态码要如实：只有白名单里的路径才给 200，其余给 404，
        避免搜索引擎与用户把不存在的页面当成正常页面。
        """
        from .views.pages import is_spa_route, render_shell

        if _wants_json():
            return _error(CODE_MESSAGES[404], 404)
        if request.path.startswith("/static/"):
            # 缺失的 js/css 直接 404，塞一份 HTML 进去会让浏览器报语法错误
            return "", 404
        if is_spa_route(request.path):
            return render_shell(200)
        return render_shell(404)

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        status = exc.code or 500
        if _is_default_description(exc):
            message = CODE_MESSAGES.get(status, exc.name or "请求失败")
        else:
            message = exc.description or CODE_MESSAGES.get(status, "请求失败")
        return _error(message, status)

    @app.errorhandler(413)
    def _too_large(_exc):
        limit = (app.config.get("UPLOAD_MAX_CONTENT_LENGTH", 0)
                 if request.path in {"/api/upload-ecg", "/api/upload-ecg/analyze"}
                 else app.config.get("MAX_CONTENT_LENGTH", 0))
        limit_kb = limit // 1024
        suffix = " MB" if limit_kb >= 1024 else " KB"
        display = limit_kb // 1024 if limit_kb >= 1024 else limit_kb
        return _error(f"请求体过大（上限 {display}{suffix}）", 413)

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        """兜底：记完整堆栈，只给用户一句中文。"""
        log.exception("未捕获异常：%s %s", request.method, request.path)
        return _error(CODE_MESSAGES[500], 500)
