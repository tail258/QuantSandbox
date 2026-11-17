"""Manual daily paper account. Advance once per observed and verified exchange session."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

import pandas as pd

from backend.api.schemas import AccountConfig
from backend.core.data_format import atomic_json, canonical_json, frame_hash
from backend.core.engine import run_backtest
from backend.core.strategy import StrategyFactory
from backend.services.provenance import engine_fingerprint

SHANGHAI = timezone(timedelta(hours=8))
RULE = {"name": "dual_ma", "parameters": {"fast_period": 5, "slow_period": 20}}
paper_lock = RLock()


def _data(snapshot, as_of, observed_at):
    proof = snapshot.get("execution_history") or {}
    calendar = proof.get("calendar") or {}
    sessions = [day for day in calendar.get("sessions", []) if day <= as_of]
    rows = [row for row in snapshot["rows"] if row["date"] <= as_of]
    if not sessions or not rows or sessions[-1] != as_of or [row["date"] for row in rows] != sessions:
        raise ValueError("逐日模拟需要完整的交易日日历和截至当日的日线")
    if not calendar.get("next_session") or calendar["sessions"][-1] != as_of:
        raise ValueError("逐日模拟需要当日截止的日历及已核对的下一交易日")
    next_session = date.fromisoformat(calendar["next_session"])
    if observed_at.astimezone(SHANGHAI) >= datetime.combine(next_session, time(9, 30), SHANGHAI):
        raise ValueError("下一交易日已经开盘，不能回填当晚计划")
    if any(row.get("is_suspended") is None or (not row["is_suspended"] and
           (row.get("limit_up") is None or row.get("limit_down") is None)) for row in rows):
        raise ValueError("历史停牌或适用的涨跌停价缺失，暂不推进逐日模拟")
    if not proof.get("dividend_review") or (proof.get("dividend_review_through") or "") < as_of:
        raise ValueError("须核查截至该日的已公告现金分红")
    if len(rows) < 20:
        raise ValueError("5/20 日双均线至少需要 20 根已完成日线")
    sources = [proof.get("price_source", {}), calendar.get("source", {}), proof["dividend_review"]]
    sources.extend((proof.get("trading_evidence") or {}).get(key) or {} for key in ("suspension", "limits"))
    for source in sources:
        if not source.get("acquired_at") or datetime.fromisoformat(source["acquired_at"]) > observed_at:
            raise ValueError("当前截点缺少已取得的行情或执行证据")
    close_time = datetime.combine(date.fromisoformat(as_of), time(15), SHANGHAI)
    if any(datetime.fromisoformat(source["acquired_at"]) < close_time for source in (sources[0], sources[3], sources[4])):
        raise ValueError("日线和交易约束须在该交易日收盘后获取并核对")
    if datetime.fromisoformat(proof["dividend_review"]["acquired_at"]).astimezone(SHANGHAI).date() < date.fromisoformat(as_of):
        raise ValueError("分红公告核查日期早于观察日")
    return rows, pd.DataFrame(rows), next_session.isoformat()


def _folder(root, project_id):
    if not re.fullmatch(r"[0-9a-f]{32}", project_id):
        raise ValueError("无效项目编号")
    return Path(root) / "daily-paper" / project_id


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _eligible_asof(as_of, now):
    shanghai_now = now.astimezone(SHANGHAI)
    if as_of > shanghai_now.date() or (as_of == shanghai_now.date() and shanghai_now.time() < time(15)):
        raise ValueError("需等观察日期收盘且日线已取得后再推进")


def list_paper(root, project_id):
    return [_read(path) for path in sorted(_folder(root, project_id).glob("*/*.json"))]


def _project_matches(project, snapshot):
    if project["symbols"] != [snapshot["symbol"]] or snapshot.get("kind") != "quotes" or snapshot["request"].get("adjust") != "3":
        raise ValueError("逐日模拟使用与单标的项目一致的未复权日线快照")


def _provenance(snapshot, frame):
    return {"snapshot_id": snapshot["id"], "rows_sha256": frame_hash(frame),
            "snapshot_sha256": hashlib.sha256(canonical_json(snapshot).encode()).hexdigest()}


def start_paper(root, project, snapshot, as_of, *, observed_at=None):
    observed_at = observed_at or datetime.now(timezone.utc)
    _eligible_asof(as_of, observed_at)
    _project_matches(project, snapshot)
    asof = as_of.isoformat()
    _, frame, next_session = _data(snapshot, asof, observed_at)
    seed = StrategyFactory.generate_signals(frame, RULE["name"], RULE["parameters"]).iloc[-1]
    account = AccountConfig().model_dump(mode="json")
    identifier = uuid4().hex
    record = {
        "id": identifier, "kind": "seed", "project_id": project["id"], "symbol": snapshot["symbol"],
        "as_of": asof, "observed_at": observed_at.isoformat(), **_provenance(snapshot, frame),
        "strategy": RULE, "account": account, "engine": engine_fingerprint(), "receipt": None,
        "plan": {"signal_date": asof, "fast_ma": float(seed.fast_ma), "slow_ma": float(seed.slow_ma),
                 "action": "buy" if seed.trade_signal > 0 else "hold",
                 "target_fraction": account["position_size"] if seed.trade_signal > 0 else None,
                 "next_session": next_session, "execution": "next_verified_tradable_open"},
    }
    existing = list(_folder(root, project["id"]).glob("*/seed.json"))
    if existing:
        raise ValueError("该研究项目已有逐日模拟账户，请使用现有记录推进")
    atomic_json(_folder(root, project["id"]) / identifier / "seed.json", record)
    return record


def advance_paper(root, project, identifier, snapshot, as_of, load_snapshot, *, observed_at=None):
    observed_at = observed_at or datetime.now(timezone.utc)
    _eligible_asof(as_of, observed_at)
    _project_matches(project, snapshot)
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("无效逐日账户编号")
    folder = _folder(root, project["id"]) / identifier
    if not (folder / "seed.json").exists():
        raise ValueError("逐日账户不存在")
    seed = _read(folder / "seed.json")
    asof = as_of.isoformat()
    saved_path = folder / (asof + ".json")
    if saved_path.exists():
        saved = _read(saved_path)
        if saved["snapshot_id"] != snapshot["id"]:
            raise ValueError("该日已入账。修订行情需要单独复核")
        return saved
    steps = sorted(folder.glob("2*.json"))
    previous = _read(steps[-1]) if steps else seed
    if asof <= previous["as_of"]:
        raise ValueError("逐日推进必须晚于当前记录")
    if asof != previous["plan"]["next_session"]:
        raise ValueError("只能推进到前次记录的下一交易日")
    rows, frame, next_session = _data(snapshot, asof, observed_at)
    prior_snapshot = load_snapshot(previous["snapshot_id"])
    if hashlib.sha256(canonical_json(prior_snapshot).encode()).hexdigest() != previous["snapshot_sha256"]:
        raise ValueError("上一日使用的快照未通过完整性校验")
    prior_rows = [row for row in prior_snapshot["rows"] if row["date"] <= previous["as_of"]]
    prefix = [row for row in rows if row["date"] <= previous["as_of"]]
    # A new event column can appear as the snapshot grows. Normalize null-only
    # keys, but disallow changing any observation already used by this account.
    def known(rows):
        return [{key: value for key, value in row.items() if value is not None} for row in rows]

    if known(prefix) != known(prior_rows) or len(rows) != len(prefix) + 1:
        raise ValueError("需要恰好一个新交易日，且历史输入不能改变；请复核缺口或数据修订")
    after_seed = [row for row in rows if row["date"] > seed["as_of"]]
    result = run_backtest({snapshot["symbol"]: frame}, {
        "tickers": [snapshot["symbol"]], "start_date": after_seed[0]["date"], "end_date": asof,
        "account": seed["account"], "strategy": seed["strategy"],
    })
    checkpoint = result["checkpoints"][-1]
    last_decision = result["decisions"][-1]
    pending = checkpoint["pending_orders"]
    if steps:
        previous_state = result["series"][-2]
        confirmed_state = previous["receipt"]["state"]
        if any(previous_state.get(field, 0) != confirmed_state.get(field, 0) for field in (
                "cash", "equity", "positions", "dividend_receivables", "dividend_cash_paid")):
            raise ValueError("当前引擎复算的账户与上一日存档不同，请先复核")
    previous_checkpoint = result["checkpoints"][-2] if steps else None
    prior_orders = previous_checkpoint["pending_orders"] if previous_checkpoint else []
    expected = previous["plan"]
    if steps:
        previous_action = prior_orders[0]["action"] if prior_orders else "hold"
    else:
        warmup = frame.loc[frame["date"] <= seed["as_of"]]
        original = StrategyFactory.generate_signals(warmup, seed["strategy"]["name"], seed["strategy"]["parameters"]).iloc[-1]
        previous_action = "buy" if original.trade_signal > 0 else "hold"
        if any(abs(float(original[field]) - expected[field]) > 1e-10 for field in ("fast_ma", "slow_ma")):
            raise ValueError("复算指标与首份盘后计划不符，请先复核")
    if previous_action != expected["action"] or (prior_orders and (
            prior_orders[0]["target_fraction"] != expected["target_fraction"] or
            prior_orders[0]["signal_date"] != expected["pending_signal_date"])):
        raise ValueError("复算委托与已存盘后计划不符，请先复核")
    trades = [row for row in result["trades"] if row["date"] == asof]
    opening_row = rows[-1]
    if any(not opening_row["limit_down"] <= row["price"] <= opening_row["limit_up"] for row in trades):
        raise ValueError("滑点后的模拟成交价超出当日涨跌停范围，请先复核")
    record = {
        "id": identifier, "kind": "session", "project_id": project["id"], "symbol": snapshot["symbol"],
        "as_of": asof, "observed_at": observed_at.isoformat(), **_provenance(snapshot, frame),
        "strategy": seed["strategy"], "account": seed["account"], "engine": engine_fingerprint(),
        "receipt": {"state": result["series"][-1], "trades": trades,
                    "blocked": [row for row in result["decisions"] if row["date"] == asof and row["status"] in {"deferred", "rejected"}]},
        "plan": {"signal_date": asof, **last_decision["evidence"]["indicators"],
                 "action": pending[0]["action"] if pending else "hold",
                 "target_fraction": pending[0]["target_fraction"] if pending else None,
                 "pending_signal_date": pending[0]["signal_date"] if pending else None,
                 "next_session": next_session, "execution": "next_verified_tradable_open"},
    }
    atomic_json(saved_path, record)
    return record
