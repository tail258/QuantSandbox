from datetime import date, timedelta

import pytest

from backend.core.decision.timeframes import analyze_completed_weeks


def bar(day, price, volume=100):
    return {'date': day, 'open': price, 'high': price + 1, 'low': price - 1,
            'close': price + 0.5, 'volume': volume}


def calendar_weeks(count):
    monday = date(2025, 1, 6)
    return [(monday + timedelta(days=7 * week + day)).isoformat()
            for week in range(count) for day in range(5)]


def context(sessions, rows, cutoff, *, coverage_start=None, suspended=(), discontinuities=()):
    return analyze_completed_weeks(sessions=sessions, active_bars=rows, suspended_sessions=suspended,
                                   discontinuities=discontinuities, coverage_start=coverage_start or sessions[0],
                                   cutoff=cutoff)


def test_short_week_is_known_at_its_actual_last_session():
    sessions = ['2025-09-29', '2025-09-30', '2025-10-09', '2025-10-10', '2025-10-13']
    rows = [bar(day, price, volume) for day, price, volume in zip(sessions, [10, 12, 30, 9], [110, 200, 500, 400])]
    before = context(sessions, rows, '2025-09-29')
    assert before['bars'] == []
    assert before['context'] == {'completed_through': None, 'scheduled_completion': '2025-09-30',
                                 'skipped_weeks': [], 'trend': 'insufficient', 'status': 'unavailable'}

    completed = context(sessions, rows, '2025-09-30')
    assert completed['bars'] == [{
        'date': '2025-09-30', 'week_start': '2025-09-29', 'first_trade_date': '2025-09-29',
        'last_trade_date': '2025-09-30', 'open': 10, 'high': 13, 'low': 9, 'close': 12.5, 'volume': 310,
    }]
    assert completed['context']['completed_through'] == '2025-09-30'
    assert completed['context']['status'] == 'insufficient'
    later = context(sessions, rows, '2025-10-09')
    assert later['bars'] == completed['bars']
    assert later['context']['scheduled_completion'] == '2025-10-10'


def test_midweek_start_and_calendar_terminal_week_are_conservative():
    sessions = calendar_weeks(3)
    rows = [bar(day, price) for price, day in enumerate(sessions, 10) if day >= sessions[2]]
    result = context(sessions, rows, sessions[-1], coverage_start=sessions[2])
    assert [row['date'] for row in result['bars']] == [sessions[9]]
    assert result['context']['scheduled_completion'] is None
    assert result['context']['skipped_weeks'] == [
        {'week_start': sessions[0], 'scheduled_completion': sessions[4], 'reason': 'partial_coverage'},
    ]


def test_suspended_session_adds_no_prices_and_does_not_advance_completion():
    sessions = calendar_weeks(2)
    suspended = [sessions[1], sessions[4]]
    rows = [bar(day, price) for day, price in zip(sessions, [8, 100, 14, 10]) if day not in suspended]

    assert context(sessions, rows, sessions[3], suspended=suspended)['bars'] == []
    result = context(sessions, rows, sessions[4], suspended=suspended)
    assert result['bars'] == [{
        'date': sessions[4], 'week_start': sessions[0], 'first_trade_date': sessions[0],
        'last_trade_date': sessions[3], 'open': 8, 'high': 15, 'low': 7, 'close': 10.5, 'volume': 300,
    }]
    assert result['context']['completed_through'] == sessions[4]


@pytest.mark.parametrize('kind', ['missing', 'zero_volume', 'reference_break'])
def test_interrupted_week_clears_context_even_before_week_end(kind):
    sessions = calendar_weeks(6)
    broken = sessions[17]
    rows = [bar(day, price, volume=0 if day == broken and kind == 'zero_volume' else 100)
            for price, day in enumerate(sessions, 10) if day != broken or kind != 'missing']
    discontinuities = [broken] if kind == 'reference_break' else []

    prior = context(sessions, rows, sessions[16], discontinuities=discontinuities)
    assert len(prior['bars']) == 3
    assert prior['context']['skipped_weeks'] == []

    interrupted = context(sessions, rows, broken, discontinuities=discontinuities)
    assert interrupted['bars'] == []
    assert all(not layer for layer in interrupted['structures'].values())
    assert interrupted['context']['trend'] == 'insufficient'
    assert interrupted['context']['completed_through'] is None
    assert interrupted['context']['skipped_weeks'] == [
        {'week_start': sessions[15], 'scheduled_completion': sessions[19], 'reason': 'discontinuity'},
    ]

    restarted = context(sessions, rows, sessions[24], discontinuities=discontinuities)
    assert [row['date'] for row in restarted['bars']] == [sessions[24]]
    assert restarted['context']['completed_through'] == sessions[24]


def test_exchange_holiday_week_and_full_instrument_halt_have_distinct_effects():
    full = calendar_weeks(5)
    sessions = full[:5] + full[10:]
    suspended = full[15:20]
    rows = [bar(day, 10) for day in sessions if day not in suspended]

    result = context(sessions, rows, full[14], suspended=suspended)
    assert [row['date'] for row in result['bars']] == [full[4], full[14]]
    assert result['context']['skipped_weeks'] == []

    halted = context(sessions, rows, full[19], suspended=suspended)
    assert halted['context']['skipped_weeks'] == [
        {'week_start': full[15], 'scheduled_completion': full[19], 'reason': 'fully_suspended'},
    ]
    assert halted['bars'] == []


def test_each_cutoff_matches_only_the_rows_and_breaks_known_through_that_date():
    prices = [10, 16, 8, 19, 9, 22, 11, 26, 13, 29, 15]
    sessions = calendar_weeks(len(prices) + 1)
    rows = [bar(day, prices[index // 5]) for index, day in enumerate(sessions[:5 * len(prices)])]

    ready = context(sessions, rows, sessions[34])
    assert ready['context']['trend'] == 'rising'
    assert ready['context']['status'] == 'ready'
    assert ready['context']['completed_through'] == sessions[34]

    break_day = sessions[37]
    for cutoff in sessions[:len(rows)]:
        full_input = context(sessions, rows, cutoff, discontinuities=[break_day])
        prefix = context(sessions, [row for row in rows if row['date'] <= cutoff], cutoff,
                         discontinuities=[break_day] if break_day <= cutoff else [])
        assert full_input == prefix
        assert all(row['date'] <= cutoff for row in prefix['bars'])
        for layer in prefix['structures'].values():
            assert all(item['confirmed_date'] is None or item['confirmed_date'] <= cutoff for item in layer)
