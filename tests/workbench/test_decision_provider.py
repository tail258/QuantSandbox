"""Exercise the decision feed's normalization without a live market connection."""
from datetime import date
import subprocess
from types import SimpleNamespace

import pytest

from backend.workbench import decision_provider as provider


def identity(**changes):
    return {"code": "sh.600105", "code_name": "永鼎股份", "type": "1", "status": "1",
            "ipoDate": "1997-09-29"} | changes


def bar(**changes):
    return {"date": "2026-11-12", "code": "sh.600105", "adjustflag": "3", "tradestatus": "1",
            "open": "24.38", "high": "25.20", "low": "23.71", "close": "23.76",
            "preclose": "24.41", "volume": "129770660"} | changes


class Response:
    error_code = "0"
    error_msg = "success"

    def __init__(self, rows):
        self.fields = list(rows[0]) if rows else []
        self._rows = iter([list(row.values()) for row in rows])

    def next(self):
        self._current = next(self._rows, None)
        return self._current is not None

    def get_row_data(self):
        return self._current


class BaoStock:
    logged_out = False

    def login(self):
        return Response([])

    def logout(self):
        self.logged_out = True

    def query_stock_basic(self, *, code):
        assert code == "sh.600105"
        return Response([identity()])

    def query_trade_dates(self, *, start_date, end_date):
        assert (start_date, end_date) == ("2026-11-12", "2026-11-16")
        return Response([{"calendar_date": f"2026-11-{day}", "is_trading_day": flag}
                         for day, flag in [(12, "1"), (13, "1"), (14, "0"), (15, "0"), (16, "1")]])

    def query_history_k_data_plus(self, code, fields, *, start_date, end_date, frequency, adjustflag):
        assert (code, start_date, end_date, frequency, adjustflag) == (
            "sh.600105", "2026-11-12", "2026-11-13", "d", "3")
        assert set(fields.split(",")) == set(bar())
        return Response([bar(), bar(date="2026-11-13", tradestatus="0", open="23.76", high="23.76",
                                    low="23.76", close="23.76", preclose="23.76", volume="0")])


def test_capture_preserves_history_provenance_reference_and_explicit_suspension():
    client = BaoStock()
    result = provider._capture(client, "600105", "2026-11-12", "2026-11-13", "2026-11-16")
    assert result["instrument"] == {"symbol": "600105", "name": "永鼎股份", "exchange": "SSE",
                                    "kind": "stock", "listed": True, "ipo_date": "1997-09-29"}
    assert result["calendar"]["sessions"] == ["2026-11-12", "2026-11-13", "2026-11-16"]
    assert result["calendar"]["start_date"] == "2026-11-12"
    assert result["calendar"]["end_date"] == "2026-11-16"
    assert result["source"] == "BaoStock"
    assert result["rows"] == [
        {"date": "2026-11-12", "open": 24.38, "high": 25.20, "low": 23.71, "close": 23.76,
         "volume": 129770660, "is_suspended": False, "prev_close": 24.41},
        {"date": "2026-11-13", "open": 23.76, "high": 23.76, "low": 23.76, "close": 23.76,
         "volume": 0, "is_suspended": True, "prev_close": 23.76},
    ]
    assert client.logged_out


def test_etf_identity_requires_the_verified_category_and_precise_prices():
    identity_rows = [identity(code="sz.159915", code_name="创业板ETF", type="5", ipoDate="2011-12-09")]
    result = provider._instrument(identity_rows, "159915", provider._market("159915"))
    assert result["kind"] == "etf"
    assert result["exchange"] == "SZSE"
    observations = provider._daily_rows(
        [bar(code="sz.159915", open="2.9110", high="2.9180", low="2.9030", close="2.9050", preclose="2.9100")],
        "sz.159915", date(2026, 11, 12), date(2026, 11, 12))
    assert observations[0]["close"] == 2.905


