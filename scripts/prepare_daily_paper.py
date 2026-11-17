"""Fetch one explicitly requested BaoStock session and prepare a reviewed paper input."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import socket
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.workbench import store
from backend.workbench.execution_history import CashDividend, ExecutionHistory, PriceRow
from backend.workbench.trading_controls import BAOSTOCK_URL, baostock_szse_controls

SHANGHAI = timezone(timedelta(hours=8))
FIELDS = "date,code,open,high,low,close,preclose,volume,adjustflag,tradestatus,isST"


def read_snapshot(identifier: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{20}", identifier):
        raise ValueError("历史快照编号无效")
    db_uri = (store.data_path() / "workbench.sqlite").resolve().as_uri()
    with closing(sqlite3.connect(db_uri + "?mode=ro", uri=True)) as connection:
        row = connection.execute("SELECT payload FROM snapshots WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise ValueError("找不到历史快照")
    snapshot = json.loads(row[0])
    payload = {key: value for key, value in snapshot.items() if key != "id"}
    if snapshot.get("id") != identifier or hashlib.sha256(store.encode(payload).encode()).hexdigest()[:20] != identifier:
        raise ValueError("历史快照未通过完整性校验")
    return snapshot


def capture_baostock(symbol: str, observation: date) -> dict:
    import baostock as bs

    def rows(result):
        if result.error_code != "0":
            raise ValueError(f"BaoStock {result.error_code}: {result.error_msg}")
        data = result.get_data().to_dict("records")
        if result.error_code != "0" or not data:
            raise ValueError("BaoStock 响应失败或没有行情，待重新核对")
        return data

    socket_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(15)
    connected = False
    try:
        login = bs.login()
        if login.error_code != "0":
            raise ValueError(f"BaoStock {login.error_code}: {login.error_msg}")
        connected = True
        day = observation.isoformat()
        bars = rows(bs.query_history_k_data_plus(f"sz.{symbol}", FIELDS, start_date=day, end_date=day,
                                                 frequency="d", adjustflag="3"))
        calendar_end = (observation + timedelta(days=21)).isoformat()
        calendar = rows(bs.query_trade_dates(start_date=day, end_date=calendar_end))
        return {"source": BAOSTOCK_URL, "package_version": version("baostock"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "request": {"code": f"sz.{symbol}", "date": day, "frequency": "d", "adjustflag": "3",
                            "fields": FIELDS, "calendar_end": calendar_end},
                "bars": bars, "calendar": calendar}
    finally:
        try:
            if connected:
                bs.logout()
        finally:
            socket.setdefaulttimeout(socket_timeout)


def prior_calendar(prior: dict, observation: date) -> dict:
    proof = prior.get("execution_history") or {}
    calendar = proof.get("calendar") or {}
    if calendar.get("next_session") != str(observation):
        raise ValueError("观察日必须是前次冻结日历中的下一交易日")
    sessions = calendar.get("sessions", [])
    if (prior.get("kind") != "quotes" or prior.get("request", {}).get("adjust") != "3" or not sessions
            or not re.fullmatch(r"00[0-3]\d{3}", prior.get("symbol", ""))
            or prior["request"]["end"] != sessions[-1] or [row["date"] for row in prior["rows"]] != sessions):
        raise ValueError("须提供含完整执行证据的前次未复权快照")
    if (proof.get("trading_evidence") or {}).get("limits_kind") != "rule_derived":
        raise ValueError("逐日追加脚本仅支持前次按深市主板规则计算涨跌停的快照")
    return calendar


def review_dividends(prior: dict, observation: date, raw_review: bytes, acquired_at: datetime) -> tuple[dict, list[dict]]:
    review = json.loads(raw_review)
    if (review.get("schema") != "quantsandbox.cash-dividend-source.v1" or review.get("symbol") != prior["symbol"]
            or review.get("exchange") != "SZSE" or review.get("share_class") != "A" or review.get("currency") != "CNY"):
        raise ValueError("分红核查必须来自同标的深市 A 股人民币现金分红")
    cutoff = date.fromisoformat(review["reviewed_through"])
    checked_at = datetime.fromisoformat(review["checked_at"])
    if checked_at.utcoffset() is None:
        raise ValueError("分红核查时间须包含时区")
    checked_local = checked_at.astimezone(SHANGHAI)
    prior_start = date.fromisoformat(prior["request"]["start"])
    if (date.fromisoformat(review["reviewed_from"]) > prior_start or cutoff < observation
            or checked_at > acquired_at
            or cutoff > checked_local.date()
            or checked_local < datetime.combine(observation, time(15), SHANGHAI)):
        raise ValueError("现金分红核查须覆盖整个已观察区间，且在本次收盘后实际完成")
    events = [CashDividend.model_validate({
        "record_date": event["record_date"], "ex_date": event["ex_date"],
        "payment_date": event["pay_date"], "cash_per_share": event["cash_per_share"],
        "announced_date": event["announced_date"], "source_url": event["source_url"],
    }) for event in review["events"]]
    if any(event.announced_date > cutoff for event in events):
        raise ValueError("分红公告日期不能晚于本次核查截止日")
    included = [event.model_dump(mode="json") for event in events if prior_start <= event.record_date <= observation]
    if len({event["record_date"] for event in included}) != len(included):
        raise ValueError("分红核查有重复的股权登记日")
    saved_events = prior["execution_history"]["dividend_events"]
    if sorted((event for event in included if event["record_date"] < str(observation)), key=lambda event: event["record_date"]) != sorted(saved_events, key=lambda event: event["record_date"]):
        raise ValueError("新的分红核查修订了先前输入，须单独复核")
    source = {"name": "巨潮资讯/发行人现金派息实施公告", "url": review["query_source_url"],
              "acquired_at": review["checked_at"], "method": review["method"],
              "raw_sha256": hashlib.sha256(raw_review).hexdigest()}
    return source, included


def prepare_input(prior: dict, observation: date, raw_review: bytes, capture: dict) -> tuple[ExecutionHistory, bytes]:
    calendar = prior_calendar(prior, observation)
    stamp = datetime.fromisoformat(capture["fetched_at"])
    if stamp.utcoffset() is None or stamp.astimezone(SHANGHAI) < datetime.combine(observation, time(15), SHANGHAI):
        raise ValueError("观察日尚未收盘，不能冻结日线")
    source, events = review_dividends(prior, observation, raw_review, stamp)
    day = str(observation)
    days = [(item["calendar_date"], item["is_trading_day"]) for item in capture["calendar"]]
    dates = [date.fromisoformat(session_day) for session_day, _ in days]
    if not days or days[0] != (day, "1") or any(flag not in ("0", "1") for _, flag in days):
        raise ValueError("BaoStock 日历未确认观察日开市")
    next_session = None
    for offset, (session_day, flag) in enumerate(days):
        if dates[offset] != observation + timedelta(days=offset):
            raise ValueError("BaoStock 日历返回缺失、重复或乱序")
        if offset and flag == "1":
            next_session = session_day
            break
    if next_session is None:
        raise ValueError("BaoStock 日历未确认下一交易日")
    if stamp.astimezone(SHANGHAI) >= datetime.combine(date.fromisoformat(next_session), time(9, 30), SHANGHAI):
        raise ValueError("下一交易日已经开盘，不能把补抓行情用于回填逐日计划")

    rows, audit = baostock_szse_controls(capture["bars"], prior["symbol"], ordinary_sessions=[observation])
    if [row["date"] for row in rows] != [day] or audit["gaps"]:
        raise ValueError(f"当日停牌、涨跌停或行情证据不足：{audit['gaps']}")
    if any(item["date"] == day for item in prior["rows"]):
        raise ValueError("观察日已在前次快照中")
    existing = prior["execution_history"]
    source_bundle = {**capture, "previous_snapshot_id": prior["id"],
                     "previous_sources": {"price_source": existing["price_source"],
                                          "trading_evidence": existing["trading_evidence"],
                                          "calendar": calendar["source"]},
                     "ordinary_session_attested": day, "applied_rules": audit["rule_urls"]}
    raw = json.dumps(source_bundle, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    digest = hashlib.sha256(raw).hexdigest()

    def daily_source(method):
        return {"name": "BaoStock", "url": BAOSTOCK_URL, "acquired_at": capture["fetched_at"],
                "method": f"保留前次固定快照 {prior['id']}；{method}", "raw_sha256": digest}

    rule_urls = sorted(set(existing["trading_evidence"]["rule_urls"]) | set(audit["rule_urls"]))
    rows = [{key: value for key, value in row.items() if key in PriceRow.model_fields} for row in prior["rows"]] + rows
    return ExecutionHistory.model_validate({
        "symbol": prior["symbol"], "start": prior["request"]["start"], "end": day,
        "price_basis": "raw_unadjusted", "volume_unit": "shares", "rows": rows,
        "price_source": daily_source("追加 BaoStock query_history_k_data_plus frequency=d adjustflag=3 的当日已收盘 OHLCV"),
        "trading_evidence": {
            "suspension": daily_source("追加当日 BaoStock tradestatus；全日交易状态，不表示开盘后无临停"),
            "limits": daily_source("人工核查当日适用深交所普通主板规则；以 BaoStock 非 ST 的当日前收参考价 preclose 按规则计算涨跌停价"),
            "limits_kind": "rule_derived", "rule_urls": rule_urls,
        },
        "calendar": {"source": daily_source("BaoStock query_trade_dates 追加当日及下一次已核对交易日"),
                     "sessions": calendar["sessions"] + [day], "next_session": next_session},
        "dividend_review": source, "dividend_review_through": day, "dividend_events": events,
    }), raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-snapshot", required=True)
    parser.add_argument("--observation", required=True, type=date.fromisoformat)
    parser.add_argument("--dividend-review", required=True, type=Path)
    parser.add_argument("--ordinary-session", action="store_true", required=True,
                        help="confirm the observed session's ordinary Shenzhen mainboard limit regime was checked")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    sidecar = args.output.with_suffix(".baostock.json")
    try:
        if args.output == sidecar or args.output.exists() or sidecar.exists() or not args.output.parent.is_dir():
            raise ValueError("输出须是现有目录内未使用的 JSON 文件名和配套证据文件名")
        now = datetime.now(timezone.utc)
        if now.astimezone(SHANGHAI) < datetime.combine(args.observation, time(15), SHANGHAI):
            raise ValueError("观察日尚未收盘")
        prior = read_snapshot(args.prior_snapshot)
        prior_calendar(prior, args.observation)
        raw_review = args.dividend_review.read_bytes()
        review_dividends(prior, args.observation, raw_review, now)
        payload, raw = prepare_input(prior, args.observation, raw_review, capture_baostock(prior["symbol"], args.observation))
        with sidecar.open("xb") as stream:
            stream.write(raw)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(payload.model_dump_json(indent=2) + "\n")
        print(f"Prepared {args.output} and {sidecar}")
    except (ValueError, OSError, sqlite3.Error, ImportError, KeyError, TypeError) as exc:
        parser.exit(1, f"Daily input not prepared: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
