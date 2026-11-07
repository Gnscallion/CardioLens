"""持久化系统通知，按账号隔离并支持已读状态。"""
from __future__ import annotations
from datetime import datetime
from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 account_id INTEGER NOT NULL,
 title TEXT NOT NULL,
 body TEXT NOT NULL,
 kind TEXT NOT NULL DEFAULT 'info',
 is_read INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_account ON notifications(account_id, is_read, id DESC);
"""

def init_db():
    with db.connect() as conn: conn.executescript(SCHEMA)

def create(account_id, title, body, kind='info'):
    with db.connect() as conn:
        cur = conn.execute('INSERT INTO notifications(account_id,title,body,kind,created_at) VALUES (?,?,?,?,?)', (account_id, title, body, kind, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        return int(cur.lastrowid)

def list_for(account_id, limit=50):
    with db.connect() as conn:
        rows = conn.execute('SELECT id,title,body,kind,is_read,created_at FROM notifications WHERE account_id=? ORDER BY id DESC LIMIT ?', (account_id, int(limit))).fetchall()
    return [dict(r) for r in rows]

def unread_count(account_id):
    with db.connect() as conn:
        return int(conn.execute('SELECT COUNT(*) AS n FROM notifications WHERE account_id=? AND is_read=0', (account_id,)).fetchone()['n'])

def mark_read(account_id, notification_id):
    with db.connect() as conn:
        cur = conn.execute('UPDATE notifications SET is_read=1 WHERE id=? AND account_id=?', (notification_id, account_id))
        return cur.rowcount > 0

def mark_all_read(account_id):
    with db.connect() as conn:
        cur = conn.execute('UPDATE notifications SET is_read=1 WHERE account_id=? AND is_read=0', (account_id,))
        return cur.rowcount
