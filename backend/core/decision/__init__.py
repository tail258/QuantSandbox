"""Causal daily structure and conditional observation rules; no order or fill model."""
from bisect import bisect_right
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from math import ceil
from statistics import fmean

from backend.core.chan import recognize_daily

RULE_VERSION = 'daily-structure-plan-v1'
VOLUME_WINDOW = 20
BREAKOUT_MULTIPLE = 1.25
ANCHOR_MAX_AGE = 80
TARGET_MAX_AGE = 180
MIN_ROOM_TO_RISK = 1.5


def _level(role, price, layer, structure, bars):
    index = structure.get('index', structure['end_index'])
    return {'role': role, 'price': price, 'evidence': {
        'layer': layer, 'id': structure['id'], 'index': index,
        'geometry_date': bars[index]['date'], 'confirmed_date': structure['confirmed_date'],
    }}


def _confirmed(items, as_of_index):
    return [item for item in items if item['status'] == 'confirmed'
            and item['confirmed_index'] is not None and item['confirmed_index'] <= as_of_index]


def _direction(tops, bottoms):
    if len(tops) < 2 or len(bottoms) < 2:
        return 'insufficient'
    high_change = tops[-1]['price'] - tops[-2]['price']
    low_change = bottoms[-1]['price'] - bottoms[-2]['price']
    if high_change > 0 and low_change > 0:
        return 'rising'
    if high_change < 0 and low_change < 0:
        return 'falling'
    return 'mixed'


def _volume(bars):
    # Today is excluded from today's ratio, but included in the fixed reference for the next session.
    positive = [bar['volume'] for bar in bars[:-1] if bar['volume'] > 0]
    prior = fmean(positive[-VOLUME_WINDOW:]) if len(positive) >= VOLUME_WINDOW else None
    last_volume = bars[-1]['volume']
    with_last = positive + ([last_volume] if last_volume > 0 else [])
    next_reference = fmean(with_last[-VOLUME_WINDOW:]) if len(with_last) >= VOLUME_WINDOW else None
    return {'window': VOLUME_WINDOW, 'multiple': BREAKOUT_MULTIPLE,
            'observed_ratio': last_volume / prior if prior and last_volume > 0 else None,
            'reference': next_reference, 'minimum': ceil(Decimal(str(next_reference)) * Decimal(str(BREAKOUT_MULTIPLE)))
            if next_reference else None}


def _nearby_levels(bars, structures, discontinuities):
    current = len(bars) - 1
    close = bars[-1]['close']
    recent = sorted(_confirmed(structures['fractals'], current), key=lambda item: item['index'])
    eligible = [item for item in recent if current - item['index'] <= TARGET_MAX_AGE
                and not any(item['date'] <= day <= bars[-1]['date'] for day in discontinuities)]
    pivots = [item for item in eligible if current - item['index'] <= ANCHOR_MAX_AGE]
    tops = [item for item in pivots if item['kind'] == 'top']
    bottoms = [item for item in pivots if item['kind'] == 'bottom']
    center = max(_confirmed(structures['centers'], current), key=lambda item: item['start_index'], default=None)
    context = None
    if center:
        lower, upper = center['lower'], center['upper']
        relation = 'below' if close < lower else 'above' if close > upper else 'inside'
        # A distant or closed band is context, not a current entry/exit threshold.
        near = (center['phase'] == 'active' and current - center['end_index'] <= ANCHOR_MAX_AGE
                and relation == 'inside'
                and not any(center['start_date'] <= day <= bars[-1]['date'] for day in discontinuities))
        context = {'id': center['id'], 'relation': relation, 'phase': center['phase'],
                   'lower': lower, 'upper': upper, 'confirmed_date': center['confirmed_date'],
                   'used_for_levels': near}
        if near:
            levels = [_level('support', lower, 'centers', center, bars),
                      _level('resistance', upper, 'centers', center, bars)]
            return levels, 'confirmed_center', context, _direction(tops, bottoms), eligible
    if tops and bottoms and tops[-1]['price'] > bottoms[-1]['price']:
        levels = [_level('support', bottoms[-1]['price'], 'fractals', bottoms[-1], bars),
                  _level('resistance', tops[-1]['price'], 'fractals', tops[-1], bars)]
        return levels, 'confirmed_fractals', context, _direction(tops, bottoms), eligible
    return [], None, context, _direction(tops, bottoms), eligible


def _condition(field, comparison, value):
    return {'field': field, 'comparison': comparison, 'value': value}


def _scenario(kind, action, conditions, evidence=()):
    return {'kind': kind, 'action': action, 'conditions': conditions, 'evidence_roles': list(evidence)}


