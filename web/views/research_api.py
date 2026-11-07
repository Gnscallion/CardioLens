from __future__ import annotations
from flask import Blueprint, jsonify, request
import math
import statistics
import uuid
from concurrent.futures import ThreadPoolExecutor
from src import research_db
from ..guard import rate_limit, require_json_body
from ..session import owner_of_request

research_bp = Blueprint('research_api', __name__, url_prefix='/api/research')
_JOBS = ThreadPoolExecutor(max_workers=2, thread_name_prefix='cardiolens-research')

def _calibration(beats):
    labeled = [b for b in beats if b.get('expert') in {'N','S','V','F','Q'} and isinstance(b.get('probs'), dict)]
    if not labeled: return {'available': False, 'reason': '当前窗口没有专家标注'}
    conf = [float(b.get('confidence', 0)) for b in labeled]
    correct = [1.0 if b.get('pred') == b.get('expert') else 0.0 for b in labeled]
    ece = 0.0; bins=[]
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        selected = [j for j,c in enumerate(conf) if lo <= c < hi or (i == 9 and c <= hi)]
        if not selected: continue
        acc = sum(correct[j] for j in selected) / len(selected)
        avg = sum(conf[j] for j in selected) / len(selected)
        ece += len(selected) / len(labeled) * abs(avg - acc)
        bins.append({'bin': f'{lo:.1f}-{hi:.1f}', 'count': len(selected), 'confidence': round(avg, 4), 'accuracy': round(acc, 4)})
    brier = sum(sum((float(b.get('probs', {}).get(k, 0)) - (1.0 if k == b.get('expert') else 0.0)) ** 2 for k in ('N','S','V','F','Q')) for b in labeled) / len(labeled)
    return {'available': True, 'n_labeled': len(labeled), 'accuracy': round(sum(correct) / len(correct), 4), 'ece': round(ece, 4), 'brier_score': round(brier, 4), 'bins': bins}

def _run_job(job_id, experiment_id, owner):
    try:
        research_db.update_job(job_id, 'running', 5)
        item = research_db.get(experiment_id, owner=owner)
        from src.inference import get_analyzer
        analyzer = get_analyzer(); configured = item['config'].get('record_ids') or []
        records = analyzer.list_records(); ids = (configured or [r['id'] for r in records if r.get('recommended')][:3])[:5]
        confidences=[]; all_beats=[]; abnormal=total=0; completed=[]
        for index, record_id in enumerate(ids, 1):
            result = analyzer.analyze_window(record_id, 0, 3, with_cam=False)
            beats = result.get('beats', []); all_beats.extend(beats)
            confidences.extend(float(b.get('confidence', 0)) for b in beats)
            abnormal += int(result.get('summary', {}).get('abnormal_count', 0)); total += len(beats); completed.append(record_id)
            research_db.update_job(job_id, 'running', int(5 + 80 * index / max(len(ids), 1)))
        mean_conf = statistics.fmean(confidences) if confidences else 0.0
        sd = statistics.pstdev(confidences) if len(confidences)>1 else 0.0
        threshold = float(item['config'].get('threshold', .65))
        metrics={'records':completed,'n_records':len(completed),'n_beats':total,'abnormal_count':abnormal,'abnormal_ratio':round(abnormal/total,4) if total else 0,'mean_confidence':round(mean_conf,4),'confidence_std':round(sd,4),'confidence_95_ci':round(1.96*sd/math.sqrt(len(confidences)),4) if confidences else 0,'low_confidence_count':sum(c<threshold for c in confidences),'calibration':_calibration(all_beats)}
        research_db.update_metrics(experiment_id, metrics, 'completed', owner=owner); research_db.update_job(job_id, 'completed', 100)
    except Exception:
        research_db.update_metrics(experiment_id, {'error':'模型或数据未就绪'}, 'failed', owner=owner)
        research_db.update_job(job_id, 'failed', 100, '实验运行失败，请检查模型和数据是否就绪')

@research_bp.get('/experiments')
def experiments():
    return jsonify({'ok': True, 'items': research_db.list_all(owner=owner_of_request())})

@research_bp.post('/experiments')
def create_experiment():
    require_json_body(); rate_limit('write')
    body = request.get_json(silent=True) or {}
    eid = research_db.create(body.get('name', ''), body.get('config', {}), owner=owner_of_request())
    return jsonify({'ok': True, 'id': eid}), 201

@research_bp.get('/experiments/<int:experiment_id>')
def experiment_detail(experiment_id):
    item = research_db.get(experiment_id, owner=owner_of_request())
    if item is None:
        return jsonify({'ok': False, 'error': '实验不存在'}), 404
    return jsonify({'ok': True, **item})

@research_bp.post('/experiments/<int:experiment_id>/metrics')
def save_metrics(experiment_id):
    require_json_body(); rate_limit('write')
    body = request.get_json(silent=True) or {}
    if not research_db.update_metrics(experiment_id, body.get('metrics', {}), body.get('status', 'completed'), owner=owner_of_request()):
        return jsonify({'ok': False, 'error': '实验不存在'}), 404
    return jsonify({'ok': True})

@research_bp.post('/experiments/<int:experiment_id>/run')
def run_experiment(experiment_id):
    owner = owner_of_request()
    item = research_db.get(experiment_id, owner=owner)
    if item is None:
        return jsonify({'ok': False, 'error': '实验不存在'}), 404
    job_id = uuid.uuid4().hex
    research_db.create_job(job_id, experiment_id, owner)
    _JOBS.submit(_run_job, job_id, experiment_id, owner)
    return jsonify({'ok': True, 'status': 'queued', 'job_id': job_id}), 202

@research_bp.get('/jobs/<job_id>')
def research_job(job_id):
    item = research_db.get_job(job_id, owner_of_request())
    if not item: return jsonify({'ok': False, 'error': '任务不存在'}), 404
    return jsonify({'ok': True, **item})