@pytest.mark.parametrize(("rows", "reason"), [
    ([], "身份资料"),
    ([identity(code="sz.600105")], "不一致"),
    ([identity(type="2")], "证券类别"),
    ([identity(status="0")], "已退市"),
    ([identity(status="")], "上市状态"),
    ([identity(ipoDate="")], "证券上市日"),
])
def test_rejects_unverified_instrument_records(rows, reason):
    with pytest.raises(ValueError, match=reason):
        provider._instrument(rows, "600105", provider._market("600105"))


@pytest.mark.parametrize("symbol", ["920001", "900901", "200002", "510300.SS", "１２３４５６"])
def test_symbol_outside_supported_exchange_codes_is_explicit(symbol):
    with pytest.raises(provider.UnsupportedInstrument):
        provider._market(symbol)


def test_calendar_missing_saturday_remains_unknown_and_never_becomes_a_holiday():
    first, last = date(2026, 11, 13), date(2026, 11, 15)
    rows = [{"calendar_date": "2026-11-13", "is_trading_day": "1"},
            {"calendar_date": "2026-11-15", "is_trading_day": "0"}]
    with pytest.raises(ValueError, match="缺少 2026-11-14"):
        provider._calendar(rows, first, last)
    with pytest.raises(ValueError, match="异常日期或交易状态"):
        provider._calendar([*rows, {"calendar_date": "2026-11-14", "is_trading_day": ""}], first, last)
    with pytest.raises(ValueError, match="异常日期或交易状态"):
        provider._calendar([*rows, rows[0]], first, last)


@pytest.mark.parametrize(("change", "reason"), [
    ({"adjustflag": "2"}, "不复权标记"),
    ({"code": "sh.600519"}, "证券代码"),
    ({"tradestatus": ""}, "状态未知"),
    ({"volume": "0"}, "成交量与交易状态"),
    ({"volume": "3.1"}, "成交量与交易状态"),
    ({"tradestatus": "0"}, "成交量与交易状态"),
    ({"tradestatus": "0", "volume": "0"}, "停牌价格"),
    ({"open": "NaN"}, "open 缺失或无效"),
    ({"high": "23.75"}, "OHLC"),
    ({"preclose": ""}, "preclose 缺失或无效"),
    ({"date": "2026-11-16"}, "超出请求区间"),
])
def test_rejects_invalid_or_ambiguous_raw_daily_rows(change, reason):
    with pytest.raises(ValueError, match=reason):
        provider._daily_rows([bar(**change)], "sh.600105", date(2026, 11, 12), date(2026, 11, 13))


def test_empty_history_leaves_coverage_to_the_calling_service():
    first, last = date(2026, 11, 12), date(2026, 11, 13)
    assert provider._daily_rows([], "sh.600105", first, last) == []
    with pytest.raises(ValueError, match="重复"):
        provider._daily_rows([bar(), bar()], "sh.600105", first, last)


def test_upstream_failure_during_pagination_is_not_success():
    class FailedPage(Response):
        def next(self):
            if super().next():
                return True
            self.error_code = "10001001"
            self.error_msg = "用户未登录"
            return False

    with pytest.raises(ValueError, match="10001001.*用户未登录"):
        provider._rows(FailedPage([bar()]), "日线查询")


def test_fetch_uses_a_bounded_process_and_preserves_unsupported_errors(monkeypatch):
    args = ("600105", "2026-11-12", "2026-11-13", "2026-11-16")

    def timeout(cmd, **kwargs):
        assert cmd[1:5] == ["-X", "utf8", "-m", "backend.workbench.decision_provider"]
        assert cmd[5:] == list(args)
        assert kwargs["timeout"] == provider.FETCH_TIMEOUT
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(provider.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="超时"):
        provider.fetch_daily_market(*args)

    monkeypatch.setattr(provider.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout='{"ok": false, "error": "已退市", "unsupported": true}', stderr=""))
    with pytest.raises(provider.UnsupportedInstrument, match="已退市"):
        provider.fetch_daily_market(*args)
