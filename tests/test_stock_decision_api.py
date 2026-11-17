from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import stock_decision


def market_rows(symbol, start, end, calendar_end):
    first = date(2025, 1, 2)
    date_end = date.fromisoformat(calendar_end)
    days = [first + timedelta(days=offset) for offset in range((date_end - first).days + 1)]
    sessions = [day.isoformat() for day in days if day.weekday() < 5 and day != date(2025, 2, 3)]
    rows = [{'date': session, 'open': 11., 'high': 12., 'low': 10., 'close': 11.,
             'volume': 100_000, 'prev_close': 11., 'is_suspended': False}
            for session in sessions if start <= session <= end]
    return {'instrument': {'symbol': symbol, 'name': 'Fixture stock', 'exchange': 'SSE', 'kind': 'stock',
                           'listed': True, 'ipo_date': first.isoformat()},
            'calendar': {'start_date': start, 'end_date': calendar_end, 'source': 'Fixture calendar',
                         'source_url': 'https://example.test/calendar', 'sessions': sessions},
            'source': 'Fixture quotes', 'source_url': 'https://example.test/quotes', 'rows': rows}


def test_scoped_cold_read_click_refresh_and_frozen_pinned_history(tmp_path, monkeypatch):
    now = [datetime.fromisoformat('2025-02-02T11:00:00+08:00')]
    calls = []

    def fetch(*args):
        calls.append(args)
        return market_rows(*args)

    monkeypatch.setattr(stock_decision, '_local', lambda clock=None: now[0])
    monkeypatch.setattr(stock_decision, 'fetch_daily_market', fetch)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        other = client.post('/api/projects', json={'name': 'Other', 'question': '', 'symbols': ['000338']}).json()
        route = '/api/decision/600105'
        assert client.get(route).json()['status'] == 'empty'
        assert not calls
        assert client.post(f'{route}/refresh?project_id={other["id"]}').status_code == 404
        assert not calls
        result = client.post(route + '/refresh').json()
        assert result['plan']['as_of'] == '2025-01-31'
        assert result['plan']['observation_session'] == '2025-02-04'  # calendar holiday, not a guessed weekday
        assert result['weekly']['context']['completed_through'] == '2025-01-31'
        assert result['plan']['data_quality'] == 'checked'
        assert {entry['key']: entry['value'] for entry in result['factors']} == {
            'sma20': 11, 'sma60': None, 'rsi14': 50, 'bollinger20': 11, 'relative_volume20': 1,
        }
        assert calls[-1][2] == '2025-02-01'
        original = result['input']['id']
        assert client.get(route).json()['input']['id'] == original
        assert client.get(f'/api/decision/000338?snapshot_id={original}').status_code == 404
        original_pinned = client.get(f'{route}?snapshot_id={original}').json()
        assert original_pinned['input']['historical'] and original_pinned['plan']['as_of'] == '2025-01-31'
        assert [item['kind'] for item in original_pinned['plan']['scenarios']] == ['otherwise']

        now[0] = datetime.fromisoformat('2025-02-04T15:10:00+08:00')
        # During the grace period the prior series remains visible, but does
        # not authorize a condition plan for after today's close.
        delayed = client.post(route + '/refresh').json()
        assert calls[-1][2] == '2025-02-03'
        assert delayed['bars'] == result['bars']  # a wider calendar alone may create a new snapshot
        assert delayed['input']['expected_session'] == '2025-02-04'
        assert 'stale_quotes' in delayed['plan']['data_issues']
        assert [item['action'] for item in delayed['plan']['scenarios']] == ['watch']

        now[0] = datetime.fromisoformat('2025-02-04T17:30:00+08:00')
        current = client.post(route + '/refresh').json()
        assert current['input']['id'] != original
        assert current['plan']['as_of'] == '2025-02-04'
        assert current['plan']['observation_session'] == '2025-02-05'
        pinned = client.get(f'{route}?snapshot_id={original}&as_of=2025-01-30').json()
        assert pinned['input']['historical']
        assert pinned['plan']['as_of'] == '2025-01-30'
        assert pinned['plan']['observation_session'] == '2025-01-31'
        assert pinned['plan']['data_issues'] == ['retrospective_snapshot']
        assert pinned['weekly']['context']['completed_through'] == '2025-01-24'
        assert pinned['weekly']['context']['scheduled_completion'] == '2025-01-31'
        assert all(bar['date'] <= '2025-01-30' for bar in pinned['bars'])
        study = client.get(f'{route}/evaluation?snapshot_id={original}&as_of=2025-01-30').json()
        assert study['regime'] == 'retrospective_single_snapshot'
        assert study['snapshot_id'] == original and study['end'] == '2025-01-30'
        assert study['assumptions']['execution'] == 'unverified_open_reference'
        assert study['counts']['scheduled_observations'] == 21
        assert client.get(f'/api/decision/000338/evaluation?snapshot_id={original}').status_code == 404
        assert client.get(f'{route}?as_of=2025-01-30').status_code == 422


