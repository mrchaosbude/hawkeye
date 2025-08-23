import sys
import types

# Stub modules required by hawkeye
class _StubBot:
    def __init__(self, *args, **kwargs):
        pass
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

_apihelper = types.SimpleNamespace(ApiException=Exception)
sys.modules.setdefault("telebot", types.SimpleNamespace(TeleBot=_StubBot, apihelper=_apihelper))
sys.modules.setdefault("telebot.apihelper", _apihelper)

class _Job:
    def __init__(self):
        self.minutes = self
        self.day = self
    def do(self, *args, **kwargs):
        return self
    def at(self, *args, **kwargs):
        return self

def _every(*args, **kwargs):
    return _Job()

sys.modules.setdefault(
    "schedule", types.SimpleNamespace(clear=lambda: None, every=_every, run_pending=lambda: None)
)

plt = types.SimpleNamespace()
mdates = types.SimpleNamespace()
sys.modules.setdefault("matplotlib", types.SimpleNamespace(pyplot=plt, dates=mdates))
sys.modules.setdefault("matplotlib.pyplot", plt)
sys.modules.setdefault("matplotlib.dates", mdates)
_sys_mpf = types.SimpleNamespace(candlestick_ohlc=lambda *a, **k: None)
sys.modules.setdefault("mplfinance", types.SimpleNamespace(original_flavor=_sys_mpf))
sys.modules.setdefault("mplfinance.original_flavor", _sys_mpf)

class _DummyThread:
    def __init__(self, *args, **kwargs):
        pass
    def start(self):
        pass

sys.modules.setdefault("threading", types.SimpleNamespace(Thread=_DummyThread))

import hawkeye


def test_signal_change_triggers_notification(monkeypatch):
    # Arrange: setup user with existing last signal
    monkeypatch.setattr(hawkeye, "users", {
        "1": {
            "notifications": True,
            "symbols": {"ETHUSDT": {"last_signal": "buy", "trade_percent": 10, "position": 1}},
        }
    })

    messages = []

    class DummyBot:
        def send_message(self, cid, text):
            messages.append((cid, text))
        def send_photo(self, cid, photo):
            messages.append(("photo", cid))
        def message_handler(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def infinity_polling(self, *args, **kwargs):
            pass

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

    monkeypatch.setattr(hawkeye, "bot", DummyBot())
    monkeypatch.setattr(hawkeye, "get_price", lambda sym: 100.0)
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv", lambda sym, limit=400: object())
    monkeypatch.setattr(
        hawkeye.strategy,
        "generate_signals",
        lambda asset, bench: DummySignals("sell"),
    )
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    orders = []

    class DummyTrader:
        def order(self, symbol, side, qty):
            orders.append((symbol, side, qty))

        def balance(self):
            return 1000.0

    trader = DummyTrader()
    monkeypatch.setattr(hawkeye, "get_binance_client", lambda cid: trader)

    # Act
    hawkeye.check_price()

    # Assert: last signal updated and notification sent
    assert hawkeye.users["1"]["symbols"]["ETHUSDT"]["last_signal"] == "sell"
    assert len(messages) == 1
    assert "ETHUSDT" in messages[0][1]
    assert orders == [("ETHUSDT", "SELL", 1)]
