"""Market-qualified research identities; strategy execution remains A-share only."""
import re


def valid_project_symbol(symbol: str) -> bool:
    return isinstance(symbol, str) and bool(re.fullmatch(r"(?:\d{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,3})?)", symbol))
