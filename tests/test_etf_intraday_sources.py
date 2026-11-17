import pytest

from backend.workbench.etf_intraday_sources import SourceError, parse_eastmoney_bars, parse_tencent_quotes


def minute(time="2026-11-05 09:35", volume="100", amount="40000"):
    return f"{time},4,4,4.1,3.9,{volume},{amount},0,0,0,0"


def payload(lines):
    return {"data": {"code": "510300", "klines": lines}}


def test_reported_amount_and_units():
    row = parse_eastmoney_bars(payload([minute(amount="39987.12")]), "510300")[0]
    assert row["amount_cny"] == 39987.12
    assert row["volume_shares"] == 10000
    assert row["time"] == "2026-11-05T09:35:00+08:00"


@pytest.mark.parametrize("lines", [[minute("2026-11-05 09:30")], [minute("2026-11-05 12:00")],
    [minute("2026-11-05 09:36")], [minute(), minute()],
    [minute("2026-11-05 09:40"), minute()], ["2026-11-05 09:35,1,2"]])
def test_invalid_minute_structure(lines):
    with pytest.raises(SourceError):
        parse_eastmoney_bars(payload(lines), "510300")


def test_missing_values_are_not_zero():
    row = parse_eastmoney_bars(payload([minute(volume="nan", amount="-")]), "510300")[0]
    assert row["amount_cny"] is None
    assert row["volume_shares"] is None


def quote(**changes):
    fields = [""] * 38
    for key, value in {1:"ETF",2:"510300",3:"4.124",4:"4.195",6:"12629370",30:"20261106161452",
                       35:"4.124/12629370/5211672667",37:"521167",**changes}.items():
        fields[int(key)] = value
    return 'v_sh510300="' + "~".join(fields) + '";'


def test_quote_exact_reported_turnover():
    row = parse_tencent_quotes(quote(), ["510300"])[0]
    assert row["amount_cny"] == 5211672667
    assert row["volume_shares"] == 1262937000
    assert row["source_time"] == "2026-11-06T16:14:52+08:00"
    assert row['last'] == 4.124
    assert row['price_raw'] == '4.124' and row['price_decimals'] == 3


def test_source_price_precision_keeps_trailing_zero():
    row = parse_tencent_quotes(quote(**{'3': '4.100'}), ['510300'])[0]
    assert row['last'] == 4.1
    assert row['price_raw'] == '4.100' and row['price_decimals'] == 3


@pytest.mark.parametrize("changes", [{"37":"521"}, {"35":"4.124/2/5211672667"}, {"30":"bad"}, {"2":"159915"}])
def test_quote_rejects_misaligned_units_and_timestamps(changes):
    with pytest.raises(SourceError):
        parse_tencent_quotes(quote(**changes), ["510300"])


def test_missing_exact_quote_amount_remains_null():
    assert parse_tencent_quotes(quote(**{"35":""}), ["510300"])[0]["amount_cny"] is None


def test_archive_resolves_current_store_scope_at_request_time(tmp_path, monkeypatch):
    from backend.workbench import etf_intraday_sources as sources, store

    class Response:
        content = b"archived response"
        status_code = 200

        def raise_for_status(self):
            pass

    monkeypatch.setattr(sources.requests, "get", lambda *args, **kwargs: Response())
    default = tmp_path / "cli-data"
    monkeypatch.setattr(store, "DATA", default)
    sources._request("https://example.com/quote")
    assert len(list((default / "etf-intraday-sources").glob("*.raw"))) == 1
    for name in ["workspace-a", "workspace-b"]:
        selected = tmp_path / name
        token = store._scope_data.set(selected)
        try:
            sources._request("https://example.com/quote")
            assert len(list((selected / "etf-intraday-sources").glob("*.raw"))) == 1
            explicit = tmp_path / (name + "-explicit")
            sources._request("https://example.com/quote", archive_dir=explicit)
            assert len(list(explicit.glob("*.raw"))) == 1
            assert len(list((selected / "etf-intraday-sources").glob("*.raw"))) == 1
        finally:
            store._scope_data.reset(token)
    assert len(list((default / "etf-intraday-sources").glob("*.raw"))) == 1
