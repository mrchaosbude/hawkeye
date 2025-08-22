import pytest
import strategies.arbitrage as arb


# Helper to patch pandas.DataFrame used inside the strategy

def _patch_dataframe(monkeypatch):
    """Replace pandas.DataFrame with a simple identity function."""
    monkeypatch.setattr(arb.pd, "DataFrame", lambda rows: rows, raising=False)


# Helper to mock requests.get to return predefined prices

def _mock_prices(monkeypatch, binance_price, coinbase_price):
    class Resp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            pass

    def fake_get(url, *args, **kwargs):
        if "binance" in url:
            return Resp({"price": str(binance_price)})
        assert "coinbase" in url
        return Resp({"data": {"amount": str(coinbase_price)}})

    monkeypatch.setattr(arb.requests, "get", fake_get, raising=False)


def test_generate_signals_hold(monkeypatch):
    """No arbitrage opportunity should emit a hold signal."""
    _patch_dataframe(monkeypatch)
    _mock_prices(monkeypatch, 100.0, 100.0)
    strategy = arb.ArbitrageStrategy()
    result = strategy.generate_signals()
    assert result[0]["Signal"] == "hold"


def test_generate_signals_buy_binance_sell_coinbase(monkeypatch):
    """Positive spread where Binance is cheaper should signal buy on Binance."""
    _patch_dataframe(monkeypatch)
    _mock_prices(monkeypatch, 100.0, 102.0)
    strategy = arb.ArbitrageStrategy()
    result = strategy.generate_signals()
    assert result[0]["Signal"] == "buy_binance_sell_coinbase"


def test_generate_signals_buy_coinbase_sell_binance(monkeypatch):
    """Positive spread where Coinbase is cheaper should signal buy on Coinbase."""
    _patch_dataframe(monkeypatch)
    _mock_prices(monkeypatch, 105.0, 100.0)
    strategy = arb.ArbitrageStrategy()
    result = strategy.generate_signals()
    assert result[0]["Signal"] == "buy_coinbase_sell_binance"


def test_generate_signals_raises_on_binance_error(monkeypatch):
    """HTTP errors from Binance should propagate."""
    _patch_dataframe(monkeypatch)

    class HTTPError(Exception):
        pass

    def fake_get(url, *args, **kwargs):
        raise HTTPError("boom")

    monkeypatch.setattr(arb.requests, "get", fake_get, raising=False)

    with pytest.raises(HTTPError):
        arb.ArbitrageStrategy().generate_signals()


def test_generate_signals_raises_on_coinbase_error(monkeypatch):
    """Errors from Coinbase requests should also propagate."""
    _patch_dataframe(monkeypatch)

    class HTTPError(Exception):
        pass

    class Resp:
        def __init__(self, payload=None, error=None):
            self._payload = payload
            self._error = error

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self._error:
                raise self._error

    def fake_get(url, *args, **kwargs):
        if "binance" in url:
            return Resp({"price": "100"})
        return Resp(error=HTTPError("fail"))

    monkeypatch.setattr(arb.requests, "get", fake_get, raising=False)

    with pytest.raises(HTTPError):
        arb.ArbitrageStrategy().generate_signals()
