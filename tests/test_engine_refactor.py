"""Independent ledger, execution and provenance contracts after engine decomposition."""
from pathlib import Path

import pandas as pd
import pytest

from backend.core.account import AccountLedger, normalize_account
from backend.core.execution import execute_order
from backend.services import provenance


def order(action="buy", target=1):
    return {"action": action, "target_fraction": target, "settings": normalize_account({"account": {
        "min_commission": 5, "commission_rate": .001, "tax_rate": .002, "slippage_bps": 0}})}


def bar(**changes):
    return pd.Series({"open": 10., "volume": 1000, **changes})


def test_settlement_allocates_basis_and_closes_complete_cycle():
    ledger = AccountLedger(10000, ["AAA"])
    settings = order()["settings"]
    ledger.buy("AAA", "2024-01-01", 500, 10, settings)
    assert ledger.cash == 4995
    assert ledger.positions["AAA"]["cost_basis"] == 5005
    value, fee, realized, closed, cycle = ledger.sell("AAA", 200, 11, settings)
    assert (value, fee, closed, cycle) == (2200, 9.4, False, 0)
    assert realized == pytest.approx(188.6)
    _, _, final_realized, closed, cycle = ledger.sell("AAA", 300, 9, settings)
    assert closed and cycle == pytest.approx(realized + final_realized)
    assert ledger.positions["AAA"]["cost_basis"] == 0
    assert ledger.cash == pytest.approx(10000 + cycle)


def test_matcher_enforces_t_plus_one_without_mutating_ledger():
    ledger = AccountLedger(10000, ["AAA"])
    fill = execute_order(ledger, "AAA", "2024-01-01", bar(), order(), 10000)
    assert fill["qty"] == 900  # Minimum commission must fit within the cash budget.
    cash = ledger.cash
    shares = ledger.positions["AAA"]["shares"]
    result = execute_order(ledger, "AAA", "2024-01-01", bar(), order("sell", 0), 10000)
    assert result["status"] == "t_plus_one"
    assert ledger.cash == cash and ledger.positions["AAA"]["shares"] == shares
    result = execute_order(ledger, "AAA", "2024-01-02", bar(), order("sell", 0), 10000)
    assert result["status"] == "filled" and result["closed"]


@pytest.mark.parametrize("changes", [{"volume": 0}, {"is_suspended": True}, {"limit_up": 10}])
def test_blocked_match_preserves_cash_and_position(changes):
    ledger = AccountLedger(10000, ["AAA"])
    result = execute_order(ledger, "AAA", "2024-01-01", bar(**changes), order(), 10000)
    assert result["status"] == "deferred"
    assert ledger.cash == 10000 and ledger.positions["AAA"]["shares"] == 0


@pytest.mark.parametrize("filename", ["core/account.py", "core/execution.py", "core/metrics.py", "api/schemas.py"])
def test_fingerprint_includes_split_computation_modules(monkeypatch, filename):
    original = Path.read_bytes
    target = Path(provenance.__file__).resolve().parents[1] / filename
    before = provenance.engine_fingerprint()
    def changed(path):
        data = original(path)
        return data + b"\n# fingerprint probe" if path == target else data
    monkeypatch.setattr(Path, "read_bytes", changed)
    assert provenance.engine_fingerprint()["source_sha256"] != before["source_sha256"]
    # A previously captured execution fingerprint is a value, not a live view.
    assert before != provenance.engine_fingerprint()
