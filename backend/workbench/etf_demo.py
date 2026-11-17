"""Deterministic synthetic inputs; no network or persistent-store access."""
from datetime import datetime, timedelta
import hashlib
import json
from .etf_intraday import SLOTS, TZ, comparison


def create_demo():
    clock = datetime(2025, 3, 28, 10, 32, tzinfo=TZ)
    days = []
    day = clock.date()
    while len(days) < 21:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    rows = [{'time': f'{day}T{slot}:00+08:00',
             'amount_cny': (1_000_000 + index * 10_000) * (1.5 if day == days[-1] else 1)}
            for day in days for index, slot in enumerate(SLOTS)]
    quote = {'price': 4.123, 'price_raw': '4.123', 'price_decimals': 3,
             'source_time': clock.isoformat(), 'amount': 22_000_000, 'change_pct': 0.73}
    inputs = {'quote': quote, 'history': {'rows': rows}, 'calendar': days}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'synthetic': True, 'source': 'synthetic:hand-authored-v1', 'code': 'DEMO-ETF',
            'clock': clock.isoformat(), 'input_sha256': digest, 'inputs': inputs,
            'comparison': comparison(quote, inputs['history'], clock, days)}
