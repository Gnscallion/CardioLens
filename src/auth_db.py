from __future__ import annotations
import re
import secrets
import hashlib
from datetime import timedelta
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from . import db

SCHEMA = """CREATE TABLE IF NOT EXISTS accounts (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL,
 email TEXT,
 email_verified INTEGER NOT NULL DEFAULT 0,
 verification_token_hash TEXT,
 verification_expires_at TEXT,
 reset_token_hash TEXT,
 reset_expires_at TEXT,
 created_at TEXT NOT NULL,
 last_login TEXT
);"""

def init_db():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(accounts)')}
        additions = {
            'email': 'TEXT', 'email_verified': 'INTEGER NOT NULL DEFAULT 0',
            'verification_token_hash': 'TEXT', 'verification_expires_at': 'TEXT',
            'reset_token_hash': 'TEXT', 'reset_expires_at': 'TEXT',
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f'ALTER TABLE accounts ADD COLUMN {name} {definition}')

def create(username, password, email=''):
    username = username.strip()
    if not re.fullmatch(r'[A-Za-z0-9_\-\u4e00-\u9fff]{3,32}', username): raise ValueError('账号名需为 3-32 位字母、数字、下划线、短横线或中文')
    if len(password) < 8: raise ValueError('密码至少需要 8 位')
    try:
        with db.connect() as conn:
            email = email.strip().lower() or None
            if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
                raise ValueError('邮箱格式不正确')
            cur=conn.execute('INSERT INTO accounts(username,password_hash,email,created_at) VALUES (?,?,?,?)',(username,generate_password_hash(password),email,datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            return {'id':int(cur.lastrowid),'username':username,'email':email,'email_verified':False}
    except Exception as e:
        if 'UNIQUE' in str(e).upper(): raise ValueError('账号名已存在，请更换一个账号名')
        raise

def authenticate(username,password):
    with db.connect() as conn: row=conn.execute('SELECT * FROM accounts WHERE username=? COLLATE NOCASE',(username.strip(),)).fetchone()
    if not row or not check_password_hash(row['password_hash'],password): return None
    with db.connect() as conn: conn.execute('UPDATE accounts SET last_login=? WHERE id=?',(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),row['id']))
    return {'id':row['id'],'username':row['username']}

def change_password(account_id, current_password, new_password):
    if len(new_password) < 8:
        raise ValueError('新密码至少需要 8 位')
    with db.connect() as conn:
        row = conn.execute('SELECT password_hash FROM accounts WHERE id=?', (account_id,)).fetchone()
        if not row or not check_password_hash(row['password_hash'], current_password):
            raise ValueError('当前密码错误')
        conn.execute('UPDATE accounts SET password_hash=? WHERE id=?',
                     (generate_password_hash(new_password), account_id))

def _token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def create_reset_token(username_or_email, ttl_minutes=30):
    with db.connect() as conn:
        row = conn.execute('SELECT id FROM accounts WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE', (username_or_email.strip(), username_or_email.strip().lower())).fetchone()
        if not row: return None
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(minutes=ttl_minutes)).isoformat()
        conn.execute('UPDATE accounts SET reset_token_hash=?, reset_expires_at=? WHERE id=?', (_token_hash(token), expires, row['id']))
        return token

def reset_password(token, new_password):
    if len(new_password) < 8: raise ValueError('新密码至少需要 8 位')
    with db.connect() as conn:
        row = conn.execute('SELECT id FROM accounts WHERE reset_token_hash=? AND reset_expires_at>?', (_token_hash(token), datetime.now().isoformat())).fetchone()
        if not row: return False
        conn.execute('UPDATE accounts SET password_hash=?, reset_token_hash=NULL, reset_expires_at=NULL WHERE id=?', (generate_password_hash(new_password), row['id']))
        return True

def create_verification_token(account_id, ttl_minutes=30):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(minutes=ttl_minutes)).isoformat()
    with db.connect() as conn:
        row = conn.execute('SELECT email FROM accounts WHERE id=?', (account_id,)).fetchone()
        if not row or not row['email']: return None
        conn.execute('UPDATE accounts SET verification_token_hash=?, verification_expires_at=? WHERE id=?', (_token_hash(token), expires, account_id))
    return token

def verify_email(token):
    with db.connect() as conn:
        row = conn.execute('SELECT id FROM accounts WHERE verification_token_hash=? AND verification_expires_at>?', (_token_hash(token), datetime.now().isoformat())).fetchone()
        if not row: return False
        conn.execute('UPDATE accounts SET email_verified=1, verification_token_hash=NULL, verification_expires_at=NULL WHERE id=?', (row['id'],))
        return True

def get(account_id):
    with db.connect() as conn: row=conn.execute('SELECT id,username,email,email_verified,created_at,last_login FROM accounts WHERE id=?',(account_id,)).fetchone()
    return dict(row) if row else None
