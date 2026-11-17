"""Local service-lifetime ETF refresh schedule (Shanghai clock)."""
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from . import store, etf

TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')
_lock = threading.RLock()

def now():
    return datetime.now(TZ)

def path():
    return store.data_path() / 'etf-refresh-settings.json'

def read():
    p = path()
    try:
        saved = etf._retry_job_io(lambda: json.loads(p.read_text(encoding='utf-8'))) if p.exists() else {}
        if not isinstance(saved, dict) or not isinstance(saved.get('enabled', True), bool) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', str(saved.get('time', '15:30'))):
            raise ValueError('Invalid refresh settings')
    except (json.JSONDecodeError, ValueError):
        return {'enabled': False, 'time': '15:30', 'warning': '刷新设置损坏；自动刷新已暂停，请重新保存设置'}
    return {'enabled': True, 'time': '15:30', **saved}

def write(s):
    p = path(); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    try:
        etf._retry_job_io(lambda: tmp.write_text(store.encode(s), encoding='utf-8'))
        etf._retry_job_io(lambda: tmp.replace(p))
    finally: tmp.unlink(missing_ok=True)

def settings(p=None):
    with _lock:
        s = read()
        if p is not None:
            if set(p) - {'enabled', 'time'}: raise ValueError('仅支持 enabled 和 time')
            if 'enabled' in p and not isinstance(p['enabled'], bool): raise ValueError('enabled 须为布尔值')
            if 'time' in p and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', str(p['time'])): raise ValueError('时间格式须为 HH:MM')
            s.update(p); s.pop('warning', None); write(s)
        n = now(); h, m = map(int, s['time'].split(':')); due = n.replace(hour=h, minute=m, second=0, microsecond=0)
        if s.get('last_auto_date') == n.date().isoformat(): due += timedelta(days=1)
        try: status = etf.get_job(s['last_job_id'])['status'] if s.get('last_job_id') else 'idle'
        except ValueError: status = 'unavailable'
        return {**s, 'timezone': 'Asia/Shanghai', 'next_run': due.isoformat() if s['enabled'] else None, 'status': status, 'last_job_id': s.get('last_job_id'), 'last_attempt': s.get('last_attempt'), 'service_required': True}

def refresh_now(auto=False):
    with _lock:
        s = read(); n = now()
        job = etf.start_job({'recent_days': 5})
        s.update(last_job_id=job['id'], last_attempt=n.isoformat())
        if auto: s['last_auto_date'] = n.date().isoformat()
        write(s)
        return job

def tick():
    with _lock:
        s = read(); n = now()
        if s['enabled'] and n.strftime('%H:%M') >= s['time'] and s.get('last_auto_date') != n.date().isoformat(): refresh_now(auto=True)

class Scheduler:
    def __init__(self, root):
        self.root = root; self.stop_event = threading.Event(); self.thread = None
    def start(self):
        self.thread = threading.Thread(target=self.run, name='etf-daily-refresh', daemon=True); self.thread.start()
    def run(self):
        token = store._scope_data.set(self.root)
        try:
            while not self.stop_event.wait(30):
                try: tick()
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('ETF scheduled refresh failed')
        finally: store._scope_data.reset(token)
    def close(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=5)
