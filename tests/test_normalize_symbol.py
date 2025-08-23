import hawkeye


def test_normalize_symbol_adds_default(monkeypatch):
    monkeypatch.setattr(hawkeye, "DEFAULT_QUOTE", "USDT")
    assert hawkeye.normalize_symbol("btc") == "BTCUSDT"


def test_normalize_symbol_handles_existing_quote(monkeypatch):
    monkeypatch.setattr(hawkeye, "DEFAULT_QUOTE", "USDT")
    assert hawkeye.normalize_symbol("ETHBUSD") == "ETHBUSD"


def test_normalize_symbol_exceptions(monkeypatch):
    monkeypatch.setattr(hawkeye, "DEFAULT_QUOTE", "USDT")
    assert hawkeye.normalize_symbol("USDT") is None
    assert hawkeye.normalize_symbol("BUSD") == "BUSDUSDT"
