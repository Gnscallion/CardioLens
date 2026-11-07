import secrets
import time

from flask import Blueprint, jsonify, request, session
from src import auth_db, db
from src import notifications_db
from src import mailer
import os
from ..guard import rate_limit, require_json_body

auth_bp=Blueprint('auth_api',__name__,url_prefix='/api/auth')
USER_KEY='account_id'
CAPTCHA_KEY='register_captcha'
CAPTCHA_TTL=300

@auth_bp.get('/captcha')
def captcha():
    left = secrets.randbelow(8) + 2
    right = secrets.randbelow(8) + 1
    session[CAPTCHA_KEY] = {'answer': str(left + right), 'expires_at': time.time() + CAPTCHA_TTL}
    return jsonify({'ok':True,'question':f'{left} + {right} = ?','expires_in':CAPTCHA_TTL})

@auth_bp.get('/me')
def me():
    u=auth_db.get(session[USER_KEY]) if session.get(USER_KEY) else None
    return jsonify({'ok':True,'user':u})

@auth_bp.post('/register')
def register():
    require_json_body(); rate_limit('write'); body=request.get_json(silent=True) or {}
    challenge = session.pop(CAPTCHA_KEY, None)
    captcha_answer = str(body.get('captcha','')).strip()
    if not challenge or float(challenge.get('expires_at', 0)) < time.time():
        return jsonify({'ok':False,'error':'验证码已过期，请刷新后重试'}),400
    if captcha_answer != str(challenge.get('answer')):
        return jsonify({'ok':False,'error':'验证码错误，请重新获取'}),400
    try: u=auth_db.create(str(body.get('username','')),str(body.get('password','')),str(body.get('email','')))
    except ValueError as e: return jsonify({'ok':False,'error':str(e)}),400
    session[USER_KEY]=u['id']; session.permanent=True
    notifications_db.create(u['id'], '欢迎使用 CardioLens', '账号已创建。你可以在分析页上传 ECG，并在历史页查看报告。', 'success')
    return jsonify({'ok':True,'user':u}),201

@auth_bp.post('/login')
def login():
    require_json_body(); rate_limit('write'); body=request.get_json(silent=True) or {}
    u=auth_db.authenticate(str(body.get('username','')),str(body.get('password','')))
    if not u: return jsonify({'ok':False,'error':'账号名或密码错误'}),401
    session[USER_KEY]=u['id']; session.permanent=True
    return jsonify({'ok':True,'user':u})

@auth_bp.post('/logout')
def logout():
    session.pop(USER_KEY,None)
    return jsonify({'ok':True})

@auth_bp.post('/password')
def password():
    require_json_body(); rate_limit('write')
    account_id = session.get(USER_KEY)
    if not account_id:
        return jsonify({'ok': False, 'error': '请先登录'}), 401
    body = request.get_json(silent=True) or {}
    try:
        auth_db.change_password(account_id, str(body.get('current_password', '')),
                                str(body.get('new_password', '')))
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    notifications_db.create(account_id, '密码已更新', '你的登录密码刚刚完成修改。', 'security')
    return jsonify({'ok': True})

def _dev_token_response(token, message):
    result = {'ok': True, 'message': message}
    if token and os.environ.get('CARDIOLENS_ENV', 'development').lower() != 'production':
        result['dev_token'] = token
    return result

@auth_bp.post('/password-reset/request')
def password_reset_request():
    require_json_body(); rate_limit('write')
    value = str((request.get_json(silent=True) or {}).get('username_or_email', '')).strip()
    token = auth_db.create_reset_token(value) if value else None
    if token:
        # 通过账号查询仅在服务端使用，响应仍保持“账号是否存在”不可枚举。
        with db.connect() as conn:
            row = conn.execute('SELECT email FROM accounts WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE', (value, value.lower())).fetchone()
        if row: mailer.send_link(row['email'], 'CardioLens 密码重置', '/auth?reset=1', token)
    # 生产环境应由邮件适配器投递；开发环境返回 token 便于验收，不暴露账号是否存在。
    return jsonify(_dev_token_response(token, '如果账号存在，重置链接已发送；请检查邮箱。'))

@auth_bp.post('/password-reset/confirm')
def password_reset_confirm():
    require_json_body(); rate_limit('write')
    body = request.get_json(silent=True) or {}
    try: ok = auth_db.reset_password(str(body.get('token', '')), str(body.get('new_password', '')))
    except ValueError as exc: return jsonify({'ok': False, 'error': str(exc)}), 400
    if not ok: return jsonify({'ok': False, 'error': '重置链接无效或已过期'}), 400
    return jsonify({'ok': True, 'message': '密码重置成功，请重新登录'})

@auth_bp.post('/email-verification/request')
def email_verification_request():
    rate_limit('write'); account_id = session.get(USER_KEY)
    if not account_id: return jsonify({'ok': False, 'error': '请先登录'}), 401
    token = auth_db.create_verification_token(account_id)
    u = auth_db.get(account_id)
    if token and u: mailer.send_link(u.get('email'), 'CardioLens 邮箱验证', '/auth?verify=1', token)
    return jsonify(_dev_token_response(token, '验证链接已生成，请检查邮箱。'))

@auth_bp.post('/email-verification/confirm')
def email_verification_confirm():
    require_json_body(); rate_limit('write')
    token = str((request.get_json(silent=True) or {}).get('token', ''))
    if not auth_db.verify_email(token): return jsonify({'ok': False, 'error': '验证链接无效或已过期'}), 400
    return jsonify({'ok': True, 'message': '邮箱验证成功'})
