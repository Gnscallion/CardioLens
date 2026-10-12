"""SPA 壳页面。

前端用 vue-router 的 history 模式，URL 与更早的版本保持一致
（`/`、`/analyze`、`/history`、`/history/12`、`/about`）。

**这里刻意不使用 catch-all 路由**。曾经的做法是注册 `/<path:path>` 兜住所有
未匹配路径并返回壳，但它会抢走本应属于路由层的判定：`GET /api/analyze`
（方法用错）会被 catch-all 接住，然后返回 404，把"方法不对"伪装成"接口不存在"，
排查时极具误导性。

现在的做法是让 Flask 正常路由，由 404 错误处理器（见 `web/errors.py`）
判断"这是一条前端路由还是一次真正的 404"，再决定返回壳还是报错。
"""
from __future__ import annotations

import json
import re

from flask import Blueprint, render_template

page_bp = Blueprint("pages", __name__)

# 前端路由白名单。只有这些路径才返回 SPA 壳并给出 200；
# 其余未知路径同样返回壳，但状态码是 404（前端渲染"页面不存在"）。
# 服务端只需要知道"哪些 URL 是合法的"，不必知道它们渲染成什么。
SPA_ROUTE_PATTERNS = (
    re.compile(r"^/$"),
    re.compile(r"^/analyze/?$"),
    re.compile(r"^/history/?$"),
    re.compile(r"^/history/\d+/?$"),
    re.compile(r"^/about/?$"),
)


def is_spa_route(path: str) -> bool:
    return any(p.match(path) for p in SPA_ROUTE_PATTERNS)


def _json_for_inline(payload: dict) -> str:
    """把数据序列化成可安全内联进 <script> 的 JSON。

    json.dumps 默认不转义 `<`，若数据里出现 `</script>` 会提前闭合脚本标签。
    这里把 `<` `>` `&` 转成 \\u 形式，顺带挡住 `<!--` 这类注释起始序列。
    """
    return (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_shell(status: int = 200):
    """渲染 SPA 壳，并把首屏数据内联进去。

    内联的好处是深链（直接打开 /analyze?record=208）不必等一次
    /api/bootstrap 往返才显示内容。
    """
    from .meta_api import build_bootstrap_payload

    payload = build_bootstrap_payload()
    html = render_template(
        "index.html",
        boot=payload,
        # 数据全部来自项目自身的常量与模型指标（不含用户输入），
        # 且 _json_for_inline 会做转义，因此这里用 |safe 输出是安全的。
        boot_json=_json_for_inline(payload),
    )
    return html, status


@page_bp.get("/")
def index():
    return render_shell()
