"""Explicit, archived public ETF quote sources. No network activity at import.

Eastmoney f56 is lots (100 shares), f57 is reported CNY turnover.
Field order follows AKShare fund_etf_hist_min_em (unadjusted klt=5).
Provider totals may differ; never splice providers into a single history.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from . import store

SHANGHAI = timezone(timedelta(hours=8))


class SourceError(ValueError):
    def __init__(self, message, provenance=None):
        super().__init__(message)
        self.provenance = provenance or {}


def _code(code):
    code = str(code)
    if not re.fullmatch(r"(?:sh|sz)?\d{6}", code):
        raise SourceError("Invalid ETF code")
    return code[-6:]


def _symbol(code):
    code = _code(code)
    return ("sh" if code.startswith("5") else "sz") + code


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def _time(value, fmt):
    try:
        return datetime.strptime(value, fmt).replace(tzinfo=SHANGHAI).isoformat()
    except (TypeError, ValueError) as exc:
        raise SourceError("Invalid provider timestamp") from exc


def _request(url, params=None, archive_dir=None):
    started = datetime.now(timezone.utc).isoformat()
    prepared = requests.Request("GET", url, params=params).prepare().url
    provenance = {"url": prepared, "request_started_at": started}
    root = Path(archive_dir) if archive_dir is not None else store.data_path() / "etf-intraday-sources"
    root.mkdir(parents=True, exist_ok=True)
    stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    try:
        response = requests.get(url, params=params, timeout=20)
        raw = response.content
        digest = hashlib.sha256(raw).hexdigest()
        provenance.update(response_received_at=datetime.now(timezone.utc).isoformat(),
                          raw_sha256=digest, status_code=response.status_code,
                          raw_file=f"{stem}-{digest[:12]}.raw")
        (root / provenance["raw_file"]).write_bytes(raw)
        response.raise_for_status()
    except requests.RequestException as exc:
        provenance.update(error=str(exc), request_finished_at=datetime.now(timezone.utc).isoformat())
        (root / f"{stem}.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SourceError(f"Provider request failed: {exc}", provenance) from exc
    (root / f"{stem}.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw, provenance


def parse_tencent_quotes(body, codes):
    """Tencent volume fields are lots; precise reported CNY is in field 35."""
    if isinstance(body, bytes):
        body = body.decode("gb18030")
    requested = {_code(c) for c in codes}
    rows = []
    for symbol, payload in re.findall(r'v_((?:sh|sz)\d{6})="([^"]*)"', body):
        fields = payload.split("~")
        if len(fields) < 38 or fields[2] != symbol[-6:]:
            raise SourceError("Missing or mismatched Tencent quote fields")
        code = fields[2]
        if code not in requested:
            continue
        volume = _number(fields[6])
        detail = fields[35].split("/")
        amount = _number(detail[2]) if len(detail) == 3 else None
        rounded_amount = _number(fields[37])
        if amount is not None and rounded_amount is not None and abs(amount - rounded_amount * 10000) > 10001:
            raise SourceError("Tencent turnover units disagree")
        if len(detail) == 3 and _number(detail[1]) != volume:
            raise SourceError("Tencent volume fields disagree")
        last, previous = _number(fields[3]), _number(fields[4])
        price_raw = fields[3] if re.fullmatch(r'\d+(?:\.\d+)?', fields[3]) else None
        price_decimals = len(price_raw.partition('.')[2]) if price_raw is not None else None
        rows.append(dict(code=code, name=fields[1], last=last, previous_close=previous,
                         price_raw=price_raw, price_decimals=price_decimals,
                         change_pct=(last / previous - 1) * 100 if last is not None and previous else None,
                         volume_shares=volume * 100 if volume is not None else None,
                         amount_cny=amount, source_time=_time(fields[30], "%Y%m%d%H%M%S")))
    if len({r['code'] for r in rows}) != len(rows):
        raise SourceError("Duplicate quote codes")
    return rows


def fetch_quotes(codes, *, archive_dir=None):
    codes = list(dict.fromkeys(_code(c) for c in codes))
    if not codes:
        return dict(rows=[], source="tencent", provenance={}, warnings=[])
    raw, provenance = _request("https://qt.gtimg.cn/q=" + ",".join(_symbol(c) for c in codes), archive_dir=archive_dir)
    try:
        rows = parse_tencent_quotes(raw, codes)
    except (ValueError, UnicodeError) as exc:
        raise SourceError(f"Invalid Tencent response: {exc}", provenance) from exc
    missing = sorted(set(codes) - {r['code'] for r in rows})
    return dict(rows=rows, source="tencent", provenance=provenance,
                warnings=[f"Missing quote: {c}" for c in missing],
                source_validation={"volume_unit": "lot_100_shares", "amount_unit": "CNY", "amount_field": 35})


def parse_eastmoney_bars(payload, code):
    code = _code(code)
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("code") != code or not isinstance(data.get("klines"), list):
        raise SourceError("Missing or mismatched Eastmoney minute data")
    rows = []
    previous = None
    for line in data["klines"]:
        fields = line.split(",")
        if len(fields) != 11:
            raise SourceError("Missing Eastmoney minute columns")
        time = _time(fields[0], "%Y-%m-%d %H:%M")
        dt = datetime.fromisoformat(time)
        minute = dt.hour * 60 + dt.minute
        if dt.minute % 5 or not (575 <= minute <= 690 or 785 <= minute <= 900):
            raise SourceError("Minute timestamp is not a regular five-minute bar end")
        if previous is not None and time <= previous:
            raise SourceError("Minute timestamps are duplicated or unordered")
        previous = time
        amount, volume = _number(fields[6]), _number(fields[5])
        rows.append(dict(code=code, time=time, amount_cny=amount,
                         volume_shares=volume * 100 if volume is not None else None))
    return rows


def fetch_bars(code, *, archive_dir=None):
    code = _code(code)
    params = dict(secid=f"{1 if code.startswith('5') else 0}.{code}", klt="5", fqt="0", beg="0",
                  end="20500101", lmt="2000", fields1="f1,f2,f3,f4,f5,f6",
                  fields2="f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61")
    raw, provenance = _request("https://push2his.eastmoney.com/api/qt/stock/kline/get", params, archive_dir)
    try:
        rows = parse_eastmoney_bars(json.loads(raw), code)
    except (ValueError, TypeError) as exc:
        raise SourceError(f"Invalid Eastmoney response: {exc}", provenance) from exc
    return dict(rows=rows, source="eastmoney", provenance=provenance, warnings=[],
                timestamp_convention="bar_end", amount_basis="reported_actual",
                source_validation={"volume_unit": "lot_100_shares", "amount_unit": "CNY", "interval_minutes": 5,
                                   "adjustment": "unadjusted", "cross_provider_equality": False,
                                   "opening_auction_in_first_bar": None,
                                   "aggregation": "vendor_reported_not_exchange_tick_reconstruction"})


fetch_minutes = fetch_bars
