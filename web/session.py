"""会话标识：每个浏览器一个随机 owner，历史记录按它隔离。

设计上有三条必须记住的事实，它们同时写在文档与界面提示里：

1. **这个 Cookie 就是凭据**。拿到标识就等于拿到那份历史，所以标识本身
   是 256 位随机数，Cookie 设 HttpOnly / SameSite，生产走 Secure。
   同时：owner 永远不出现在任何 API 响应里，也不写进日志。

2. **清浏览器数据 = 失去历史入口**。记录仍在数据库中，但没有标识就找不到。
   这是产品事实，界面上要明说（见前端 SessionNotice 组件），
   而不是让用户以为"记录丢了"。不要用 localStorage 备份标识——
   那会把凭据暴露给 XSS，得不偿失。

3. **它不是一个账号**。没有密码、没有找回、不关联任何设备信息，
   不做埋点。仅用于把历史记录分组。
"""
from __future__ import annotations

import secrets

from flask import g, session

# 会话字典中存放 owner 的键
OWNER_KEY = "oid"

# 256 位。作为 bearer 凭据足够，且不可能被猜到。
TOKEN_BYTES = 32


def current_owner() -> str:
    """返回当前浏览器的标识；首次访问时签发。

    这里用的是 Flask 自带的签名 Cookie session——它本身就是 itsdangerous
    签名过的 Cookie，等价于「自签 token」但零存储、零清理任务，
    因此不再自己实现一套。
    """
    account_id = session.get('account_id')
    if account_id:
        return f'account:{account_id}'
    oid = session.get(OWNER_KEY)
    if not oid:
        oid = secrets.token_hex(TOKEN_BYTES)
        session[OWNER_KEY] = oid
        session.permanent = True        # 采用 PERMANENT_SESSION_LIFETIME 的有效期
    return oid


def bind_owner() -> None:
    """请求前把 owner 挂到 g 上，供各视图直接取用。"""
    g.owner = current_owner()


def owner_of_request() -> str:
    """取当前请求的 owner。缺 g.owner 时兜底签发，避免视图层崩。"""
    oid = getattr(g, "owner", None)
    if not oid:
        oid = current_owner()
        g.owner = oid
    return oid
