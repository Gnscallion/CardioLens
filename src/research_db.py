"""科研实验数据库：复用项目 SQLite，保存实验配置、状态与真实指标。"""
from __future__ import annotations

import json
from datetime import datetime
from . import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS research_experiments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner TEXT NOT NULL,
  name TEXT NOT NULL,
  config_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'planned',
  metrics_json TEXT,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_owner ON research_experiments(owner, id DESC);
CREATE TABLE IF NOT EXISTS research_jobs (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  experiment_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_jobs_owner ON research_jobs(owner, created_at DESC);
"""

def init_db() -> None:
    with db.connect() as conn:
        conn.executescript(SCHEMA)

def create(name: str, config: dict, *, owner: str) -> int:
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with db.connect() as conn:
        cur = conn.execute("""INSERT INTO research_experiments
          (owner,name,config_json,status,created_at,updated_at) VALUES (?,?,?,?,?,?)""",
          (owner, name.strip() or '未命名实验', json.dumps(config, ensure_ascii=False), 'planned', now, now))
        return int(cur.lastrowid)

def list_all(*, owner: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM research_experiments WHERE owner=? ORDER BY id DESC", (owner,)).fetchall()
    return [_row(r) for r in rows]

def get(experiment_id: int, *, owner: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM research_experiments WHERE id=? AND owner=?", (experiment_id, owner)).fetchone()
    return _row(row) if row else None

def update_metrics(experiment_id: int, metrics: dict, status: str = 'completed', *, owner: str) -> bool:
    with db.connect() as conn:
        cur = conn.execute("UPDATE research_experiments SET metrics_json=?,status=?,updated_at=? WHERE id=? AND owner=?",
          (json.dumps(metrics, ensure_ascii=False), status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), experiment_id, owner))
        return cur.rowcount > 0

def _row(row) -> dict:
    d = dict(row)
    d['config'] = json.loads(d.pop('config_json'))
    d['metrics'] = json.loads(d.pop('metrics_json')) if d.get('metrics_json') else None
    d.pop('owner', None)
    return d

def create_job(job_id, experiment_id, owner):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with db.connect() as conn:
        conn.execute('INSERT INTO research_jobs(id,owner,experiment_id,status,created_at,updated_at) VALUES (?,?,?,?,?,?)', (job_id, owner, experiment_id, 'queued', now, now))

def update_job(job_id, status, progress=0, error=''):
    with db.connect() as conn:
        conn.execute('UPDATE research_jobs SET status=?,progress=?,error=?,updated_at=? WHERE id=?', (status, int(progress), error, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), job_id))

def get_job(job_id, owner):
    with db.connect() as conn:
        row = conn.execute('SELECT id,experiment_id,status,progress,error,created_at,updated_at FROM research_jobs WHERE id=? AND owner=?', (job_id, owner)).fetchone()
    return dict(row) if row else None
