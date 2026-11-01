import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextvars import ContextVar

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('QUANT_WORKBENCH_DATA', Path(os.environ.get('QUANT_SANDBOX_DATA_DIR', ROOT / 'data')) / 'workbench'))
VERSION = '3.1.0'
_scope_data = ContextVar('workbench_data', default=None)

def data_path():
    return _scope_data.get() or DATA

def now():
    return datetime.now(timezone.utc).isoformat()

def encode(x):
    return json.dumps(x, ensure_ascii=False, allow_nan=False, sort_keys=True)

def db():
    selected = data_path()
    selected.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(selected / 'workbench.sqlite', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, key TEXT, fetched TEXT, payload TEXT);
    CREATE INDEX IF NOT EXISTS by_key ON snapshots(key,fetched);
    CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created TEXT, payload TEXT);
    CREATE TABLE IF NOT EXISTS profiles(symbol TEXT PRIMARY KEY, payload TEXT);
    CREATE TABLE IF NOT EXISTS events(created TEXT, kind TEXT, message TEXT);
    ''')
    return c

def snapshot(key, payload):
    payload = {**payload, 'fetched_at': now(), 'version': VERSION}
    sid = hashlib.sha256(encode(payload).encode()).hexdigest()[:20]
    payload['id'] = sid
    with db() as c:
        c.execute('INSERT INTO snapshots VALUES(?,?,?,?)', (sid,key,payload['fetched_at'],encode(payload)))
    return payload

def latest(key):
    with db() as c:
        r = c.execute('SELECT payload FROM snapshots WHERE key=? ORDER BY fetched DESC LIMIT 1',(key,)).fetchone()
    return json.loads(r[0]) if r else None

def latest_prefix(prefix):
    with db() as c:
        rows=c.execute('SELECT payload FROM snapshots s WHERE key LIKE ? AND fetched=(SELECT MAX(fetched) FROM snapshots t WHERE t.key=s.key)',(prefix+'%',)).fetchall()
    return [json.loads(r[0]) for r in rows]

def get_snapshot(sid):
    with db() as c:
        r = c.execute('SELECT payload FROM snapshots WHERE id=?',(sid,)).fetchone()
    if not r: raise ValueError('找不到数据快照')
    return json.loads(r[0])

def get_snapshots(ids):
    found={}
    with db() as c:
        for i in range(0,len(ids),900):
            batch=ids[i:i+900]
            if not batch:continue
            rows=c.execute('SELECT id,payload FROM snapshots WHERE id IN ('+','.join('?' for _ in batch)+')',batch).fetchall()
            found.update({r['id']:json.loads(r['payload']) for r in rows})
    if any(s not in found for s in ids):raise ValueError('找不到数据快照')
    return [found[s] for s in ids]

def catalog():
    with db() as c:
        rows = c.execute("SELECT payload FROM snapshots s WHERE key NOT GLOB 'etf_cache:*' AND fetched=(SELECT MAX(fetched) FROM snapshots t WHERE t.key=s.key) ORDER BY fetched DESC").fetchall()
    return [json.loads(r[0]) for r in rows]

def event(kind, message):
    with db() as c: c.execute('INSERT INTO events VALUES(?,?,?)',(now(),kind,message))

def save_run(payload):
    payload = {**payload, 'version':VERSION}
    rid = hashlib.sha256(encode(payload).encode()).hexdigest()[:16]
    payload = {**payload, 'id':rid, 'version':VERSION, 'created_at':now()}
    with db() as c: c.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?)',(rid,payload['created_at'],encode(payload)))
    return get_run(rid)

def get_run(rid):
    with db() as c: r = c.execute('SELECT payload FROM runs WHERE id=?',(rid,)).fetchone()
    if not r: raise ValueError('找不到分析记录')
    return json.loads(r[0])

def runs():
    with db() as c: rows = c.execute('SELECT payload FROM runs ORDER BY created DESC LIMIT 100').fetchall()
    return [json.loads(r[0]) for r in rows]

def profile(symbol, value=None):
    with db() as c:
        if value is not None:
            c.execute('INSERT OR REPLACE INTO profiles VALUES(?,?)',(symbol,encode(value)))
            return value
        r = c.execute('SELECT payload FROM profiles WHERE symbol=?',(symbol,)).fetchone()
    return json.loads(r[0]) if r else {'symbol':symbol,'template':'general','peers':[], 'metrics':['revenue','profit','cashflow'],'focus':'','name':symbol}
