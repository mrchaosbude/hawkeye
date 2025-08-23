import binance_client
import hawkeye


def test_place_protective_order_types(monkeypatch):
    client = binance_client.BinanceClient("k", "s")

    def fake_get(url, params=None, timeout=10):
        class R:
            def raise_for_status(self):
                pass
            def json(self):
                return {"price": "100"}
        return R()

    calls = []
    def fake_post(url, headers=None, params=None, timeout=10):
        calls.append(params)
        class R:
            def raise_for_status(self):
                pass
            def json(self):
                return {}
        return R()

    monkeypatch.setattr(binance_client.requests, "get", fake_get, raising=False)
    monkeypatch.setattr(binance_client.requests, "post", fake_post, raising=False)

    client.place_protective_order("BTCUSDT", "SELL", 1.0, 99.0)
    client.place_protective_order("BTCUSDT", "SELL", 1.0, 105.0)

    assert calls[0]["type"] == "STOP_MARKET"
    assert calls[1]["type"] == "TAKE_PROFIT_MARKET"


def test_check_price_places_protective_orders(monkeypatch):
    class DummyBot:
        def send_message(self, *a, **k):
            pass
        def send_photo(self, *a, **k):
            pass
        def message_handler(self, *a, **k):
            def decorator(func):
                return func
            return decorator
        def infinity_polling(self, *a, **k):
            pass

    monkeypatch.setattr(hawkeye, "bot", DummyBot())

    hawkeye.users = {
        "1": {
            "notifications": True,
            "binance_api_key": "k",
            "binance_api_secret": "s",
            "symbols": {"BTCUSDT": {"trade_amount": 100.0}},
        }
    }
    hawkeye.binance_clients = {}
    hawkeye.auto_stop = 1.0
    hawkeye.auto_takeprofit = 2.0

    class DummySignals:
        def __init__(self, signal):
            self.signal = signal
        class _ILoc:
            def __init__(self, signal):
                self.signal = signal
            def __getitem__(self, idx):
                return {"Signal": self.signal}
        @property
        def iloc(self):
            return self._ILoc(self.signal)

    monkeypatch.setattr(hawkeye, "get_price", lambda sym: 100.0)
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv", lambda sym: object())
    monkeypatch.setattr(hawkeye.strategy, "generate_signals", lambda asset, bench: DummySignals("buy"))
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    monkeypatch.setattr(hawkeye, "translate", lambda cid, key, **kwargs: key)
    monkeypatch.setattr(hawkeye, "generate_buy_sell_chart", lambda sym: None)

    class DummyClient:
        def __init__(self, api_key, api_secret):
            self.api_key = api_key
            self.api_secret = api_secret
            self.orders = []
            self.protective = []
        def balance(self):
            return 1000.0
        def order(self, symbol, side, qty):
            self.orders.append((symbol, side, qty))
        def place_protective_order(self, symbol, side, qty, stop_price):
            self.protective.append((symbol, side, qty, stop_price))

    monkeypatch.setattr(hawkeye, "BinanceClient", DummyClient)

    hawkeye.check_price()

    client = hawkeye.binance_clients["1"]
    assert client.orders == [("BTCUSDT", "BUY", 1.0)]
    assert (
        client.protective
        == [
            ("BTCUSDT", "SELL", 1.0, 99.0),
            ("BTCUSDT", "SELL", 1.0, 102.0),
        ]
    )
