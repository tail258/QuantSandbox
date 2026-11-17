"""Normalize BaoStock daily rows with explicit Shenzhen mainboard rule coverage."""

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


BAOSTOCK_URL = "https://www.baostock.com/"
SZSE_ORDINARY_A_SHARE_RULES = (
    (date(2021, 4, 6), "https://www.szse.cn/lawrules/rule/repeal/rules/P020231230545287939887.pdf"),
    (date(2023, 4, 10), "https://docs.static.szse.cn/www/lawrules/rule/stock/trade/W020230217564423808793.pdf"),
    (date(2026, 7, 6), "https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf"),
)

_TICK = Decimal("0.01")
_ORDINARY_LIMIT = Decimal("0.10")
_PRICE_FIELDS = ("open", "high", "low", "close")


def _decimal(value) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _is_price(value: Decimal | None) -> bool:
    return value is not None and value > 0 and value % _TICK == 0


def _price_limits(reference: Decimal) -> tuple[Decimal, Decimal]:
    upper = (reference * (1 + _ORDINARY_LIMIT)).quantize(_TICK, rounding=ROUND_HALF_UP)
    lower = (reference * (1 - _ORDINARY_LIMIT)).quantize(_TICK, rounding=ROUND_HALF_UP)
    return max(reference + _TICK, upper), max(_TICK, min(reference - _TICK, lower))


def baostock_szse_controls(
    raw_rows: Iterable[Mapping], symbol: str, *, ordinary_sessions: Iterable[date] = (),
) -> tuple[list[dict], dict]:
    """Return unadjusted OHLCV plus evidenced status and rules-derived limits.

    The caller must attest which sessions use the ordinary Shenzhen mainboard
    A-share rule. A listing/resumption/other exemption cannot be established
    from the stock code, price movement, or a missing row. Without attestation,
    a valid reference, and BaoStock's normal non-ST trading status, leave both
    limits unknown. Results use BaoStock's same-session `preclose`, which may
    include the ex-rights reference price rather than the previous row's close.
    """
    if not re.fullmatch(r"00[0-3]\d{3}", symbol):
        raise ValueError("仅支持深交所主板 A 股格式")
    ordinary_days = set(ordinary_sessions)
    observed = set()
    rows, rule_urls, gaps = [], set(), {}
    for row in raw_rows:
        session = date.fromisoformat(row["date"])
        if session in observed:
            raise ValueError(f"BaoStock 返回重复交易日：{session}")
        observed.add(session)
        if row.get("code") != f"sz.{symbol}" or str(row.get("adjustflag")) != "3":
            raise ValueError(f"BaoStock 行情必须是同标的不复权日线：{session}")
        prices = {key: _decimal(row.get(key)) for key in _PRICE_FIELDS}
        volume = _decimal(row.get("volume"))
        if (not all(_is_price(price) for price in prices.values()) or volume is None or volume < 0 or
                volume != volume.to_integral_value()):
            raise ValueError(f"BaoStock OHLCV 无效或缺失：{session}")
        if not prices["low"] <= min(prices["open"], prices["close"]) <= max(prices["open"], prices["close"]) <= prices["high"]:
            raise ValueError(f"BaoStock OHLC 错序：{session}")

        status = {"0": True, "1": False}.get(str(row.get("tradestatus")))
        if (status is True and volume != 0) or (status is False and volume == 0):
            status = None  # Inconsistent evidence is unresolved, not normal trading.
        normalized = {"date": str(session), **{key: float(value) for key, value in prices.items()},
                      "volume": int(volume), "is_suspended": status, "limit_up": None, "limit_down": None}
        rows.append(normalized)
        if status is True:
            continue
        reference = _decimal(row.get("preclose"))
        rule_url = next((url for effective, url in reversed(SZSE_ORDINARY_A_SHARE_RULES) if session >= effective), None)
        if status is None:
            gaps[str(session)] = "unknown_or_inconsistent_trading_status"
        elif str(row.get("isST")) != "0":
            gaps[str(session)] = "unknown_or_special_treatment"
        elif session not in ordinary_days or rule_url is None:
            gaps[str(session)] = "ordinary_limit_regime_unconfirmed"
        elif not _is_price(reference):
            gaps[str(session)] = "missing_or_invalid_reference_price"
        else:
            upper, lower = _price_limits(reference)
            if not lower <= prices["low"] <= prices["high"] <= upper:
                gaps[str(session)] = "observed_prices_outside_derived_limits"
                continue
            rule_urls.add(rule_url)
            normalized.update(limit_up=float(upper), limit_down=float(lower))
    return sorted(rows, key=lambda row: row["date"]), {"rule_urls": sorted(rule_urls), "gaps": dict(sorted(gaps.items()))}
