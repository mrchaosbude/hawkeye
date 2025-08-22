import types
import hawkeye


def test_get_daily_ohlcv_uses_coinbase(monkeypatch):
    monkeypatch.setattr(hawkeye, "data_source", "coinbase")
    called = {}
    def fake_coinbase(sym, limit=400):
        called["sym"] = sym
        called["limit"] = limit
        return "coinbase"
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv_coinbase", fake_coinbase)
    result = hawkeye.get_daily_ohlcv("ETHUSD", limit=10)
    assert result == "coinbase"
    assert called == {"sym": "ETHUSD", "limit": 10}


def test_get_daily_ohlcv_binance_handles_error(monkeypatch, caplog):
    monkeypatch.setattr(hawkeye, "data_source", "binance")
    class Resp:
        status_code = 400
        text = "invalid"
        def json(self):
            return {"msg": "Invalid symbol"}
    monkeypatch.setattr(
        hawkeye.requests, "get", lambda *a, **k: Resp(), raising=False
    )
    with caplog.at_level(hawkeye.logging.ERROR):
        result = hawkeye.get_daily_ohlcv("BAD")
    assert result is None
    assert "Binance API error for BAD" in caplog.text
    assert "Invalid symbol" in caplog.text
    assert "Client Error" not in caplog.text
