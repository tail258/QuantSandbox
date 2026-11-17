from datetime import date, timedelta

import pytest

from backend.core.decision.evaluation import evaluate_daily


@pytest.fixture
def market():
    rows = []
    session = date(2025, 1, 1)

    def append(close, *, opening=None, high=None, low=None, volume=1_000):
        nonlocal session
        while session.weekday() >= 5:
            session += timedelta(days=1)
        rows.append({'date': session.isoformat(), 'open': close if opening is None else opening,
                     'high': round(close + .2, 2) if high is None else high,
                     'low': round(close - .2, 2) if low is None else low,
                     'close': close, 'volume': volume, 'is_suspended': False,
                     'prev_close': rows[-1]['close'] if rows else close})
        session += timedelta(days=1)

    vertices = [105, 96, 180, 105, 145, 109, 118, 112]
    for left, right in zip(vertices, vertices[1:]):
        for offset in range(5):
            append(round(left + (right - left) * offset / 5, 2))
    append(118, opening=114, high=118.1, low=113)
    append(121, opening=120, high=122, low=116, volume=1_800)
    append(121, opening=121, high=122, low=120, volume=1_300)
    append(124, opening=124, high=126, low=123, volume=1_300)
    append(120, opening=123, high=126, low=118)
    return rows, [row['date'] for row in rows]


def run(rows, sessions, *, start=None, end=None, **options):
    arguments = dict(sessions=sessions, history_start=sessions[0], start=start or sessions[35],
                     end=end or sessions[-1], price_tick='.01', holding_sessions=1)
    return evaluate_daily(rows, **(arguments | options))


def group(report, kind='breakout'):
    return next(item for item in report['scenarios'] if item['kind'] == kind)


def test_existing_rule_triggers_from_prior_plan_with_aligned_price_comparison(market):
    rows, sessions = market
    report = run(rows, sessions)
    assert report['regime'] == 'retrospective_single_snapshot'
    assert report['assumptions']['execution'] == 'unverified_open_reference'
    breakout = group(report)
    assert (breakout['offered'], breakout['triggered'], breakout['untriggered']) == (2, 1, 1)
    control, event = breakout['observations']
    assert event['triggered'] is True and control['triggered'] is False
    assert event['conditions'] == [
        {'field': 'close', 'comparison': 'gt', 'value': 118.2},
        {'field': 'close', 'comparison': 'lte', 'value': 123.36},
        {'field': 'volume', 'comparison': 'gte', 'value': 1_250},
    ]
    assert [event[key] for key in ('plan_as_of', 'observation_date', 'entry_reference_date', 'exit_reference_date')] == sessions[35:39]
    assert (event['entry_open'], event['exit_open']) == (121, 124)
    assert breakout['events']['count'] == breakout['comparison']['count'] == 1
    assert breakout['events']['mean_return'] == pytest.approx(124 / 121 - 1)
    assert breakout['events']['stressed_mean_return'] == pytest.approx(123.93 / 121.07 - 1 - .001)
    assert breakout['comparison']['mean_return'] == pytest.approx(121 / 120 - 1)
    assert breakout['mean_difference'] == pytest.approx(124 / 121 - 121 / 120)
    assert breakout['events']['first_quartile'] is None
    assert 'overlapping_windows_not_independent' in report['caveats']


def test_observation_volume_can_trigger_only_fixed_threshold_and_later_bars_do_not_change_it(market):
    rows, sessions = market
    qualifying = group(run(rows, sessions))['observations'][1]
    rows[36]['volume'] = 1_200
    untriggered = group(run(rows, sessions))['observations'][1]
    assert qualifying['conditions'] == untriggered['conditions']
    assert qualifying['triggered'] and not untriggered['triggered']

    prefix_report = run(rows[:39], sessions[:39], end=sessions[38])
    rows[39].update(open=1.01, close=200, high=900, low=1.01, volume=10_000_000)
    assert run(rows, sessions, end=sessions[38]) == prefix_report


