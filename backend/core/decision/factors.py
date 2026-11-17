"""A small selectable set of descriptive factors on continuous closed bars."""
from statistics import fmean, pstdev

FACTOR_KEYS = ('sma20', 'sma60', 'rsi14', 'bollinger20', 'relative_volume20')
DEFAULT_FACTORS = ('sma20', 'relative_volume20')
FACTOR_VERSION = 'decision-factors-v1'


def describe_factors(bars, discontinuities=()):
    """Apply the repository's descriptive conventions on the same chart basis."""
    if not bars:
        return []
    end = bars[-1]['date']
    last_break = max((day for day in discontinuities if day <= end), default='')
    tail = [row for row in bars if row['date'] > last_break]
    closes = [row['close'] for row in tail]
    volume = [row['volume'] for row in tail]
    middle = fmean(closes[-20:]) if len(closes) >= 20 else None
    spread = 2 * pstdev(closes[-20:]) if middle is not None else None
    slow = fmean(closes[-60:]) if len(closes) >= 60 else None
    rsi = None
    if len(closes) >= 15:
        delta = [right - left for left, right in zip(closes[-15:-1], closes[-14:])]
        gain = fmean(max(0, change) for change in delta)
        loss = fmean(max(0, -change) for change in delta)
        rsi = 100 * gain / (gain + loss) if gain + loss else 50.0
    prior = fmean(volume[-21:-1]) if len(volume) >= 21 else None

    def as_factor(key, value, basis='raw_unadjusted', **details):
        return {'key': key, 'value': value, 'as_of': end, 'basis': basis, **details}

    return [
        as_factor('sma20', middle), as_factor('sma60', slow), as_factor('rsi14', rsi),
        as_factor('bollinger20', middle, lower=None if spread is None else middle - spread,
                  detail=None if spread is None else middle + spread),
        as_factor('relative_volume20', volume[-1] / prior if prior else None,
                  basis='eligible_traded_sessions', detail=prior),
    ]
