"""Read-only ETF quote cache and actual five-minute same-time comparisons."""
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import math
import json
import time
import threading
import uuid
from . import store, etf

TZ = timezone(timedelta(hours=8))
_LOCK = threading.RLock()
_JOBS = {}
_ACTIVE = {}
_ERRORS = {}
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix='etf-intraday-bars')
_QUOTES = ThreadPoolExecutor(max_workers=1, thread_name_prefix='etf-intraday-quotes')


def now():
    return datetime.now(TZ)


def timestamp(value):
    d = datetime.fromisoformat(value)
    if d.tzinfo is None:
        raise ValueError('Source timestamp must include timezone')
    return d.astimezone(TZ)


def slots():
    return [f'{h:02d}:{m:02d}' for h, m in [(9 + n // 60, n % 60) for n in range(35, 151, 5)] + [(13 + n // 60, n % 60) for n in range(5, 121, 5)]]


SLOTS = slots()


def comparison(quote, history, clock=None, calendar=None):
    clock = clock or now()
    result = dict(ratio=None, sample_count=0, target_samples=20, status='unavailable', boundary=None,
                  current_amount=None, historical_mean_amount=None, excluded_days=[], unit='CNY',
                  calendar_status='observed_source_sessions_only', stale=True)
    if not quote or not quote.get('source_time') or not history:
        return result
    try:
        qt = timestamp(quote['source_time'])
    except (ValueError, TypeError):
        return result
    if qt.weekday() >= 5 or qt > clock + timedelta(minutes=1):
        return result
    eligible = [s for s in SLOTS if s <= qt.strftime('%H:%M')]
    if not eligible:
        return result
    boundary = eligible[-1]
    days = {}
    invalid = set()
    for row in history.get('rows', []):
        try:
            t = timestamp(row['time']); amount = row['amount_cny']
            if not isinstance(amount, (float, int)) or not math.isfinite(amount) or amount < 0:
                raise ValueError('Invalid amount')
            day, slot = t.date().isoformat(), t.strftime('%H:%M')
            if slot not in SLOTS or t.second or t.microsecond:
                invalid.add(day); continue
            daily = days.setdefault(day, {})
            if slot in daily:
                invalid.add(day)
            daily[slot] = amount
        except (ValueError, KeyError, TypeError):
            continue
    today = qt.date().isoformat()
    required = SLOTS[:SLOTS.index(boundary) + 1]
    current = days.get(today, {})
    result['boundary'] = today + 'T' + boundary + ':00+08:00'
    result['comparison_cutoff'] = result['boundary']
    result['stale'] = quote_stale(qt, clock)
    if today in invalid or any(s not in current for s in required):
        return result
    result['current_amount'] = sum(current[s] for s in required)
    observed = sorted(d for d in days if d < today)
    covered = sorted({d for d in (calendar or []) if d < today})
    if observed and (not covered or covered[-1] < observed[-1]):
        calendar = None
        result['calendar_warning'] = 'Index calendar predates latest observed session; observed sessions only'
    selected = sorted({d for d in (calendar if calendar is not None else days) if d < today}, reverse=True)[:20]
    result['calendar_status'] = 'verified_index_sessions' if calendar is not None and len(selected) == 20 else 'unverified'
    result['window_start'] = min(selected) if selected else None
    result['window_end'] = max(selected) if selected else None
    result['sample_dates'] = []
    values = []
    for d in selected:
        if d in invalid or set(days.get(d, {})) != set(SLOTS):
            result['excluded_days'].append({'date': d, 'reason': 'incomplete_or_duplicate_bars'})
        else:
            values.append(sum(days[d][s] for s in required))
            result['sample_dates'].append(d)
    n = len(values)
    result.update(sample_count=n, status='complete' if n == 20 and result['calendar_status'] == 'verified_index_sessions' else 'provisional' if n >= 5 else 'insufficient')
    if values:
        result['historical_mean_amount'] = sum(values) / n
    if n >= 5 and result['historical_mean_amount'] > 0 and not result['stale']:
        result['ratio'] = result['current_amount'] / result['historical_mean_amount']
    return result


def _key(kind, code):
    return f'etf:intraday:{kind}:{code}'


def quote_stale(t, clock):
    if t.date() != clock.date() or t > clock + timedelta(minutes=1):
        return True
    hm = clock.strftime('%H:%M')
    source_hm = t.strftime('%H:%M')
    if hm >= '15:00' and source_hm >= '15:00':
        return False
    if '11:30' <= hm < '13:00' and source_hm == '11:30':
        return False
    return clock - t > timedelta(seconds=120)


def _record_error(code, errors, kind='quote'):
    store.snapshot(_key('errors_' + kind, code), {'errors': errors})


def _job_path(jid):
    if len(jid) != 32 or not all(c in '0123456789abcdef' for c in jid):
        raise ValueError('Unknown ETF intraday job')
    return store.data_path() / 'etf-intraday-jobs' / (jid + '.json')


def _retry_io(action):
    for attempt in range(5):
        try:
            return action()
        except (PermissionError, json.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(.02 * (attempt + 1))


def _persist_job(job):
    path = _job_path(job['id']); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with _LOCK:
        try:
            _retry_io(lambda: tmp.write_text(store.encode({k:v for k,v in job.items() if k != 'key'}), encoding='utf-8'))
            _retry_io(lambda: tmp.replace(path))
        finally:
            tmp.unlink(missing_ok=True)


def session(source_time, clock):
    if not source_time:
        return 'unknown'
    t = timestamp(source_time)
    if t.weekday() >= 5:
        return 'weekend'
    hm = t.strftime('%H:%M')
    if hm < '09:30':
        return 'auction' if hm >= '09:15' else 'pre_open'
    if hm <= '11:30' or '13:00' <= hm <= '15:00':
        return 'trading'
    return 'lunch' if hm < '13:00' else 'after_close'


def dashboard(codes=None):
    items = []
    clock = now()
    calendar = None
    state = store.latest('etf_dashboard')
    if state:
        run = store.get_run(state['run_id'])
        for sid in run['inputs']:
            snap = store.get_snapshot(sid)
            if snap.get('kind') == 'etf_index':
                calendar = [r['date'] for r in snap['rows'] if r.get('close') is not None]
                break
    for code in etf.codes_of(codes):
        q = store.latest(_key('quote', code)); h = store.latest(_key('bars', code))
        quote = q['rows'][0] if q else None
        try:
            stale = not quote or quote_stale(timestamp(quote['source_time']), clock)
        except (ValueError, TypeError, KeyError):
            stale = True
        errors = []
        for kind in ('quote', 'bars'):
            error_state = store.latest(_key('errors_' + kind, code))
            errors.extend(error_state.get('errors', []) if error_state else [])
        comp = comparison(quote, h, clock, calendar)
        if quote:
            quote = {**quote, 'price': quote.get('last'), 'amount': quote.get('amount_cny'), 'session': session(quote.get('source_time'), clock), 'session_valid': not stale and not errors and session(clock.isoformat(), clock) in ('auction', 'trading') and timestamp(quote['source_time']).date() == clock.date(), 'freshness': 'stale' if stale else 'after_close_snapshot' if clock.strftime('%H:%M') >= '15:00' else 'current'}
        if errors:
            comp.update(stale=True, ratio=None)
        comp['current_amount_cny'] = comp['current_amount']
        comp['historical_mean_amount_cny'] = comp['historical_mean_amount']
        # A cached bar set may predate the current quote boundary.
        items.append(dict(code=code, quote=quote, comparison=comp, stale=stale or bool(errors), errors=errors,
                          quote_snapshot_id=q['id'] if q else None, history_snapshot_id=h['id'] if h else None,
                          quote_source=q.get('source') if q else None, history_source=h.get('source') if h else None,
                          quote_fetched_at=q.get('fetched_at') if q else None, history_fetched_at=h.get('fetched_at') if h else None,
                          provenance={'quote': q.get('provenance') if q else None, 'history': h.get('provenance') if h else None}))
    return {'items': items, 'generated_at': clock.isoformat(), 'quote_ttl_seconds': 20, 'bar_ttl_seconds': 300}


def _fresh(snapshot, ttl):
    return snapshot and 0 <= (now() - timestamp(snapshot['fetched_at'])).total_seconds() < ttl


def _bars(code, force=False):
    from . import etf_intraday_sources as source
    key = _key('bars', code)
    if not force and _fresh(store.latest(key), 300):
        return
    data = source.fetch_bars(code)
    if not data.get('rows') or data.get('amount_basis') != 'reported_actual' or data.get('timestamp_convention') != 'bar_end':
        raise ValueError('Actual bar-end turnover data required')
    store.snapshot(key, {**data, 'content_hash': hashlib.sha256(store.encode(data).encode()).hexdigest()})


def _run(jid, codes, history, force):
    from . import etf_intraday_sources as source
    job = _JOBS[jid]; job['status'] = 'running'
    root = str(store.data_path())
    try:
        needed = [] if history else [c for c in codes if force or not _fresh(store.latest(_key('quote', c)), 20)]
        if needed:
            try:
                data = source.fetch_quotes(needed)
                by_code = {r['code']: r for r in data['rows']}
                for c in needed:
                    if c not in by_code:
                        raise ValueError('Quote batch omitted ' + c)
                    source_clock = timestamp(by_code[c]['source_time'])
                    if source_clock > now() + timedelta(minutes=1):
                        raise ValueError('Quote source timestamp is in the future: ' + c)
                for c in needed:
                    payload = {**data, 'rows': [by_code[c]]}
                    store.snapshot(_key('quote', c), {**payload, 'content_hash': hashlib.sha256(store.encode(payload).encode()).hexdigest()})
                    _ERRORS[(root, c)] = []; _record_error(c, [])
            except Exception as exc:
                for c in needed:
                    _ERRORS[(root, c)] = [str(exc)]; _record_error(c, [str(exc)])
                job['errors'].append(str(exc))
        bar_codes = codes if history else []
        if not history:
            due = [c for c in codes if store.latest(_key('bars', c)) and not _fresh(store.latest(_key('bars', c)), 300)]
            if due:
                job['bar_job_id'] = start_job({'codes': due, 'history': True})['id']
        if bar_codes:
            for c in bar_codes:
                try:
                    _bars(c, force)
                    _record_error(c, [], 'bars')
                except Exception as exc:
                    _ERRORS.setdefault((root, c), []).append(str(exc)); _record_error(c, _ERRORS[(root, c)], 'bars'); job['errors'].append(c + ': ' + str(exc))
                job['completed'] += 1
        else:
            job['completed'] = len(codes)
        job['status'] = 'completed' if not job['errors'] else 'completed_with_errors'
    except Exception as exc:
        job.update(status='failed'); job['errors'].append(str(exc))
    finally:
        try:
            _persist_job(job)
        finally:
            with _LOCK:
                _ACTIVE.pop(job['key'], None)


def start_job(params=None):
    params = params or {}; codes = etf.codes_of(params.get('codes'))
    history = bool(params.get('history', False)); force = bool(params.get('force', False))
    key = (str(store.data_path()), tuple(sorted(codes)), history)
    with _LOCK:
        if key in _ACTIVE:
            return get_job(_ACTIVE[key])
        jid = uuid.uuid4().hex
        _JOBS[jid] = dict(id=jid, status='queued', codes=codes, history=history, completed=0, total=len(codes), errors=[], key=key, data_scope=str(store.data_path()))
        try:
            _persist_job(_JOBS[jid])
        except Exception:
            _JOBS.pop(jid, None)
            raise
        _ACTIVE[key] = jid
        ctx = copy_context(); (_POOL if history else _QUOTES).submit(ctx.run, _run, jid, codes, history, force)
        return get_job(jid)


def get_job(jid):
    path = _job_path(jid)
    job = _JOBS.get(jid)
    if job and job.get('data_scope') != str(store.data_path()):
        raise ValueError('Unknown ETF intraday job')
    if not job:
        if not path.exists():
            raise ValueError('Unknown ETF intraday job')
        with _LOCK:
            try:
                job = _retry_io(lambda: json.loads(path.read_text(encoding='utf-8')))
            except json.JSONDecodeError as exc:
                raise ValueError('ETF intraday job record is damaged; refresh again') from exc
        if job.get('data_scope') != str(store.data_path()):
            raise ValueError('Unknown ETF intraday job')
        if job['status'] in ('running', 'queued'):
            job.update(status='interrupted', errors=job.get('errors', []) + ['Service restarted; refresh again'])
    return {k: v for k, v in job.items() if k not in ('key', 'data_scope')}
