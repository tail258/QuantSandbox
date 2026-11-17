"""Immutable stock/ETF inputs and freshness gates for the decision overview."""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import Future
from datetime import date, datetime, time, timedelta, timezone
from math import isclose
from threading import Lock, Semaphore
from zoneinfo import ZoneInfo

from backend.core.decision import ANCHOR_MAX_AGE, analyze_daily
from backend.core.decision.evaluation import MAX_OBSERVATIONS, evaluate_daily
from backend.core.decision.factors import DEFAULT_FACTORS, FACTOR_KEYS, FACTOR_VERSION, describe_factors
from backend.core.decision.timeframes import analyze_completed_weeks
from backend.services.errors import ResearchError
from backend.workbench import store
from backend.workbench.decision_provider import fetch_daily_market

SHANGHAI = ZoneInfo('Asia/Shanghai')
SESSION_CLOSE = time(15)
# Allow an ordinary provider publication delay; bars fetched earlier are never
# promoted into finalized daily bars simply because the reader's clock advanced.
INGEST_AFTER = time(16, 30)
RECENT_DISCONTINUITY_DAYS = 10
SNAPSHOT_KIND = 'stock_decision_daily'
BAR_FIELDS = ('date', 'open', 'high', 'low', 'close', 'volume')
_lock = Lock()
_provider_slot = Semaphore(1)
_in_flight: dict[tuple[str, str], Future] = {}


def validate_scope(symbol: str, project: dict | None):
    if not re.fullmatch(r'[0-9]{6}', symbol):
        raise ResearchError(422, '该入口目前只支持已核验的沪深股票及 ETF 代码。')
    if project is not None and symbol not in project['symbols']:
        raise ResearchError(404, '证券不属于当前研究项目。')


def _local(clock: datetime | None = None):
    now = clock or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError('Stock decision clock must include a timezone')
    return now.astimezone(SHANGHAI)


def _key(symbol):
    return f'decision-quotes:{symbol}'


def _hash(payload):
    return hashlib.sha256(store.encode(payload).encode('utf-8')).hexdigest()


def _verify(frozen, symbol):
    if (frozen.get('kind') != SNAPSHOT_KIND or frozen.get('symbol') != symbol
            or frozen.get('instrument', {}).get('symbol') != symbol):
        raise ResearchError(404, '该行情快照不属于当前证券。')
    data = {key: value for key, value in frozen.items() if key != 'id'}
    if not _hash(data).startswith(frozen['id']):
        raise ResearchError(409, '行情快照完整性校验失败。')


def _coverage(calendar, now):
    today = now.date().isoformat()
    known = calendar['start_date'] <= today <= calendar['end_date']
    expected = max((day for day in calendar['sessions'] if day < today or
                    day == today and now.time() >= SESSION_CLOSE), default=None) if known else None
    return known, expected


def _publication_breaks(rows, sessions):
    # A provider's same-session reference can differ after an ex-rights event.
    # Treat a discrepancy as a possible discontinuity, not a proven dividend.
    previous_session = {day: prior for prior, day in zip(sessions, sessions[1:])}
    # Explicitly suspended rows carry a verified frozen reference. Keep them
    # here so an adjustment during a halt cannot splice two price bases.
    return [current['date'] for previous, current in zip(rows, rows[1:])
            if previous_session.get(current['date']) == previous['date']
            and current['prev_close'] is not None
            and not isclose(current['prev_close'], previous['close'], rel_tol=1e-6, abs_tol=0.00011)]


def _empty(symbol, project, refresh_status='cache', warning=None):
    return {'symbol': symbol, 'project_id': project['id'] if project else None,
            'status': 'empty', 'refresh_status': refresh_status, 'warning': warning,
            'input': None, 'instrument': None, 'bars': [], 'structures': {}, 'plan': None, 'weekly': None,
            'factors': [], 'structure_observations': []}