def test_failed_refresh_keeps_last_real_snapshot_and_disables_current_scenarios(tmp_path, monkeypatch):
    now = datetime.fromisoformat('2025-02-04T17:30:00+08:00')
    monkeypatch.setattr(stock_decision, '_local', lambda clock=None: now)
    monkeypatch.setattr(stock_decision, 'fetch_daily_market', market_rows)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        route = '/api/decision/600105'
        saved = client.post(route + '/refresh').json()

        def fail(*args):
            raise ValueError('来源暂时不可用')

        monkeypatch.setattr(stock_decision, 'fetch_daily_market', fail)
        fallback = client.post(route + '/refresh').json()
        assert fallback['refresh_status'] == 'failed'
        assert fallback['warning'] == '来源暂时不可用'
        assert fallback['input']['id'] == saved['input']['id']
        assert fallback['bars'] == saved['bars']
        assert 'provider_refresh_failed' in fallback['plan']['data_issues']
        blank = client.post('/api/decision/000338/refresh').json()
        assert blank['status'] == 'empty' and not blank['bars'] and blank['plan'] is None


def test_missing_bar_and_confirmed_halt_are_distinguished(tmp_path, monkeypatch):
    now = datetime.fromisoformat('2025-02-04T17:30:00+08:00')
    monkeypatch.setattr(stock_decision, '_local', lambda clock=None: now)

    def sparse(*args):
        payload = market_rows(*args)
        payload['rows'] = [row for row in payload['rows'] if row['date'] != '2025-01-30']
        payload['rows'][-1].update({'is_suspended': True, 'volume': 0, 'open': 11., 'high': 11., 'low': 11.})
        return payload

    monkeypatch.setattr(stock_decision, 'fetch_daily_market', sparse)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        data = client.post('/api/decision/600105/refresh').json()
        assert data['input']['missing_sessions'] == ['2025-01-30']
        assert data['input']['suspended_sessions'] == ['2025-02-04']
        assert data['input']['last_observed_session'] == '2025-02-04'
        assert data['plan']['as_of'] == '2025-01-31'
        assert {'last_session_untradable', 'recent_session_gap'} <= set(data['plan']['data_issues'])
        assert [item['kind'] for item in data['plan']['scenarios']] == ['otherwise']


def test_factor_selections_stay_local_to_symbol_and_project(tmp_path):
    route = '/api/decision/600105/factors'
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        project = client.post('/api/projects', json={'name': 'Example', 'symbols': ['600105']}).json()
        other = client.post('/api/projects', json={'name': 'Other', 'symbols': ['000338']}).json()
        scoped = f'{route}?project_id={project["id"]}'
        assert client.get(scoped).json()['selected'] == ['sma20', 'relative_volume20']
        assert client.put(scoped, json={'selected': ['rsi14', 'bollinger20']}).json()['selected'] == ['rsi14', 'bollinger20']
        assert client.put(scoped, json={'selected': ['rsi14', 'rsi14']}).status_code == 422
        assert client.put(scoped, json={'selected': ['unsupported']}).status_code == 422
        assert client.put(f'{route}?project_id={other["id"]}', json={'selected': []}).status_code == 404
        assert client.get(route).json()['selected'] == ['sma20', 'relative_volume20']
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        assert client.get(scoped).json()['selected'] == ['rsi14', 'bollinger20']


@pytest.mark.parametrize('reset_day', ['2025-01-31', '2025-02-04'])
def test_potential_price_reset_during_a_halt_or_at_resumption_disables_the_plan(tmp_path, monkeypatch, reset_day):
    monkeypatch.setattr(stock_decision, '_local', lambda _: datetime.fromisoformat('2025-02-04T17:30:00+08:00'))

    def after_halt(*args):
        payload = market_rows(*args)
        for row in payload['rows']:
            if row['date'] >= reset_day:
                for field in ('open', 'close', 'high', 'low', 'prev_close'):
                    row[field] /= 2
            if row['date'] == '2025-01-31':
                row.update(is_suspended=True, volume=0, open=row['close'], high=row['close'], low=row['close'])
        return payload

    monkeypatch.setattr(stock_decision, 'fetch_daily_market', after_halt)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        result = client.post('/api/decision/600105/refresh').json()
        assert result['input']['reference_breaks'] == [reset_day]
        assert 'recent_reference_discontinuity' in result['plan']['data_issues']
        assert [item['kind'] for item in result['plan']['scenarios']] == ['otherwise']
        assert result['weekly']['context']['completed_through'] is None
        assert all(item['value'] is None for item in result['factors'])


def test_provider_request_straddling_close_uses_clock_when_serving_the_plan(tmp_path, monkeypatch):
    clocks = iter(map(datetime.fromisoformat, ('2025-02-04T14:59:50+08:00', '2025-02-04T15:00:10+08:00')))
    monkeypatch.setattr(stock_decision, '_local', lambda _: next(clocks))
    monkeypatch.setattr(stock_decision, 'fetch_daily_market', market_rows)
    with TestClient(create_app(tmp_path, run_jobs=False)) as client:
        result = client.post('/api/decision/600105/refresh').json()
        assert result['plan']['as_of'] == '2025-01-31'
        assert result['input']['expected_session'] == '2025-02-04'
        assert 'stale_quotes' in result['plan']['data_issues']
        assert [item['kind'] for item in result['plan']['scenarios']] == ['otherwise']
