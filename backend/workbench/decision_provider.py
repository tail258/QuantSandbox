"""BaoStock identity, complete calendar, and raw daily prices for decision research."""
from __future__ import annotations

from contextlib import redirect_stdout, suppress
from datetime import date, timedelta
from decimal import Decimal
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys


SOURCE = "BaoStock"
SOURCE_URL = "https://www.baostock.com/"
FETCH_TIMEOUT = 55
_ROOT = Path(__file__).resolve().parents[2]
_PRICE_FIELDS = ("open", "high", "low", "close")
_FIELDS = "date,code,open,high,low,close,preclose,volume,adjustflag,tradestatus"


class DecisionProviderError(ValueError):
    """The decision feed could not supply trustworthy upstream data."""


class UnsupportedInstrument(DecisionProviderError):
    """The requested instrument is outside this feed's confirmed scope."""


def _market(symbol: str) -> tuple[str, str, str]:
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise UnsupportedInstrument("证券代码须为 6 位数字")
    if symbol.startswith(("600", "601", "603", "605", "688")):
        return f"sh.{symbol}", "SSE", "stock"
    if symbol.startswith(("000", "001", "002", "003", "300", "301")):
        return f"sz.{symbol}", "SZSE", "stock"
    if symbol.startswith("5"):
        return f"sh.{symbol}", "SSE", "etf"
    if symbol.startswith("159"):
        return f"sz.{symbol}", "SZSE", "etf"
    raise UnsupportedInstrument("当前行情来源仅支持沪深 A 股及 ETF，不覆盖该证券代码")


def _date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise DecisionProviderError(f"{field}须为有效的 YYYY-MM-DD 日期") from exc
    return parsed


def _request(symbol: str, start: str, end: str, calendar_end: str):
    market = _market(symbol)
    dates = tuple(_date(value, field) for value, field in
                  ((start, "行情开始日"), (end, "行情截止日"), (calendar_end, "日历截止日")))
    if not dates[0] <= dates[1] <= dates[2]:
        raise DecisionProviderError("行情及日历日期范围无效")
    return market, dates


def _instrument(rows: list[dict], symbol: str, market: tuple[str, str, str]) -> dict:
    code, exchange, kind = market
    if not rows:
        raise UnsupportedInstrument("BaoStock 未返回此证券的身份资料")
    if len(rows) != 1 or rows[0].get("code") != code:
        raise DecisionProviderError("BaoStock 证券身份返回重复或与请求代码不一致")
    row = rows[0]
    if {"1": "stock", "5": "etf"}.get(row.get("type")) != kind:
        raise UnsupportedInstrument("BaoStock 返回的证券类别与当前支持的沪深 A 股或 ETF 代码不符")
    if row.get("status") == "0":
        raise UnsupportedInstrument("BaoStock 显示该证券已退市")
    if row.get("status") != "1":
        raise DecisionProviderError("BaoStock 未确认该证券的上市状态")
    name = row.get("code_name")
    if not isinstance(name, str) or not name.strip():
        raise DecisionProviderError("BaoStock 证券名称缺失")
    ipo_date = _date(row.get("ipoDate"), "BaoStock 证券上市日")
    return {"symbol": symbol, "name": name.strip(), "exchange": exchange,
            "kind": kind, "listed": True, "ipo_date": ipo_date.isoformat()}


def _calendar(rows: list[dict], start: date, end: date) -> dict:
    flags: dict[date, str] = {}
    for row in rows:
        day = _date(row.get("calendar_date"), "BaoStock 日历日期")
        flag = row.get("is_trading_day")
        if not start <= day <= end or day in flags or flag not in ("0", "1"):
            raise DecisionProviderError(f"BaoStock 交易日历存在异常日期或交易状态：{day}")
        flags[day] = flag
    if len(flags) != (end - start).days + 1:
        missing = next(start + timedelta(days=i) for i in range((end - start).days + 1)
                       if start + timedelta(days=i) not in flags)
        raise DecisionProviderError(f"BaoStock 交易日历缺少 {missing}，无法判断该日是否交易")
    return {"start_date": start.isoformat(), "end_date": end.isoformat(),
            "source": "BaoStock · query_trade_dates", "source_url": SOURCE_URL,
            "sessions": [day.isoformat() for day in sorted(flags) if flags[day] == "1"]}


def _number(row: dict, key: str, day: date) -> Decimal:
    value = row.get(key)
    if not isinstance(value, str) or len(value) > 32 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise DecisionProviderError(f"BaoStock 日线 {day} 的 {key} 缺失或无效")
    return Decimal(value)