def _view(frozen, symbol, project, now, *, cutoff=None, pinned=False, refresh_status='cache', warning=None):
    _verify(frozen, symbol)
    calendar = frozen['calendar']
    verified, latest_expected = _coverage(calendar, now)
    sessions = calendar['sessions']
    last_observed = frozen['rows'][-1]['date']
    if pinned and cutoff is None:
        cutoff = last_observed
    if cutoff is not None and (cutoff > last_observed or cutoff < frozen['rows'][0]['date'] or cutoff not in sessions):
        raise ResearchError(422, '所选历史截点必须是行情快照覆盖内的已知交易日。')
    end = cutoff or last_observed
    rows = [row for row in frozen['rows'] if row['date'] <= end]
    active = [row for row in rows if not row['is_suspended'] and row['volume'] > 0]
    zero_sessions = [row['date'] for row in rows if not row['is_suspended'] and row['volume'] <= 0]
    suspended = [row['date'] for row in rows if row['is_suspended']]
    observed = {row['date'] for row in rows}
    start = max(frozen['request']['start'], frozen['instrument']['ipo_date'])
    expected_through = end if cutoff or latest_expected is None else max(end, latest_expected)
    missing = [day for day in sessions if start <= day <= expected_through and day not in observed]
    issues = []
    if cutoff is None:
        if not verified:
            issues.append('calendar_outdated')
        elif latest_expected and last_observed < latest_expected:
            issues.append('stale_quotes')
    if warning:
        issues.append('provider_refresh_failed')
    if not active or rows[-1]['date'] != active[-1]['date']:
        issues.append('last_session_untradable')
    last_active = active[-1]['date'] if active else None
    planned_for = next((day for day in sessions if day > last_active), None) if last_active else None
    reference_breaks = _publication_breaks(rows, sessions)
    discontinuities = sorted(set(missing + zero_sessions + reference_breaks))
    if last_active:
        lookback = active[max(0, len(active) - ANCHOR_MAX_AGE)]['date']
        if any(day >= lookback for day in missing + zero_sessions):
            issues.append('recent_session_gap')
        recent = (date.fromisoformat(last_active) - timedelta(days=RECENT_DISCONTINUITY_DAYS)).isoformat()
        if any(day >= recent for day in reference_breaks):
            issues.append('recent_reference_discontinuity')
    if cutoff is not None:
        issues.append('retrospective_snapshot')
    snapshot = {'id': frozen['id'], 'sha256': _hash({k: v for k, v in frozen.items() if k != 'id'}),
                'source': frozen['source'], 'source_url': frozen['source_url'], 'fetched_at': frozen['fetched_at'],
                'price_basis': 'raw_unadjusted', 'volume_unit': 'shares' if frozen['instrument']['kind'] == 'stock' else 'units',
                'start_date': active[0]['date'] if active else None, 'end_date': last_active,
                'last_observed_session': rows[-1]['date'], 'expected_session': latest_expected if cutoff is None else cutoff,
                'calendar_source': calendar['source'], 'calendar_source_url': calendar['source_url'],
                'market_timezone': 'Asia/Shanghai', 'missing_sessions': missing, 'suspended_sessions': suspended,
                'zero_volume_sessions': zero_sessions, 'reference_breaks': reference_breaks,
                'historical': cutoff is not None}
    active_bars = [{key: row[key] for key in BAR_FIELDS} for row in active]
    model = analyze_daily(active_bars,
                          observation_session=planned_for, data_issues=issues, discontinuities=discontinuities,
                          price_tick='0.01' if frozen['instrument']['kind'] == 'stock' else '0.001',
                          include_center_observations=True) if active else {
                              'bars': [], 'structures': {}, 'plan': None, 'structure_observations': []}
    weekly = analyze_completed_weeks(sessions=sessions, active_bars=active_bars, suspended_sessions=suspended,
                                    discontinuities=discontinuities, coverage_start=start, cutoff=end)
    return {'symbol': symbol, 'project_id': project['id'] if project else None,
            'status': 'ready' if model['plan'] else 'no_active_bars', 'refresh_status': refresh_status,
            'warning': warning, 'input': snapshot, 'instrument': frozen['instrument'], 'weekly': weekly,
            'factors': describe_factors(active_bars, discontinuities), **model}


def _saved_snapshot(snapshot_id):
    try:
        return store.get_snapshot(snapshot_id)
    except ValueError as exc:
        raise ResearchError(404, '找不到该行情快照。') from exc


def get_analysis(symbol, project=None, *, snapshot_id=None, cutoff=None, clock=None):
    validate_scope(symbol, project)
    if cutoff is not None and snapshot_id is None:
        raise ResearchError(422, '历史回看需指定原始行情快照。')
    frozen = _saved_snapshot(snapshot_id) if snapshot_id else store.latest(_key(symbol))
    return _view(frozen, symbol, project, _local(clock), cutoff=cutoff, pinned=snapshot_id is not None) if frozen else _empty(symbol, project)


