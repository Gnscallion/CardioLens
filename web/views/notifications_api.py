from flask import Blueprint, jsonify, request, session
from src import notifications_db
from ..guard import rate_limit

notifications_bp = Blueprint('notifications_api', __name__, url_prefix='/api/notifications')

def account_id(): return session.get('account_id')

@notifications_bp.get('')
def list_notifications():
    aid = account_id()
    if not aid: return jsonify({'ok': True, 'items': [], 'unread': 0})
    return jsonify({'ok': True, 'items': notifications_db.list_for(aid), 'unread': notifications_db.unread_count(aid)})

@notifications_bp.post('/<int:notification_id>/read')
def mark_read(notification_id):
    aid = account_id()
    if not aid: return jsonify({'ok': False, 'error': '请先登录'}), 401
    rate_limit('write')
    if not notifications_db.mark_read(aid, notification_id): return jsonify({'ok': False, 'error': '通知不存在'}), 404
    return jsonify({'ok': True, 'unread': notifications_db.unread_count(aid)})

@notifications_bp.post('/read-all')
def mark_all_read():
    aid = account_id()
    if not aid: return jsonify({'ok': False, 'error': '请先登录'}), 401
    rate_limit('write')
    notifications_db.mark_all_read(aid)
    return jsonify({'ok': True, 'unread': 0})
