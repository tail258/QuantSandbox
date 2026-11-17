"""Retrospective daily decision event study on one instrument and one fixed snapshot."""
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from math import isclose, isfinite
from operator import ge, gt, le, lt
from statistics import fmean, median, quantiles

from backend.core.decision import ANCHOR_MAX_AGE, RULE_VERSION, analyze_daily


PROTOCOL = 'stock-decision-event-study-v1'
MAX_OBSERVATIONS = 252
MAX_HOLDING_SESSIONS = 20
_RECENT_REFERENCE_DAYS = 10
_BAR_FIELDS = ('date', 'open', 'high', 'low', 'close', 'volume')
_ENTRY = 'review_entry_after_close'
_EXIT = 'review_exit_if_holding'
_KINDS = {'breakout': _ENTRY, 'retest': _ENTRY, 'support_failure': _EXIT}
_COMPARE = {'gt': gt, 'gte': ge, 'lt': lt, 'lte': le}
_BPS = Decimal(10_000)


def _iso(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Use an ISO calendar date (YYYY-MM-DD)') from exc
    if parsed.isoformat() != value:
        raise ValueError('Use an ISO calendar date (YYYY-MM-DD)')
    return value


def _ordered_dates(values):
    dates = [_iso(day) for day in values]
    if dates != sorted(set(dates)):
        raise ValueError('Daily dates must be unique and ascending')
    return dates


def _decimal(value):
    try:
        number = Decimal(str(value))
        if number.is_finite() and isfinite(float(number)):
            return number
    except (InvalidOperation, ValueError, OverflowError):
        pass
    raise ValueError('Use finite numeric evaluation inputs')


def _price(value):
    return type(value) in (int, float) and 0 < value < float('inf')


def _bar_issue(row):
    if row is None:
        return 'missing_bar'
    if row.get('is_suspended') is True:
        return 'suspended'
    if row.get('is_suspended') is not False:
        return 'trading_status_unverified'
    if not all(_price(row.get(field)) for field in _BAR_FIELDS[1:]):
        return 'invalid_ohlcv'
    if not row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high']:
        return 'invalid_ohlcv'
    return None


def _reference_issue(previous, current):
    if not previous or not _price(previous.get('close')) or not _price(current.get('prev_close')):
        return 'reference_unverified'
    if not isclose(current['prev_close'], previous['close'], rel_tol=1e-6, abs_tol=0.00011):
        return 'reference_discontinuity'
    return None


def _trigger(scenario, observation):
    return all(_COMPARE[condition['comparison']](observation[condition['field']], condition['value'])
               for condition in scenario['conditions'])


def _on_grid(price, tick):
    return price == (price / tick).to_integral_value() * tick


def _round_to_tick(price, tick, rounding):
    return (price / tick).to_integral_value(rounding=rounding) * tick


def _entry_mark_is_in_plan(scenario, price):
    # A price outside the previously published close-price bracket no longer
    # represents the plan, even if the completed observation triggered it.
    return all(_COMPARE[item['comparison']](price, _decimal(item['value']))
               for item in scenario['conditions'] if item['field'] == 'close')


def _label(index, sessions, by_date, end, holding_sessions, tick, observation):
    exit_index = index + 1 + holding_sessions
    if exit_index >= len(sessions) or sessions[exit_index] > end:
        return None, 'outcome_after_cutoff'
    entry_date = sessions[index + 1]
    exit_date = sessions[exit_index]
    previous = observation
    for day in sessions[index + 1:exit_index + 1]:
        current = by_date.get(day)
        if not current:
            return None, 'outcome_missing_bar'
        if current.get('is_suspended') is True:
            return None, 'outcome_suspended'
        if current.get('is_suspended') is not False:
            return None, 'outcome_trading_status_unverified'
        if issue := _reference_issue(previous, current):
            return None, 'outcome_' + issue
        previous = current
    # Daily trading status is retrospective. This establishes two observed
    # prices only; it does not establish opening auction access or liquidity.
    opens = [by_date[day].get('open') for day in (entry_date, exit_date)]
    if not all(_price(price) for price in opens):
        return None, 'outcome_open_unavailable'
    entry_open, exit_open = map(_decimal, opens)
    if not all(_on_grid(price, tick) for price in (entry_open, exit_open)):
        return None, 'outcome_open_off_tick'
    return (entry_date, exit_date, entry_open, exit_open), None


def _scored_observation(scenario, mark, observation, tick, slippage, cost):
    entry_date, exit_date, entry_open, exit_open = mark
    stressed_return = None
    if scenario['action'] == _ENTRY:
        stressed_entry = _round_to_tick(entry_open * (1 + slippage), tick, ROUND_CEILING)
        if not _entry_mark_is_in_plan(scenario, entry_open) or not _entry_mark_is_in_plan(scenario, stressed_entry):
            return None, 'entry_open_outside_plan'
        stressed_exit = _round_to_tick(exit_open * (1 - slippage), tick, ROUND_FLOOR)
        if stressed_exit > 0:
            stressed_return = float(stressed_exit / stressed_entry - 1 - cost)
    return {**observation, 'entry_reference_date': entry_date, 'exit_reference_date': exit_date,
            'entry_open': float(entry_open), 'exit_open': float(exit_open),
            'market_return': float(exit_open / entry_open - 1), 'stressed_return': stressed_return}, None


def _stats(observations):
    values = [item['market_return'] for item in observations]
    stressed = [item['stressed_return'] for item in observations if item['stressed_return'] is not None]
    quartiles = quantiles(values, n=4, method='inclusive') if len(values) >= 4 else None
    return {'count': len(values), 'mean_return': fmean(values) if values else None,
            'median_return': median(values) if values else None,
            'first_quartile': quartiles[0] if quartiles else None,
            'third_quartile': quartiles[2] if quartiles else None,
            'stressed_count': len(stressed), 'stressed_mean_return': fmean(stressed) if stressed else None}


def _summary(group):
    observations = group['observations']
    events = _stats([item for item in observations if item['triggered']])
    comparison = _stats([item for item in observations if not item['triggered']])
    difference = events['mean_return'] - comparison['mean_return'] if events['count'] and comparison['count'] else None
    return {**group, 'excluded': dict(group['excluded']), 'events': events,
            'comparison': comparison, 'mean_difference': difference}


def _observation_reason(previous, current, active, gaps, reference_breaks):
    if issue := _bar_issue(previous):
        return 'prior_' + issue
    if issue := _bar_issue(current):
        return 'observation_' + issue
    if issue := _reference_issue(previous, current):
        return 'observation_' + issue
    lookback = active[max(0, len(active) - ANCHOR_MAX_AGE)]['date']
    if gaps and gaps[-1] >= lookback:
        return 'recent_session_gap'
    recent = (date.fromisoformat(previous['date']) - timedelta(days=_RECENT_REFERENCE_DAYS)).isoformat()
    if reference_breaks and reference_breaks[-1] >= recent:
        return 'recent_reference_discontinuity'
    return None


def _record_scenarios(groups, scenarios, plan, current, mark, mark_reason, tick, slippage, cost):
    for scenario in scenarios:
        group = groups[scenario['kind']]
        triggered = _trigger(scenario, current)
        observation = {'plan_as_of': plan['as_of'], 'observation_date': current['date'], 'triggered': triggered,
                       'conditions': scenario['conditions']}
        group['offered'] += 1
        group['triggered' if triggered else 'untriggered'] += 1
        if mark_reason:
            outcome, reason = None, mark_reason
        else:
            outcome, reason = _scored_observation(scenario, mark, observation, tick, slippage, cost)
        if reason:
            group['excluded'][reason] += 1
            group['unscored'].append({**observation, 'reason': reason})
        else:
            group['observations'].append(outcome)


def evaluate_daily(rows, *, sessions, history_start, start, end, price_tick, holding_sessions=5,
                   slippage_bps=5, round_trip_cost_bps=10) -> dict:
    """Compare forward price references on triggered and untriggered rule days.

    `rows` are raw daily observations with explicit `is_suspended` and a sourced
    `prev_close`. `sessions` is a caller-verified exchange calendar. Keep the
    requested range and listing date outside this pure evaluator, and pass the
    later of those dates as `history_start`. `end` is a strict outcome cutoff.
    """
    history_start, start, end = map(_iso, (history_start, start, end))
    if not history_start <= start <= end:
        raise ValueError('Evaluation dates must follow the verified history start')
    if type(holding_sessions) is not int or not 1 <= holding_sessions <= MAX_HOLDING_SESSIONS:
        raise ValueError(f'Holding sessions must be an integer from 1 to {MAX_HOLDING_SESSIONS}')
    tick, slippage, cost = map(_decimal, (price_tick, slippage_bps, round_trip_cost_bps))
    if tick not in (Decimal('0.01'), Decimal('0.001')):
        raise ValueError('Price tick must be 0.01 (stock) or 0.001 (ETF)')
    if not (0 <= slippage < _BPS and 0 <= cost < _BPS):
        raise ValueError('Cost assumptions must be in [0, 10000) bps')
    sessions = [day for day in _ordered_dates(sessions) if day >= history_start]
    dates = _ordered_dates(row['date'] for row in rows)
    by_date = dict(zip(dates, rows, strict=True))
    scheduled = sum(start <= day <= end for day in sessions)
    if scheduled > MAX_OBSERVATIONS:
        raise ValueError(f'Evaluate no more than {MAX_OBSERVATIONS} observation sessions at a time')

    groups = {kind: {'kind': kind, 'action': action, 'offered': 0, 'triggered': 0, 'untriggered': 0,
                     'observations': [], 'unscored': [], 'excluded': Counter()} for kind, action in _KINDS.items()}
    excluded = Counter()
    observation_exclusions = []
    active = []
    gaps = []
    reference_breaks = []
    previous = None
    for index, day in enumerate(sessions):
        if day > end:
            break
        current = by_date.get(day)
        if day >= start:
            reason = (_observation_reason(previous, current, active, gaps, reference_breaks) if index
                      else 'prior_session_unavailable')
            if not reason:
                plan = analyze_daily(active, observation_session=day, data_issues=(),
                                     discontinuities=[*gaps, *reference_breaks], price_tick=str(tick))['plan']
                scenarios = [item for item in plan['scenarios'] if item['kind'] in groups]
                if scenarios:
                    mark, mark_reason = _label(index, sessions, by_date, end, holding_sessions, tick, current)
                    _record_scenarios(groups, scenarios, plan, current, mark, mark_reason, tick,
                                      slippage / _BPS, cost / _BPS)
                else:
                    reason = next(iter(plan['data_issues']), 'no_eligible_rule')
            if reason:
                excluded[reason] += 1
                observation_exclusions.append({'date': day, 'reason': reason})

        issue = _bar_issue(current)
        if issue in (None, 'suspended') and previous is not None and _reference_issue(previous, current):
            reference_breaks.append(day)
        if issue is None:
            active.append({key: current[key] for key in _BAR_FIELDS})
        elif issue != 'suspended':
            gaps.append(day)
        previous = current

    return {'protocol': PROTOCOL, 'rule_version': RULE_VERSION, 'regime': 'retrospective_single_snapshot',
            'start': start, 'end': end, 'holding_sessions': holding_sessions,
            'assumptions': {'price_tick': float(tick), 'slippage_bps': float(slippage),
                            'round_trip_cost_bps': float(cost), 'execution': 'unverified_open_reference',
                            'earliest_entry': 'next_session_open', 'earliest_exit': 'session_after_entry_open',
                            'comparison': 'eligible_same_scenario_not_triggered'},
            'counts': {'scheduled_observations': scheduled, 'evaluated_observations': scheduled - sum(excluded.values()),
                       'excluded_observations': sum(excluded.values())},
            'exclusions': dict(excluded), 'observation_exclusions': observation_exclusions,
            'scenarios': [_summary(group) for group in groups.values()],
            'caveats': ['historical_revision_vintages_unverified', 'opening_auction_fills_and_limits_unverified',
                        'raw_price_returns_only', 'overlapping_windows_not_independent',
                        'comparison_is_conditional_and_descriptive', 'support_failure_is_market_return_without_shorting',
                        'costs_are_sensitivity_assumptions', 'single_instrument_in_sample']}