def _daily_rows(rows: list[dict], code: str, start: date, end: date) -> list[dict]:
    observations = {}
    for row in rows:
        day = _date(row.get("date"), "BaoStock 日线日期")
        if not start <= day <= end or day in observations:
            raise DecisionProviderError(f"BaoStock 日线日期重复或超出请求区间：{day}")
        if row.get("code") != code or row.get("adjustflag") != "3":
            raise DecisionProviderError(f"BaoStock 日线 {day} 的证券代码或不复权标记不符")
        status = row.get("tradestatus")
        if status not in ("0", "1"):
            raise DecisionProviderError(f"BaoStock 日线 {day} 的交易状态未知")
        suspended = status == "0"
        prices = {key: _number(row, key, day) for key in _PRICE_FIELDS}
        volume = _number(row, "volume", day)
        reference = _number(row, "preclose", day)
        if (any(price <= 0 or not math.isfinite(float(price)) for price in (*prices.values(), reference)) or
                not prices["low"] <= min(prices["open"], prices["close"]) <=
                max(prices["open"], prices["close"]) <= prices["high"]):
            raise DecisionProviderError(f"BaoStock 日线 {day} 的 OHLC 或前收参考价无效")
        if volume != volume.to_integral_value() or volume > 2**53 - 1 or (volume == 0) != suspended:
            raise DecisionProviderError(f"BaoStock 日线 {day} 的成交量与交易状态不一致或无效")
        # BaoStock reports a suspended day with flat OHLC at the same-session
        # preclose, zero shares, and blank turnover (which we do not request).
        if suspended and any(price != reference for price in prices.values()):
            raise DecisionProviderError(f"BaoStock 日线 {day} 的停牌价格与前收参考价不一致")
        observations[day] = {"date": day.isoformat(), **{key: float(value) for key, value in prices.items()},
                             "volume": int(volume), "is_suspended": suspended, "prev_close": float(reference)}
    return [observations[day] for day in sorted(observations)]


def _check_response(response, label: str) -> None:
    if getattr(response, "error_code", None) != "0":
        reason = getattr(response, "error_msg", None) or "未收到有效响应"
        code = getattr(response, "error_code", "")
        raise DecisionProviderError(f"BaoStock {label}失败（{code}）：{reason}")


def _rows(response, label: str) -> list[dict]:
    _check_response(response, label)
    rows = []
    fields = response.fields
    while response.next():
        values = response.get_row_data()
        if len(values) != len(fields) or len(fields) != len(set(fields)):
            raise DecisionProviderError(f"BaoStock {label}响应字段不完整")
        rows.append(dict(zip(fields, values, strict=True)))
    # BaoStock may update the response error code while requesting another page.
    _check_response(response, label)
    return rows


def _capture(client, symbol: str, start: str, end: str, calendar_end: str) -> dict:
    market, (first, last, calendar_last) = _request(symbol, start, end, calendar_end)
    code = market[0]
    _check_response(client.login(), "登录")
    try:
        instrument = _instrument(_rows(client.query_stock_basic(code=code), "证券身份查询"), symbol, market)
        calendar = _calendar(_rows(client.query_trade_dates(start_date=start, end_date=calendar_end), "交易日历查询"),
                             first, calendar_last)
        rows = _daily_rows(_rows(client.query_history_k_data_plus(code, _FIELDS, start_date=start, end_date=end,
                                                                frequency="d", adjustflag="3"), "日线查询"),
                           code, first, last)
        return {"instrument": instrument, "calendar": calendar, "rows": rows,
                "source": SOURCE, "source_url": SOURCE_URL}
    finally:
        with suppress(Exception):
            client.logout()


def fetch_daily_market(symbol: str, start: str, end: str, calendar_end: str) -> dict:
    """Acquire read-only market data in a process that can be killed on timeout."""
    _request(symbol, start, end, calendar_end)
    try:
        job = subprocess.run([sys.executable, "-X", "utf8", "-m", "backend.workbench.decision_provider",
                              symbol, start, end, calendar_end], cwd=_ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=FETCH_TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise DecisionProviderError(f"BaoStock 行情获取超时（{FETCH_TIMEOUT} 秒）") from exc
    except OSError as exc:
        raise DecisionProviderError(f"无法启动 BaoStock 行情进程：{exc}") from exc

    try:
        response = json.loads(job.stdout)
        if job.returncode != 0 or not isinstance(response, dict) or type(response.get("ok")) is not bool:
            raise ValueError
        if response["ok"] and isinstance(response.get("data"), dict):
            return response["data"]
        if response["ok"] or not isinstance(response.get("error"), str):
            raise ValueError
    except ValueError as exc:
        detail = job.stderr.strip()[-300:]
        raise DecisionProviderError("BaoStock 行情进程未返回有效结果" + (f"：{detail}" if detail else "")) from exc
    error_type = UnsupportedInstrument if response.get("unsupported") else DecisionProviderError
    raise error_type(response["error"])


def _main(args: list[str]) -> None:
    try:
        with redirect_stdout(io.StringIO()):
            try:
                import baostock
            except ImportError as exc:
                raise DecisionProviderError("BaoStock 未安装；请安装 requirements-market.txt") from exc
            data = _capture(baostock, *args)
        response = {"ok": True, "data": data}
    except DecisionProviderError as exc:
        response = {"ok": False, "error": str(exc), "unsupported": isinstance(exc, UnsupportedInstrument)}
    except Exception as exc:
        response = {"ok": False, "error": f"BaoStock 行情获取失败：{type(exc).__name__}: {exc}"}
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    _main(sys.argv[1:])
