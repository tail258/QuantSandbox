"""Import sourced, unadjusted daily prices and execution evidence into a frozen research snapshot."""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Annotated, Literal

import pandas as pd
from pydantic import AnyHttpUrl, AwareDatetime, Field, StrictBool, model_validator

from backend.api.schemas import StrictModel
from backend.core.data_format import COLUMNS, DIVIDEND_COLUMNS, DataUnavailable, frame_records, validate_frame
from backend.workbench import store


class SourceSpec(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    url: AnyHttpUrl
    acquired_at: AwareDatetime
    method: str = Field(min_length=1, max_length=3000)
    raw_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class TradingEvidence(StrictModel):
    suspension: SourceSpec | None = None
    limits: SourceSpec | None = None
    limits_kind: Literal["published", "rule_derived"] | None = None
    rule_urls: list[AnyHttpUrl] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def coherent_limit_provenance(self):
        if (self.limits is None) != (self.limits_kind is None):
            raise ValueError("涨跌停来源须说明直接公布或按规则计算")
        if self.limits_kind == "rule_derived" and not self.rule_urls:
            raise ValueError("按规则计算涨跌停须附交易所原文")
        return self


class ObservationCalendar(StrictModel):
    source: SourceSpec
    sessions: list[date] = Field(min_length=1, max_length=4000)
    next_session: date | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def coherent_span(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("须同时提供交易日历的已核验起止日期")
        if self.start_date is not None and not self.start_date <= min(self.sessions) <= max(self.sessions) <= self.end_date:
            raise ValueError("交易日必须位于已核验的日历区间内")
        return self


def calendar_span(calendar: dict) -> tuple[str, str] | None:
    """Legacy snapshots establish coverage between listed sessions only."""
    sessions = calendar.get("sessions")
    if not sessions:
        return None
    return calendar.get("start_date") or min(sessions), calendar.get("end_date") or max(sessions)


Positive = Annotated[float, Field(gt=0)]


class PriceRow(StrictModel):
    date: date
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: Annotated[float, Field(ge=0)]
    is_suspended: StrictBool | None = None
    limit_up: Positive | None = None
    limit_down: Positive | None = None

    @model_validator(mode="after")
    def coherent_execution_controls(self):
        if (self.limit_up is None) != (self.limit_down is None):
            raise ValueError("涨跌停价必须成对提供；不明留空")
        if self.limit_down is not None and not self.is_suspended:
            if not self.limit_down <= self.low <= self.high <= self.limit_up:
                raise ValueError("成交区间超出所提供的当日涨跌停价")
        if self.is_suspended and self.volume != 0:
            raise ValueError("停牌行的实际成交量必须为零")
        return self


class CashDividend(StrictModel):
    record_date: date
    ex_date: date
    payment_date: date
    cash_per_share: Positive
    announced_date: date
    source_url: AnyHttpUrl

    @model_validator(mode="after")
    def ordered_dates(self):
        if not self.announced_date < self.record_date < self.ex_date <= self.payment_date:
            raise ValueError("只知公告日期时，须满足公告日 < 股权登记日 < 除息日 ≤ 到账日")
        return self


class ExecutionHistory(StrictModel):
    symbol: str = Field(pattern=r"^\d{6}$")
    start: date
    end: date
    price_basis: Literal["raw_unadjusted"]
    volume_unit: Literal["shares"]
    price_source: SourceSpec
    trading_evidence: TradingEvidence = Field(default_factory=TradingEvidence)
    calendar: ObservationCalendar | None = None
    dividend_review: SourceSpec | None = None
    dividend_review_through: date | None = None
    dividend_events: list[CashDividend] = Field(default_factory=list, max_length=100)
    base_snapshot_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{20}$")
    rows: list[PriceRow] = Field(min_length=1, max_length=4000)


def import_execution_history(history: ExecutionHistory) -> dict:
    if history.start > history.end or history.end > date.today():
        raise ValueError("历史行情日期范围无效")
    dates = [row.date for row in history.rows]
    if dates != sorted(set(dates)) or dates[0] < history.start or dates[-1] > history.end:
        raise ValueError("日线须按观测日期升序、日期唯一且在声明范围内")
    calendar_days = history.calendar.sessions if history.calendar else None
    if calendar_days and (calendar_days != sorted(set(calendar_days)) or
                          not history.start <= calendar_days[0] <= calendar_days[-1] <= history.end or
                          set(dates) - set(calendar_days)):
        raise ValueError("交易日日历须为区间内的有序唯一日期，且日线日期必须在日历内")
    if history.calendar and history.calendar.start_date is not None and (
            not history.start <= history.calendar.start_date <= history.calendar.end_date <= history.end):
        raise ValueError("已核验日历区间须位于声明的历史行情区间内")
    if history.calendar and history.calendar.next_session and history.calendar.next_session <= history.end:
        raise ValueError("下一交易日必须晚于历史核查区间")
    evidence = history.trading_evidence
    if any(row.is_suspended is not None for row in history.rows) and not evidence.suspension:
        raise ValueError("停牌字段须提供可核对的历史来源")
    if any(row.limit_up is not None for row in history.rows) and not evidence.limits:
        raise ValueError("涨跌停字段须提供可核对的历史来源")
    dividends = {event.record_date: event for event in history.dividend_events}
    if len(dividends) != len(history.dividend_events) or dividends.keys() - set(dates):
        raise ValueError("每笔分红须关联到唯一且存在的股权登记日行情")
    if history.dividend_review_through is not None and (
            history.dividend_review is None or not history.start <= history.dividend_review_through <= date.today()):
        raise ValueError("分红核查截止日须附来源并位于有效历史范围")
    if history.base_snapshot_id:
        base = store.get_snapshot(history.base_snapshot_id)
        if base["kind"] != "quotes" or base["symbol"] != history.symbol or base["request"].get("adjust") != "3":
            raise ValueError("原始快照必须是同标的未复权日线")
        previous = [{key: row[key] for key in COLUMNS} for row in base["rows"]]
        current = [row.model_dump(mode="json", include=set(COLUMNS)) for row in history.rows]
        if previous != current:
            raise ValueError("补充执行证据时必须保留原快照的完整日期及 OHLCV")

    rows = []
    for row in history.rows:
        data = row.model_dump(mode="json", exclude_none=True)
        if history.dividend_review is not None:
            data.update(dict.fromkeys(DIVIDEND_COLUMNS))
        if event := dividends.get(row.date):
            data.update(cash_dividend_per_share=event.cash_per_share, dividend_ex_date=event.ex_date.isoformat(),
                        dividend_payment_date=event.payment_date.isoformat())
        rows.append(data)
    try:
        rows = frame_records(validate_frame(pd.DataFrame(rows)))
    except DataUnavailable as exc:
        raise ValueError(str(exc)) from exc
    provenance = history.model_dump(mode="json", exclude={"rows", "symbol", "start", "end", "price_basis", "volume_unit"})
    calendar = provenance["calendar"] or {}
    span = calendar_span(calendar)
    fully_covered = span is not None and span[0] <= history.start.isoformat() <= history.end.isoformat() <= span[1]
    coverage = {
        "expected_sessions": len(calendar_days) if fully_covered else None,
        "missing_sessions": [day.isoformat() for day in sorted(set(calendar_days) - set(dates))] if fully_covered else None,
        "observed_sessions": len(dates),
        "unknown_suspension": sum(row.is_suspended is None for row in history.rows),
        "unknown_limits_on_active_or_unknown_sessions": sum(row.limit_up is None and row.is_suspended is not True for row in history.rows),
        "suspended_sessions": sum(row.is_suspended is True for row in history.rows),
        "dividend_events": len(dividends),
    }
    provenance["coverage"] = coverage
    if history.base_snapshot_id:
        provenance["base_snapshot_sha256"] = hashlib.sha256(store.encode(base).encode()).hexdigest()
    payload = {
        "kind": "quotes", "symbol": history.symbol, "rows": rows,
        "request": {"kind": "quotes", "symbol": history.symbol, "start": history.start.isoformat(),
                    "end": history.end.isoformat(), "adjust": "3"},
        "source": history.price_source.name, "source_url": str(history.price_source.url), "unit": "元 / 股",
        "method": "不复权日线；成交量统一为股；停牌、涨跌停与分红见执行证据及覆盖率，未知保留缺失。",
        "execution_history": provenance,
    }
    return store.snapshot("execution-quotes:" + history.symbol, payload)