def analyze_daily(bars, *, cutoff=None, observation_session=None, data_issues=(), discontinuities=(), price_tick='0.01',
                  include_center_observations=False):
    """Analyze only bars available on the requested cutoff (ascending local session dates).

    Calendar freshness, verified instrument, and discontinuities are inputs from the
    immutable market snapshot service. A historical caller must provide the corresponding
    as-of quality context. The returned chart geometry is reconstructed from the same prefix.
    """
    dates = [bar['date'] for bar in bars]
    if dates != sorted(set(dates)):
        raise ValueError('Daily bars must have unique ascending dates')
    if cutoff is not None:
        cutoff = date.fromisoformat(cutoff).isoformat()
        bars = bars[:bisect_right(dates, cutoff)]
    if not bars:
        raise ValueError('No closed daily observations at the selected cutoff')
    as_of = bars[-1]['date']
    if observation_session is not None and date.fromisoformat(observation_session).isoformat() <= as_of:
        raise ValueError('Observation session must follow the analysis cutoff')
    tick = Decimal(price_tick)
    if not tick.is_finite() or tick <= 0:
        raise ValueError('Price tick must be positive and finite')
    replay = recognize_daily(bars)
    structures = replay['structures']
    levels, basis, center, trend, pivots = _nearby_levels(bars, structures, discontinuities)
    latest_break = max((day for day in discontinuities if day <= as_of), default=None)
    volume_bars = [bar for bar in bars if latest_break is None or bar['date'] > latest_break]
    volume = (_volume(volume_bars) if volume_bars else
              {'window': VOLUME_WINDOW, 'multiple': BREAKOUT_MULTIPLE, 'observed_ratio': None,
               'reference': None, 'minimum': None})
    close = bars[-1]['close']
    issues = list(dict.fromkeys(data_issues))
    if observation_session is None:
        issues.append('session_unverified')
    if bars[-1]['volume'] <= 0:
        issues.append('zero_latest_volume')
    if volume['reference'] is None:
        issues.append('volume_history_short')
    issues = list(dict.fromkeys(issues))
    scenarios = []
    phase = 'unresolved'
    if levels:
        support, resistance = (level['price'] for level in levels)
        phase = 'below_support' if close < support else 'above_resistance' if close > resistance else 'inside_range'
        if not issues and phase != 'below_support':
            scenarios.append(_scenario('support_failure', 'review_exit_if_holding',
                                       [_condition('close', 'lt', support)], ('support',)))
            recent_targets = [item for item in pivots if item['kind'] == 'top' and item['price'] > resistance]
            if recent_targets and volume['minimum'] is not None:
                target = min(recent_targets, key=lambda item: (item['price'], -item['index']))
                ratio = Decimal(str(MIN_ROOM_TO_RISK))
                # Round down, so the published inclusive ceiling cannot admit
                # a price above the nominal ratio because of binary floating point.
                nominal_cap = (Decimal(str(target['price'])) + ratio * Decimal(str(support))) / (1 + ratio)
                legal_cap = (nominal_cap / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
                first_breakout = ((Decimal(str(resistance)) / tick).to_integral_value(rounding=ROUND_FLOOR) + 1) * tick
                cap = float(legal_cap)
                if legal_cap >= first_breakout and close <= cap:
                    levels.append(_level('reference_target', target['price'], 'fractals', target, bars))
                    common = [_condition('close', 'gt', resistance), _condition('close', 'lte', cap),
                              _condition('volume', 'gte', volume['minimum'])]
                    if phase == 'inside_range':
                        scenarios.insert(0, _scenario('breakout', 'review_entry_after_close', common,
                                                     ('resistance', 'support', 'reference_target')))
                    else:
                        scenarios.insert(0, _scenario('retest', 'review_entry_after_close', [
                            _condition('low', 'lte', resistance), _condition('low', 'gt', support), *common,
                        ], ('resistance', 'support', 'reference_target')))
    scenarios.append(_scenario('otherwise', 'watch', []))
    watch_reason = ('unverified_input' if issues else 'no_qualified_anchors' if not levels
                    else 'support_already_broken' if phase == 'below_support'
                    else 'await_close_confirmation' if any(s['action'] == 'review_entry_after_close' for s in scenarios)
                    else 'no_clear_entry_room')
    plan = {'rule_version': RULE_VERSION, 'structure_version': replay['algorithm'], 'as_of': as_of,
            'observation_session': observation_session, 'stance': 'watch', 'watch_reason': watch_reason,
            'data_quality': 'limited' if issues else 'checked', 'data_issues': issues,
            'edge_validation': 'unvalidated', 'min_room_to_risk': MIN_ROOM_TO_RISK, 'price_tick': float(tick),
            'trend': trend, 'phase': phase, 'level_basis': basis, 'last_center': center,
            'levels': levels, 'volume': volume, 'scenarios': scenarios}
    result = {'plan': plan, 'bars': bars, 'structures': structures}
    if include_center_observations:
        from backend.core.decision.structure_observation import observe_center_retests
        result['structure_observations'] = observe_center_retests(bars, discontinuities=discontinuities, replay=replay)[-3:]
    return result
