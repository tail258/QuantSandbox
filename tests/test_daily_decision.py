from datetime import date, timedelta

import pytest

from backend.core.decision import analyze_daily


def waves(vertices, steps=5):
    bars = []
    for start, end in zip(vertices, vertices[1:]):
        for offset in range(steps):
            price = round(start + (end - start) * offset / steps, 4)
            stamp = date(2025, 1, 1) + timedelta(days=len(bars))
            bars.append({'date': stamp.isoformat(), 'open': price, 'high': price + .2,
                         'low': price - .2, 'close': price, 'volume': 1_000.0})
    return bars


def test_breakout_exposes_anchors_volume_and_risk_ceiling_instead_of_a_buy_now_signal():
    bars = waves([105, 96, 180, 105, 145, 109, 118, 112])
    bars[-1]['volume'] = 2_000.0
    out = analyze_daily(bars, observation_session='2025-02-05')
    plan = out['plan']
    assert plan['stance'] == 'watch'
    assert plan['level_basis'] == 'confirmed_fractals'
    assert plan['as_of'] == '2025-02-04'
    assert plan['volume']['observed_ratio'] == 2.0
    assert plan['volume']['reference'] == 1_050.0
    support, resistance, target = plan['levels']
    assert [level['price'] for level in plan['levels']] == pytest.approx([108.8, 118.2, 145.2])
    known = {item['id']: item for item in out['structures']['fractals']}
    for level in plan['levels']:
        proof = level['evidence']
        assert known[proof['id']]['status'] == 'confirmed'
        assert proof['geometry_date'] < proof['confirmed_date'] <= plan['as_of']
    breakout, invalidation, fallback = plan['scenarios']
    assert breakout['kind'] == 'breakout'
    assert breakout['action'] == 'review_entry_after_close'
    trigger, ceiling, volume = breakout['conditions']
    assert trigger == {'field': 'close', 'comparison': 'gt', 'value': resistance['price']}
    assert (target['price'] - ceiling['value']) / (ceiling['value'] - support['price']) == pytest.approx(1.5)
    assert ceiling['value'] == 123.36
    assert volume == {'field': 'volume', 'comparison': 'gte', 'value': 1313}
    assert invalidation['action'] == 'review_exit_if_holding'
    assert invalidation['conditions'] == [{'field': 'close', 'comparison': 'lt', 'value': support['price']}]
    assert fallback['action'] == 'watch'


def test_every_historical_cutoff_matches_independent_prefix_with_unrelated_future_prices():
    bars = waves([105, 96, 180, 105, 145, 109, 118, 112, 180, 80, 130, 60, 167], steps=6)
    for idx, bar in enumerate(bars):
        future_discontinuity = (bars[idx + 1]['date'],) if idx + 1 < len(bars) else ()
        next_date = (date.fromisoformat(bar['date']) + timedelta(days=1)).isoformat()
        from_full = analyze_daily(bars, cutoff=bar['date'], observation_session=next_date,
                                  discontinuities=future_discontinuity)
        assert from_full == analyze_daily(bars[:idx + 1], observation_session=next_date)
        for level in from_full['plan']['levels']:
            assert level['evidence']['confirmed_date'] <= bar['date']


def test_stale_or_discontinuous_input_cannot_offer_conditional_orders():
    bars = waves([105, 96, 180, 105, 145, 109, 118, 112])
    stale = analyze_daily(bars, observation_session='2025-02-05', data_issues=('stale_quotes',))['plan']
    assert stale['levels']
    assert stale['data_issues'] == ['stale_quotes']
    assert [s['kind'] for s in stale['scenarios']] == ['otherwise']
    broken = analyze_daily(bars, observation_session='2025-02-05',
                           discontinuities=(bars[-3]['date'],))['plan']
    assert not broken['levels']
    assert broken['watch_reason'] == 'unverified_input'
    assert 'volume_history_short' in broken['data_issues']
    assert [s['action'] for s in broken['scenarios']] == ['watch']


def test_no_entry_when_first_overhead_structure_leaves_too_little_room():
    bars = waves([105, 96, 146, 105, 124, 109, 118, 112])
    plan = analyze_daily(bars, observation_session='2025-02-05')['plan']
    assert plan['watch_reason'] == 'no_clear_entry_room'
    assert [s['kind'] for s in plan['scenarios']] == ['support_failure', 'otherwise']


def test_retest_requires_a_real_contact_and_keeps_invalidation_distinct():
    bars = waves([105, 96, 180, 105, 145, 109, 118, 112])
    bars.append({'date': '2025-02-05', 'open': 119.0, 'high': 121.8,
                 'low': 116.0, 'close': 121.0, 'volume': 1800.0})
    plan = analyze_daily(bars, observation_session='2025-02-06')['plan']
    assert plan['phase'] == 'above_resistance'
    retest = plan['scenarios'][0]
    assert retest['kind'] == 'retest'
    assert retest['conditions'][:3] == [
        {'field': 'low', 'comparison': 'lte', 'value': 118.2},
        {'field': 'low', 'comparison': 'gt', 'value': 113.0},
        {'field': 'close', 'comparison': 'gt', 'value': 118.2},
    ]


def test_volume_warmup_does_not_cross_known_input_discontinuity():
    bars = waves([105, 96, 180, 105, 145, 109, 118, 112])
    missing = bars.pop(17)['date']
    plan = analyze_daily(bars, observation_session='2025-02-05', discontinuities=(missing,))['plan']
    assert 'volume_history_short' in plan['data_issues']
    assert not plan['volume']['reference']
    assert [s['kind'] for s in plan['scenarios']] == ['otherwise']


def test_breakout_interval_must_contain_a_legal_price_for_that_instrument():
    bars = waves([10.5, 9.6, 18.0, 10.5, 11.88, 11.80, 11.83, 11.80])
    for bar in bars:
        # The same price observations on stock and ETF tick grids.
        price = round(bar['close'], 2)
        bar.update(open=price, low=price, high=price, close=price)
    stock = analyze_daily(bars, observation_session='2025-02-05', price_tick='0.01')['plan']
    etf = analyze_daily(bars, observation_session='2025-02-05', price_tick='0.001')['plan']
    assert stock['watch_reason'] == 'no_clear_entry_room'
    assert etf['scenarios'][0]['kind'] == 'breakout'
    assert etf['scenarios'][0]['conditions'][1]['value'] == 11.832
