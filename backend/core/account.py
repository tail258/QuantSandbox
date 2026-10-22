"""Account configuration and long-only cash/position ledger."""
import math
import pandas as pd


def _date(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d")


ACCOUNT_DEFAULTS = {"initial_cash": 100000.0, "commission_rate": 0.00025,
                    "tax_rate": 0.0005, "min_commission": 5.0, "slippage_bps": 5.0,
                    "position_size": 0.3, "lot_size": 100, "execution_delay": 1}


def normalize_account(config):
    account = {**ACCOUNT_DEFAULTS, **config.get("account", {})}
    for key in ACCOUNT_DEFAULTS:
        value = account[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"账户参数 {key} 必须为有限数值")
    if account["initial_cash"] <= 0 or not 0 <= account["position_size"] <= 1:
        raise ValueError("初始资金必须为正数，单标的仓位须在 0–1 之间")
    for key in ("commission_rate", "tax_rate"):
        if not 0 <= account[key] <= 0.1:
            raise ValueError(f"{key} 须在 0–0.1 之间")
    if account["min_commission"] < 0 or not 0 <= account["slippage_bps"] <= 1000:
        raise ValueError("最低佣金不能为负，滑点须在 0–1000 bps 之间")
    for key in ("lot_size", "execution_delay"):
        if account[key] < 1 or int(account[key]) != account[key]:
            raise ValueError(f"{key} 必须为正整数")
        account[key] = int(account[key])
    return account


class AccountLedger:
    """Own cash and position basis; settlement uses unrounded execution amounts."""
    def __init__(self, initial_cash, tickers):
        self.cash = float(initial_cash)
        self.positions = {t: {"shares": 0, "cost_basis": 0.0, "entry_date": None, "cycle_pnl": 0.0} for t in tickers}

    def buy(self, ticker, day, qty, price, settings):
        position = self.positions[ticker]
        value = qty * price
        fee = max(settings["min_commission"], value * settings["commission_rate"])
        self.cash -= value + fee
        if not position["shares"]:
            position["entry_date"] = _date(day)
            position["cycle_pnl"] = 0.0
        position["shares"] += qty
        position["cost_basis"] += value + fee
        position["last_buy_date"] = _date(day)
        return value, fee

    def sell(self, ticker, qty, price, settings):
        position = self.positions[ticker]
        closed, cycle_pnl = False, 0.0
        value = qty * price
        fee = max(settings["min_commission"], value * settings["commission_rate"]) + value * settings["tax_rate"]
        removed_basis = position["cost_basis"] * qty / position["shares"]
        realized = value - fee - removed_basis
        self.cash += value - fee
        position["cost_basis"] -= removed_basis
        position["shares"] -= qty
        position["cycle_pnl"] += realized
        if not position["shares"]:
            closed = True
            cycle_pnl = position["cycle_pnl"]
            position["cost_basis"] = 0.0
            position["entry_date"] = None
        return value, fee, realized, closed, cycle_pnl
