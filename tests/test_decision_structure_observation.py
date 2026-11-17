from datetime import date, timedelta

import pytest

from backend.core.chan import recognize_daily
from backend.core.decision.structure_observation import observe_center_retests


def waves(vertices):
    prices = [start + (end - start) * offset / 5 for start, end in zip(vertices, vertices[1:])
              for offset in range(5)] + [vertices[-1]]
    return [
        {'date': (date(2020, 1, 1) + timedelta(days=index)).isoformat(), 'open': value,
         'high': value + .02, 'low': value - .02, 'close': value, 'volume': 100}
        for index, value in enumerate(prices)
    ]


def departure_vertices():
    return [13, 10, 16, 12, 20, 14, 17, 9, 15, 11, 18, 12, 15, 10.5, 12, 3, 7, 4, 6,
            1, 5, 2, 6, 3, 5, .8, 4, 2, 5, 3, 4, .5, 3, 1, 4, 2, 3, .3, 2]


@pytest.mark.parametrize(('side', 'edge', 'extreme'), [('below', 9.98, 6.02), ('above', 11.02, 14.98)])
def test_departure_and_retest_are_observable_only_after_both_confirm(side, edge, extreme):
    vertices = departure_vertices()
    bars = waves(vertices if side == 'below' else [21 - value for value in vertices])
    for index in (71, 72, 95, 110, 116, 130):
        assert observe_center_retests(bars[:index + 1]) == []

    observation, = observe_center_retests(bars[:132])
    assert observation['side'] == side
    assert observation['edge'] == edge
    assert observation['outside_extreme'] == extreme
    assert observation['center']['confirmed_date'] == bars[71]['date']
    assert observation['first_exit_date'] == bars[72]['date']
    assert observation['departure']['confirmed_date'] == bars[116]['date']
    assert observation['geometry_date'] == bars[110]['date']
    assert observation['retest']['confirmed_date'] == observation['available_date'] == bars[131]['date']
    assert observation['status'] == 'intact'


@pytest.mark.parametrize('touch_at', [103, 113])
def test_raw_touch_rejects_retest_even_if_v1_confirms_same_segment(touch_at):
    bars = waves(departure_vertices())[:132]
    bars[touch_at]['high'] = 9.98
    replay = recognize_daily(bars)
    center, = replay['structures']['centers']
    assert center['phase'] == 'closed'
    assert center['closed_by'] == 'segment:95'
    assert observe_center_retests(bars, replay=replay) == []


def test_reject_crossing_before_the_center_was_confirmed_and_center_extension():
    earlier_crossing = departure_vertices()
    earlier_crossing[13:15] = [2, 6]
    bars = waves(earlier_crossing)[:132]
    assert recognize_daily(bars)['structures']['centers'][0]['phase'] == 'closed'
    assert observe_center_retests(bars) == []

    extension = waves([13, 10, 16, 12, 20, 14, 17, 9, 15, 11, 18, 12, 15, 8, 14, 10, 17,
                       11, 14, 7, 13, 9, 16, 10, 13, 6])
    center, = recognize_daily(extension)['structures']['centers']
    assert center['phase'] == 'active' and len(center['segment_ids']) > 3
    assert observe_center_retests(extension) == []


def test_later_crossing_or_unknown_gap_changes_status_only_after_it_happens():
    bars = waves(departure_vertices())[:135]
    bars[133]['high'] = 9.98
    first, = observe_center_retests(bars[:132])
    invalidated, = observe_center_retests(bars)
    gap = bars[132]['date']
    uncertain, = observe_center_retests(bars, discontinuities=(gap,))
    assert invalidated == {**first, 'status': 'reentered', 'status_date': bars[133]['date']}
    assert uncertain == {**first, 'status': 'unverifiable', 'status_date': gap}


def test_break_before_proof_rejects_observation_and_future_breaks_never_change_history():
    bars = waves(departure_vertices())
    break_date = bars[103]['date']
    full = observe_center_retests(bars)
    assert observe_center_retests(bars, discontinuities=(break_date,)) == []
    for index in range(len(bars)):
        prefix = bars[:index + 1]
        actual = observe_center_retests(prefix, discontinuities=(bars[-1]['date'],))
        expected = [item for item in full if item['available_index'] <= index]
        assert [(item['id'], item['available_date']) for item in actual] == [
            (item['id'], item['available_date']) for item in expected
        ]
    with pytest.raises(ValueError, match='same daily prefix'):
        observe_center_retests(bars[:132], replay=recognize_daily(bars))
