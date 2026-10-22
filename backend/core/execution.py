"""Daily-open matching, lot sizing, price limits and T+1 eligibility."""
import math
import pandas as pd


def _number(value):
    if value is None or pd.isna(value):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _date(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def execute_order(ledger, ticker, day, row, order, previous_equity):
    """Match one due order; deferred and T+1 orders remain pending at the caller."""
    settings = order["settings"]
    position = ledger.positions[ticker]
    action = order["action"]
    raw_price = float(row.open)
    target_value = previous_equity * order["target_fraction"]
    if action == "rebalance":
        action = "sell" if position["shares"] * raw_price > target_value else "buy"
    blocked = row.volume <= 0 or bool(row.get("is_suspended", False))
    if action == "buy" and _number(row.get("limit_up")) is not None:
        blocked = blocked or raw_price >= float(row.limit_up) - 1e-8
    if action == "sell" and _number(row.get("limit_down")) is not None:
        blocked = blocked or raw_price <= float(row.limit_down) + 1e-8
    if blocked:
        return {"status": "deferred", "action": action}
    price = raw_price * (1 + settings["slippage_bps"] / 10000 * (1 if action == "buy" else -1))
    lot = settings["lot_size"]
    realized = 0.0
    closed = False
    cycle_pnl = 0.0
    if action == "buy":
        budget = min(ledger.cash, max(0, target_value - position["shares"] * raw_price))
        qty = int(budget / (price * (1 + settings["commission_rate"])) // lot) * lot
        while qty and qty * price + max(settings["min_commission"], qty * price * settings["commission_rate"]) > budget + 1e-8:
            qty -= lot
        if qty:
            value, fee = ledger.buy(ticker, day, qty, price, settings)
    else:
        if position.get("last_buy_date") == _date(day):
            return {"status": "t_plus_one", "action": action}
        if order["action"] == "rebalance":
            keep = int(target_value / raw_price // lot) * lot
            qty = max(0, position["shares"] - keep)
        else:
            qty = position["shares"]
        if qty:
            value, fee, realized, closed, cycle_pnl = ledger.sell(ticker, qty, price, settings)
    return {"status": "filled" if qty else "rejected", "action": action, "raw_price": raw_price, "price": price, "qty": qty,
            "value": value if qty else 0.0, "fee": fee if qty else 0.0, "realized": realized, "closed": closed, "cycle_pnl": cycle_pnl}
