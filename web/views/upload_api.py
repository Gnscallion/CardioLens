from __future__ import annotations
from flask import Blueprint, jsonify, request
import numpy as np
from src.signal_quality import parse_signal, assess
from src.inference import AnalysisError, get_analyzer
from ..guard import rate_limit

upload_bp = Blueprint('upload_api', __name__, url_prefix='/api')
MAX_BYTES = 5 * 1024 * 1024

@upload_bp.post('/upload-ecg')
def upload_ecg():
    rate_limit('preview')
    f = request.files.get('file')
    if not f: return jsonify({'ok': False, 'error': '请选择 CSV 或 TXT 格式的 ECG 文件'}), 400
    raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: return jsonify({'ok': False, 'error': '文件不能超过 5 MB'}), 413
    try:
        signal = parse_signal(raw); quality = assess(signal)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    # 仅返回受限预览数据，避免把上传内容无限制回显；后续模型适配可复用此结果。
    quality['preview'] = np.round(signal[:min(len(signal), 3600)], 5).tolist()
    return jsonify({'ok': True, 'filename': f.filename, **quality})

@upload_bp.post('/upload-ecg/analyze')
def analyze_uploaded_ecg():
    rate_limit('analyze')
    f = request.files.get('file')
    if not f: return jsonify({'ok': False, 'error': '请选择 ECG 文件'}), 400
    raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: return jsonify({'ok': False, 'error': '文件不能超过 5 MB'}), 413
    try:
        signal = parse_signal(raw)
        quality = assess(signal)
        result = get_analyzer().analyze_uploaded_signal(signal, with_cam=False)
    except (ValueError, AnalysisError) as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    return jsonify({'ok': True, 'filename': f.filename, 'quality': quality, **result})