def test_open_reference_is_not_conditioned_on_same_day_total_volume_or_extremes(market):
    rows, sessions = market
    before = group(run(rows, sessions))['observations'][1]
    rows[37].update(volume=0, low=.1, high=400)
    rows[38].update(volume=0, low=.1, high=400)
    assert group(run(rows, sessions))['observations'][1] == before


@pytest.mark.parametrize(('change', 'reason'), [
    ({'open': 127, 'high': 127}, 'entry_open_outside_plan'),
    ({'open': 118.15, 'low': 118}, 'entry_open_outside_plan'),
    ({'open': 123.36, 'high': 124}, 'entry_open_outside_plan'),
    ({'open': 121.005}, 'outcome_open_off_tick'),
    ({'prev_close': 101}, 'outcome_reference_discontinuity'),
    ({'prev_close': None}, 'outcome_reference_unverified'),
    ({'is_suspended': True}, 'outcome_suspended'),
    ({'is_suspended': None}, 'outcome_trading_status_unverified'),
])
def test_unusable_open_excludes_trigger_without_shifting_reference_date(market, change, reason):
    rows, sessions = market
    rows[37].update(change)
    breakout = group(run(rows, sessions))
    assert breakout['triggered'] == 1
    assert breakout['events']['count'] == 0
    assert breakout['events']['mean_return'] is None and breakout['mean_difference'] is None
    event = next(item for item in breakout['unscored'] if item['triggered'])
    assert event['reason'] == reason
    assert event['observation_date'] == sessions[36]


def test_missing_session_and_boundary_exclude_labels_even_when_later_bars_exist(market):
    rows, sessions = market
    breakout = group(run(rows[:37] + rows[38:], sessions))
    assert next(item for item in breakout['unscored'] if item['triggered'])['reason'] == 'outcome_missing_bar'
    missing_observation = run(rows[:36] + rows[37:], sessions)
    assert {'date': sessions[36], 'reason': 'observation_missing_bar'} in missing_observation['observation_exclusions']
    assert {'date': sessions[38], 'reason': 'recent_session_gap'} in missing_observation['observation_exclusions']
    cutoff = group(run(rows, sessions, end=sessions[37]))
    assert next(item for item in cutoff['unscored'] if item['triggered'])['reason'] == 'outcome_after_cutoff'


def test_reference_change_on_a_halt_remains_a_break_after_resumption(market):
    rows, sessions = market
    for row in rows[34:]:
        for field in ('open', 'high', 'low', 'close', 'prev_close'):
            row[field] /= 2
    halted_price = rows[34]['prev_close']
    rows[34].update(is_suspended=True, volume=0, open=halted_price, high=halted_price,
                    low=halted_price, close=halted_price)
    rows[35]['prev_close'] = halted_price
    report = run(rows, sessions)
    assert {'date': sessions[35], 'reason': 'prior_suspended'} in report['observation_exclusions']
    assert {'date': sessions[36], 'reason': 'recent_reference_discontinuity'} in report['observation_exclusions']


def test_support_failure_reports_signed_market_return_without_short_or_cost_model(market):
    rows, sessions = market
    rows[35].update(open=113, high=114, low=105, close=106)
    rows[36].update(open=106, high=107, low=103, close=104, prev_close=106)
    rows[37].update(open=103, high=104, low=101, close=102, prev_close=104)
    rows[38]['prev_close'] = 102
    result = group(run(rows, sessions), 'support_failure')
    assert result['action'] == 'review_exit_if_holding'
    assert result['events']['count'] == 1
    assert result['events']['mean_return'] == pytest.approx(103 / 106 - 1)
    assert result['events']['stressed_count'] == 0
    assert result['events']['stressed_mean_return'] is None


def test_requires_minimum_later_exit_and_bounds_requested_observations(market):
    rows, sessions = market
    with pytest.raises(ValueError, match='Holding sessions'):
        run(rows, sessions, holding_sessions=0)
    oversized = [(date(2025, 1, 1) + timedelta(days=day)).isoformat() for day in range(253)]
    with pytest.raises(ValueError, match='252'):
        run([], oversized, start=oversized[0])
