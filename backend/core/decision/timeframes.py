"""Weekly candles and structure from completed spans of a verified market calendar."""
from datetime import date, timedelta
from itertools import groupby

from backend.core.chan import recognize_daily
from backend.core.decision import _direction


def _monday(session: str) -> str:
    day = date.fromisoformat(session)
    return (day - timedelta(days=day.weekday())).isoformat()


def _weekly_bar(week_start: str, completion: str, trades: list[dict]) -> dict:
    return {
        'date': completion,
        'week_start': week_start,
        'first_trade_date': trades[0]['date'],
        'last_trade_date': trades[-1]['date'],
        'open': trades[0]['open'],
        'high': max(row['high'] for row in trades),
        'low': min(row['low'] for row in trades),
        'close': trades[-1]['close'],
        'volume': sum(row['volume'] for row in trades),
    }


def analyze_completed_weeks(*, sessions, active_bars, suspended_sessions, discontinuities,
                            coverage_start, cutoff) -> dict:
    """Derive context as of a closed session from the same frozen daily input.

    The session list must cover every exchange session from the request start
    through its frozen calendar horizon. A later calendar week proves the last
    session of an earlier week, including holiday-shortened weeks. The calendar
    alone cannot prove the end of its own terminal week.

    Only the uninterrupted tail of reliable weeks feeds structure recognition.
    A known break in an unfinished week retires earlier price context immediately.
    """
    if list(sessions) != sorted(set(sessions)) or cutoff not in sessions:
        raise ValueError('Weekly context requires a unique ordered calendar and a known cutoff session')
    observed = [row for row in active_bars if coverage_start <= row['date'] <= cutoff]
    by_date = {row['date']: row for row in observed}
    suspended = set(suspended_sessions)
    breaks = set(discontinuities) | {row['date'] for row in observed if row['volume'] <= 0}
    if (len(by_date) != len(observed) or set(by_date).difference(sessions)
            or suspended.intersection(by_date)):
        raise ValueError('Weekly observations must match distinct trading sessions')

    calendar_weeks = [(week, list(days)) for week, days in groupby(sessions, key=_monday)]
    cutoff_week = _monday(cutoff)
    bars = []
    skipped = []
    scheduled_completion = None
    for number, (week, days) in enumerate(calendar_weeks):
        if week > cutoff_week:
            break
        if days[-1] < coverage_start:
            continue
        completion = days[-1] if number + 1 < len(calendar_weeks) else None
        if week == cutoff_week:
            scheduled_completion = completion
        completed = completion is not None and completion <= cutoff
        elapsed = [day for day in days if coverage_start <= day <= cutoff]
        if any(day in breaks or (day not in by_date and day not in suspended) for day in elapsed):
            reason = 'discontinuity'
        elif week < coverage_start:
            # A request or listing partway through a week gives no comparable
            # opening span, even if the available calendar begins there too.
            reason = 'partial_coverage'
        elif not completed:
            continue
        else:
            trades = [by_date[day] for day in elapsed if day in by_date]
            if trades:
                bars.append(_weekly_bar(week, completion, trades))
                continue
            reason = 'fully_suspended'
        skipped.append({'week_start': week, 'scheduled_completion': completion, 'reason': reason})
        bars.clear()

    structures = recognize_daily(bars)['structures']
    fractals = sorted((item for item in structures['fractals'] if item['status'] == 'confirmed'),
                      key=lambda item: item['index'])
    trend = _direction([pivot for pivot in fractals if pivot['kind'] == 'top'],
                       [pivot for pivot in fractals if pivot['kind'] == 'bottom'])
    if not bars:
        status = 'unavailable'
    elif trend == 'insufficient':
        status = 'insufficient'
    else:
        status = 'ready'
    return {'bars': bars, 'structures': structures, 'context': {
        'completed_through': bars[-1]['date'] if bars else None,
        'scheduled_completion': scheduled_completion,
        'skipped_weeks': skipped,
        'trend': trend,
        'status': status,
    }}
