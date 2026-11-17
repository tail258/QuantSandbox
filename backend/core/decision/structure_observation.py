"""Observe confirmed outside-center retests in the fixed daily structure rules."""
from bisect import bisect_left, bisect_right

from backend.core.chan import recognize_daily


RULE_VERSION = 'daily-center-retest-v1'
SEGMENT_EVIDENCE = ('id', 'direction', 'start_index', 'end_index', 'start_date', 'end_date',
                    'start_price', 'end_price', 'confirmed_index', 'confirmed_date', 'confirmation_rule')
CENTER_EVIDENCE = ('id', 'lower', 'upper', 'start_date', 'end_date', 'confirmed_index', 'confirmed_date')


def _outside(price, edge, side):
    return price > edge if side == 'above' else price < edge


def _evidence(center, previous, segments, by_start, bars, frame, breaks):
    if (center['confirmed_index'], center['lower'], center['upper']) != (
            previous['confirmed_index'], previous['lower'], previous['upper']):
        return None
    last_member = segments.get(center['segment_ids'][-1])
    retest = segments.get(center['closed_by'])
    if not last_member or not retest:
        return None
    departure = by_start.get(last_member['end_index'])
    if (not departure or departure['end_index'] != retest['start_index'] or
            departure['end_price'] != retest['start_price'] or
            departure['direction'] == retest['direction'] or
            departure['id'] in center['segment_ids'] or retest['id'] in center['segment_ids']):
        return None
    center_at = center['confirmed_index']
    available = frame['index']
    if not center_at < departure['confirmed_index'] < retest['confirmed_index'] <= available:
        return None
    if not center['lower'] <= departure['start_price'] <= center['upper']:
        return None
    if departure['direction'] == 'up':
        side, edge, exit_field, return_field = 'above', center['upper'], 'high', 'low'
    else:
        side, edge, exit_field, return_field = 'below', center['lower'], 'low', 'high'
    if not _outside(departure['end_price'], edge, side):
        return None
    first_exit = next((i for i in range(departure['start_index'], departure['end_index'] + 1)
                       if _outside(bars[i][exit_field], edge, side)), None)
    if first_exit is None or first_exit <= center_at:
        return None
    first_break = bisect_left(breaks, center['start_date'])
    if first_break < len(breaks) and breaks[first_break] <= frame['date']:
        return None
    prices = [row[return_field] for row in bars[retest['start_index']:available + 1]]
    nearest_price = min(prices) if side == 'above' else max(prices)
    if not _outside(nearest_price, edge, side):
        return None

    return {
        'id': f"center_retest:{center['id']}:{retest['id']}",
        'kind': 'confirmed_center_retest',
        'rule_version': RULE_VERSION,
        'side': side, 'edge': edge, 'outside_extreme': nearest_price,
        'first_exit_date': bars[first_exit]['date'],
        'geometry_index': retest['end_index'], 'geometry_date': retest['end_date'],
        'available_index': available, 'available_date': frame['date'],
        'center': {key: center[key] for key in CENTER_EVIDENCE},
        'departure': {key: departure[key] for key in SEGMENT_EVIDENCE},
        'retest': {key: retest[key] for key in SEGMENT_EVIDENCE},
    }


def _latest_status(observation, bars, breaks):
    latest = bars[-1]['date']
    after_proof = bisect_right(breaks, observation['available_date'])
    gap = breaks[after_proof] if after_proof < len(breaks) and breaks[after_proof] <= latest else None
    side = observation['side']
    field = 'low' if side == 'above' else 'high'
    for row in bars[observation['available_index'] + 1:]:
        if gap and row['date'] >= gap:
            return 'unverifiable', gap
        if not _outside(row[field], observation['edge'], side):
            return 'reentered', row['date']
    return 'intact', latest


def observe_center_retests(bars, *, discontinuities=(), replay=None) -> list[dict]:
    """Return an ordered observation history with status at the last input bar.

    A supplied v1 replay must have been computed from the same frozen bars.
    Shapes can be drawn at their geometry dates. They are first available on
    the replay frame that confirms the center's closure and both legs. Equality
    with the boundary counts as a touch. These observations supply chart context.
    """
    if replay is None:
        replay = recognize_daily(bars)
    frames = replay['frames']
    if len(frames) != len(bars) or any(frame['index'] != index or frame['date'] != row['date']
                                     for index, (frame, row) in enumerate(zip(frames, bars))):
        raise ValueError('Center observations require replay frames for the same daily prefix')
    breaks = sorted(set(discontinuities))
    segments = {}
    centers = {}
    observations = []
    for frame in frames:
        changed_centers = {}
        for i in range(frame['event_start'], frame['event_end']):
            event = replay['events'][i]
            item = event['structure']
            identifier = item['id']
            if event['layer'] == 'segments':
                if event['action'] == 'removed' or item['status'] != 'confirmed':
                    segments.pop(identifier, None)
                else:
                    segments[identifier] = item
            elif event['layer'] == 'centers':
                changed_centers.setdefault(identifier, centers.get(identifier))
                if event['action'] == 'removed':
                    centers.pop(identifier, None)
                else:
                    centers[identifier] = item

        for identifier, previous in changed_centers.items():
            center = centers.get(identifier)
            if (not previous or previous['status'] != 'confirmed' or previous['phase'] != 'active' or
                    not center or center['status'] != 'confirmed' or center['phase'] != 'closed'):
                continue
            by_start = {segment['start_index']: segment for segment in segments.values()}
            observation = _evidence(center, previous, segments, by_start, bars, frame, breaks)
            if observation is not None:
                status, status_date = _latest_status(observation, bars, breaks)
                observations.append({**observation, 'status': status, 'status_date': status_date})
    return observations
