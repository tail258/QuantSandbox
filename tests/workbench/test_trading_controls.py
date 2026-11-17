from datetime import date

import pytest

from backend.workbench.trading_controls import SZSE_ORDINARY_A_SHARE_RULES, baostock_szse_controls


def bar(day="2026-10-23", **overrides):
    return {"date": day, "code": "sz.000338", "adjustflag": "3", "open": "20.35", "close": "21.49",
            "high": "21.52", "low": "20.14", "volume": "120173991", "preclose": "20.73",
            "tradestatus": "1", "isST": "0", **overrides}


def parse(rows, *, attest=True):
    days = [date.fromisoformat(row["date"]) for row in rows] if attest else []
    return baostock_szse_controls(rows, "000338", ordinary_sessions=days)


def test_uses_ex_reference_and_selects_dated_exchange_rules():
    raw = [bar("2023-03-31"), bar("2023-04-10"), bar("2026-10-22", preclose="21.88"), bar()]
    rows, review = parse(raw)
    assert rows[-1]["limit_up"] == 22.80
    assert rows[-1]["limit_down"] == 18.66
    assert rows[-1]["volume"] == 120173991
    assert rows[-1]["is_suspended"] is False
    assert set(review["rule_urls"]) == {url for _, url in SZSE_ORDINARY_A_SHARE_RULES}
    assert review["gaps"] == {}


def test_rounds_at_half_cent_using_exchange_tick():
    rows, _ = parse([bar(preclose="20.75")])
    assert rows[0]["limit_up"] == 22.83  # 22.825 rounds up, not banker's rounding.
    assert rows[0]["limit_down"] == 18.68


def test_leaves_limits_unknown_without_scope_or_valid_daily_evidence():
    rows, review = parse([bar()], attest=False)
    assert rows[0]["is_suspended"] is False
    assert rows[0]["limit_up"] is None
    assert review["gaps"] == {"2026-10-23": "ordinary_limit_regime_unconfirmed"}

    rows, review = parse([bar("2026-10-19", isST="1"), bar("2026-10-20", preclose=""),
                          bar("2026-10-21", high="22.81"), bar("2026-10-22", tradestatus="0"),
                          bar("2026-10-23", tradestatus="0", volume="0")])
    assert all(row["limit_up"] is None and row["limit_down"] is None for row in rows)
    assert rows[3]["is_suspended"] is None
    assert rows[4]["is_suspended"] is True
    assert review["gaps"] == {
        "2026-10-19": "unknown_or_special_treatment", "2026-10-20": "missing_or_invalid_reference_price",
        "2026-10-21": "observed_prices_outside_derived_limits", "2026-10-22": "unknown_or_inconsistent_trading_status",
    }


@pytest.mark.parametrize("raw", [[bar(adjustflag="2")], [bar(), bar()], [bar(volume="")]])
def test_invalid_price_history_is_rejected(raw):
    with pytest.raises(ValueError):
        parse(raw)
