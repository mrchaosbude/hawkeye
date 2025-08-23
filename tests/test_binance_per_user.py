import hawkeye


def test_orders_use_user_specific_binance_clients(monkeypatch):
    class DummyBot:
        def send_message(self, *args, **kwargs):
            pass
        def send_photo(self, *args, **kwargs):
            pass
        def message_handler(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def infinity_polling(self, *args, **kwargs):
            pass
    monkeypatch.setattr(hawkeye, "bot", DummyBot())

    hawkeye.users = {
        "1": {
            "notifications": True,
            "binance_api_key": "k1",
            "binance_api_secret": "s1",
            "symbols": {"BTCUSDT": {"trade_amount": 100.0, "position": 1.0}},
        },
        "2": {
            "notifications": True,
            "binance_api_key": "k2",
            "binance_api_secret": "s2",
            "symbols": {"ETHUSDT": {"trade_amount": 200.0, "position": 2.0}},
        },
    }

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
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv", lambda sym, limit=400: object())
    monkeypatch.setattr(hawkeye.strategy, "generate_signals", lambda asset, bench: DummySignals("sell"))
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    monkeypatch.setattr(hawkeye, "translate", lambda cid, key, **kwargs: key)
    monkeypatch.setattr(hawkeye, "generate_buy_sell_chart", lambda sym: None)

    created_clients = {}

    class DummyClient:
        def __init__(self, api_key, api_secret):
            self.api_key = api_key
            self.api_secret = api_secret
            self.orders = []
            created_clients[(api_key, api_secret)] = self
        def balance(self):
            return 1000.0
        def order(self, symbol, side, qty):
            self.orders.append((symbol, side, qty))

    monkeypatch.setattr(hawkeye, "BinanceClient", DummyClient)

    hawkeye.check_price()

    assert created_clients[("k1", "s1")].orders == [("BTCUSDT", "SELL", 1.0)]
    assert created_clients[("k2", "s2")].orders == [("ETHUSDT", "SELL", 2.0)]
