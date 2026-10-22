from modules.hot_tickers import earnings_in_universe, pick_quotes


def _q(symbol, cap=50e9, chg=1.0):
    return {"symbol": symbol, "marketCap": cap, "regularMarketChangePercent": chg, "shortName": symbol + " Inc"}


def test_pick_quotes_drops_microcaps_foreign_and_share_classes():
    quotes = [_q("AAA"), _q("TINY", cap=1e8), _q("BRK-B"), _q("SHOP.TO"), _q("BBB")]
    assert [r["symbol"] for r in pick_quotes(quotes)] == ["AAA", "BBB"]


def test_pick_quotes_respects_limit_and_missing_cap():
    quotes = [_q(f"T{i}") for i in range(10)] + [{"symbol": "NOCAP"}]
    assert len(pick_quotes(quotes, limit=3)) == 3
    assert pick_quotes([{"symbol": "NOCAP"}]) == []


def test_earnings_in_universe_filters_and_sorts_by_date():
    cal = [
        {"symbol": "ZZZ", "date": "2026-10-25"},
        {"symbol": "NVDA", "date": "2026-10-28"},
        {"symbol": "AAPL", "date": "2026-10-23"},
    ]
    out = earnings_in_universe(cal, {"NVDA", "AAPL"})
    assert [e["symbol"] for e in out] == ["AAPL", "NVDA"]
