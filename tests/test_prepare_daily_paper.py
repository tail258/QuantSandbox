from datetime import date
import hashlib
import json

import pytest

from scripts.prepare_daily_paper import prepare_input


OBSERVATION = date(2026, 11, 16)
PREVIOUS = "2026-11-13"
NEXT = "2026-11-17"


@pytest.fixture
def inputs():
    source = {"name": "BaoStock", "url": "https://www.baostock.com/",
              "acquired_at": "2026-11-13T12:00:00+00:00", "method": "日线"}
    prior = {"id": "a" * 20, "symbol": "000338", "kind": "quotes",
             "request": {"start": PREVIOUS, "end": PREVIOUS, "adjust": "3"},
             "rows": [{"date": PREVIOUS, "open": 19.84, "high": 20.18, "low": 18.66, "close": 18.75,
                       "volume": 112480805, "limit_up": 21.78, "limit_down": 17.82, "is_suspended": False,
                       "cash_dividend_per_share": None}],
             "execution_history": {"price_source": source, "trading_evidence": {"rule_urls": [], "limits_kind": "rule_derived"},
                                   "calendar": {"sessions": [PREVIOUS], "next_session": str(OBSERVATION), "source": source},
                                   "dividend_events": []}}
    review = {"schema": "quantsandbox.cash-dividend-source.v1", "symbol": "000338", "exchange": "SZSE",
              "share_class": "A", "currency": "CNY", "reviewed_from": PREVIOUS, "reviewed_through": str(OBSERVATION),
              "checked_at": "2026-11-16T09:00:00+00:00", "query_source_url": "https://www.cninfo.com.cn/",
              "method": "Planned observation fixture", "events": []}
    capture = {"source": "https://www.baostock.com/", "fetched_at": "2026-11-16T09:01:00+00:00",
               "bars": [{"date": str(OBSERVATION), "code": "sz.000338", "adjustflag": "3", "open": "19.00",
                         "high": "19.31", "low": "18.66", "close": "19.20", "volume": "1234567",
                         "preclose": "18.75", "tradestatus": "1", "isST": "0"}],
               "calendar": [{"calendar_date": day, "is_trading_day": "1"} for day in (str(OBSERVATION), NEXT)]}
    return prior, review, capture


def test_prepares_one_session_and_hashes_the_raw_inputs(inputs):
    prior, review, capture = inputs
    proposed, raw = prepare_input(prior, OBSERVATION, json.dumps(review).encode(), capture)
    assert proposed.calendar.sessions == [date.fromisoformat(PREVIOUS), OBSERVATION]
    assert proposed.calendar.next_session == date.fromisoformat(NEXT)
    assert proposed.rows[0].model_dump(mode="json") == {key: value for key, value in prior["rows"][0].items()
                                                        if key != "cash_dividend_per_share"}
    assert proposed.rows[1].limit_up == 20.63
    assert proposed.rows[1].limit_down == 16.88
    assert proposed.price_source.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert json.loads(raw)["bars"] == capture["bars"]


@pytest.mark.parametrize("problem", ["calendar_gap", "stale_review", "old_dividend_revised", "after_next_open", "risk_warning", "published_limits"])
def test_blocks_unusable_input_without_rewriting_prior_rows(inputs, problem):
    prior, review, capture = inputs
    if problem == "calendar_gap":
        capture["calendar"][1]["calendar_date"] = "2026-11-18"
    elif problem == "stale_review":
        review["reviewed_through"] = PREVIOUS
    elif problem == "old_dividend_revised":
        review["events"] = [{"record_date": PREVIOUS, "ex_date": str(OBSERVATION), "pay_date": str(OBSERVATION),
                             "announced_date": "2026-11-12", "cash_per_share": .5, "source_url": "https://www.cninfo.com.cn/"}]
    elif problem == "after_next_open":
        capture["fetched_at"] = "2026-11-17T01:30:00+00:00"
    elif problem == "published_limits":
        prior["execution_history"]["trading_evidence"]["limits_kind"] = "published"
    else:
        capture["bars"][0]["isST"] = "1"
    before = json.dumps(prior)
    with pytest.raises(ValueError):
        prepare_input(prior, OBSERVATION, json.dumps(review).encode(), capture)
    assert before == json.dumps(prior)