def evaluation(symbol, project, snapshot_id, *, cutoff=None, holding_sessions=5):
    validate_scope(symbol, project)
    frozen = _saved_snapshot(snapshot_id)
    _verify(frozen, symbol)
    history_start = max(frozen['request']['start'], frozen['instrument']['ipo_date'])
    sessions = frozen['calendar']['sessions']
    end = cutoff or frozen['rows'][-1]['date']
    if end not in sessions or not frozen['rows'][0]['date'] <= end <= frozen['rows'][-1]['date']:
        raise ResearchError(422, '验证截点须位于原始快照的已知交易日范围。')
    window = [day for day in sessions if history_start <= day <= end][-MAX_OBSERVATIONS:]
    result = evaluate_daily(frozen['rows'], sessions=sessions, history_start=history_start,
                            start=window[0], end=end, holding_sessions=holding_sessions,
                            price_tick='0.01' if frozen['instrument']['kind'] == 'stock' else '0.001')
    return {**result, 'symbol': symbol, 'project_id': project['id'] if project else None, 'snapshot_id': snapshot_id}


def factor_selection(symbol, project, keys=None):
    validate_scope(symbol, project)
    project_id = project['id'] if project else None
    namespace = f'decision-factors:{project_id or "standalone"}:{symbol}'
    if keys is not None and (len(set(keys)) != len(keys) or not set(keys).issubset(FACTOR_KEYS)):
        raise ResearchError(422, '请选择无重复的已支持因子。')
    result = (store.profile(namespace, {'selected': keys, 'updated_at': store.now()})
              if keys is not None else store.profile(namespace))
    return {'symbol': symbol, 'project_id': project_id, 'selected': result.get('selected', list(DEFAULT_FACTORS)),
            'updated_at': result.get('updated_at'), 'version': FACTOR_VERSION}


def _fetch_and_store(symbol, now):
    old = store.latest(_key(symbol))
    today = now.date()
    # Reuse the original start on refresh to preserve the structure context.
    start = old['request']['start'] if old else (today - timedelta(days=4 * 366)).isoformat()
    query_end = today if now.time() >= INGEST_AFTER else today - timedelta(days=1)
    calendar_end = today + timedelta(days=21 - today.weekday())
    # Anonymous BaoStock connections may invalidate each other's session.
    # Serialize the provider call across different symbols as well as joining
    # duplicate requests for the same symbol below.
    with _provider_slot:
        raw = fetch_daily_market(symbol, start, query_end.isoformat(), calendar_end.isoformat())
    sessions = set(raw['calendar']['sessions'])
    supplied = [row['date'] for row in raw['rows']]
    if not supplied or supplied != sorted(set(supplied)) or any(
            not start <= day <= query_end.isoformat() or day not in sessions for day in supplied):
        raise ValueError('行情日期与已知交易日不一致，未写入新的行情快照。')
    if old and supplied[-1] < old['rows'][-1]['date']:
        raise ValueError('来源返回的行情比已保存版本更旧，保留原快照。')
    payload = {**raw, 'kind': SNAPSHOT_KIND, 'symbol': symbol,
               'request': {'start': start, 'end': query_end.isoformat(), 'adjust': '3'}}
    if old and all(payload[key] == old.get(key) for key in ('rows', 'calendar', 'instrument', 'source', 'source_url')):
        return old
    return store.snapshot(_key(symbol), payload)


def _joined_refresh(symbol, now):
    key = (str(store.data_path().resolve()), symbol)
    with _lock:
        handle = _in_flight.get(key)
        owner = handle is None
        if owner:
            handle = Future()
            _in_flight[key] = handle
    if not owner:
        return handle.result()
    try:
        result = _fetch_and_store(symbol, now)
    except BaseException as error:
        handle.set_exception(error)
        raise
    else:
        handle.set_result(result)
        return result
    finally:
        with _lock:
            _in_flight.pop(key, None)


def refresh_analysis(symbol, project=None, *, clock=None):
    validate_scope(symbol, project)
    request_time = _local(clock)
    try:
        frozen = _joined_refresh(symbol, request_time)
    except ValueError as exc:
        warning = str(exc)
        frozen = store.latest(_key(symbol))
        if not frozen:
            return _empty(symbol, project, 'failed', warning)
        return _view(frozen, symbol, project, _local(clock), refresh_status='failed', warning=warning)
    # A provider request may have straddled the end of the observation session.
    return _view(frozen, symbol, project, _local(clock), refresh_status='refreshed')
