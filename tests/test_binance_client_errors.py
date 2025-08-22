import pytest
import binance_client


def test_order_timeout(monkeypatch):
    client = binance_client.BinanceClient("k", "s")

    def fake_post(*args, **kwargs):
        raise binance_client.Timeout("timeout")

    monkeypatch.setattr(binance_client.requests, "post", fake_post, raising=False)

    with pytest.raises(binance_client.BinanceAPIError):
        client.order("BTCUSDT", "BUY", 1.0)


def test_balance_request_exception(monkeypatch):
    client = binance_client.BinanceClient("k", "s")

    def fake_get(*args, **kwargs):
        raise binance_client.RequestException("boom")

    monkeypatch.setattr(binance_client.requests, "get", fake_get, raising=False)

    with pytest.raises(binance_client.BinanceAPIError):
        client.balance()
