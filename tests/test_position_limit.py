import sys
import types
import pytest

# Stub external modules required by hawkeye
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


class DummyBot:
    def __init__(self):
        self.messages = []
    def send_message(self, cid, text):
        self.messages.append((cid, text))
    def send_photo(self, cid, photo):
        pass
    def message_handler(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def infinity_polling(self, *args, **kwargs):
        pass


class DummyTrader:
    def __init__(self):
        self.orders = []
        self._balance = 1000.0
    def order(self, symbol, side, qty):
        self.orders.append((symbol, side, qty))
        price = 100.0
        if side == "BUY":
            self._balance -= price * qty
        else:
            self._balance += price * qty
    def balance(self):
        return self._balance


def test_autotrade_skips_when_position_open(monkeypatch):
    monkeypatch.setattr(hawkeye, "bot", DummyBot())
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    monkeypatch.setattr(hawkeye, "get_price", lambda sym: 100.0)
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv", lambda sym, limit=400: object())
    monkeypatch.setattr(hawkeye.strategy, "generate_signals", lambda asset, bench: DummySignals("buy"))
    trader = DummyTrader()
    monkeypatch.setattr(hawkeye, "get_binance_client", lambda cid: trader)
    hawkeye.users = {
        "1": {
            "notifications": True,
            "symbols": {"ETHUSDT": {"last_signal": "hold", "trade_percent": 10, "position": 1.0}},
        }
    }
    hawkeye.check_price()
    assert trader.orders == []
    assert hawkeye.users["1"]["symbols"]["ETHUSDT"]["position"] == 1.0


def test_autotradesim_skips_when_position_open(monkeypatch):
    bot = DummyBot()
    monkeypatch.setattr(hawkeye, "bot", bot)
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    monkeypatch.setattr(hawkeye, "get_price", lambda sym: 100.0)
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv", lambda sym, limit=400: object())
    monkeypatch.setattr(hawkeye.strategy, "generate_signals", lambda asset, bench: DummySignals("buy"))
    trader = DummyTrader()
    monkeypatch.setattr(hawkeye, "get_binance_client", lambda cid: trader)
    hawkeye.users = {
        "1": {
            "notifications": True,
            "symbols": {
                "ETHUSDT": {
                    "last_signal": "hold",
                    "trade_percent": 10,
                    "sim_start": 1000,
                    "sim_balance": 900,
                    "sim_position": 1.0,
                    "sim_actions": [],
                }
            },
        }
    }
    calls = []
    def fake_record(cfg, side, price, qty):
        calls.append((side, qty))
        return ""
    monkeypatch.setattr(hawkeye, "record_simulated_trade", fake_record)
    hawkeye.check_price()
    assert calls == []
    data = hawkeye.users["1"]["symbols"]["ETHUSDT"]
    assert data["sim_actions"] == []
    assert data["sim_position"] == 1.0


def test_autotrade_respects_max_percent(monkeypatch):
    monkeypatch.setattr(hawkeye, "bot", DummyBot())
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    monkeypatch.setattr(hawkeye, "get_price", lambda sym: 100.0)
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv", lambda sym, limit=400: object())
    monkeypatch.setattr(hawkeye.strategy, "generate_signals", lambda asset, bench: DummySignals("buy"))
    trader = DummyTrader()
    monkeypatch.setattr(hawkeye, "get_binance_client", lambda cid: trader)
    hawkeye.users = {
        "1": {
            "notifications": True,
            "symbols": {
                "ETHUSDT": {
                    "last_signal": "hold",
                    "trade_percent": 10,
                    "max_percent": 25,
                    "position": 0.0,
                }
            },
        }
    }
    for expected in [1.0, 0.9, 0.6]:
        hawkeye.check_price()
        hawkeye.users["1"]["symbols"]["ETHUSDT"]["last_signal"] = "sell"
    quantities = [o[2] for o in trader.orders]
    expected = [1.0, 0.9, 0.6]
    assert all(abs(a - b) < 1e-6 for a, b in zip(quantities, expected))
    hawkeye.check_price()
    assert len(trader.orders) == 3
    assert abs(hawkeye.users["1"]["symbols"]["ETHUSDT"]["position"] - 2.5) < 1e-6


def test_autotradesim_respects_max_percent(monkeypatch):
    bot = DummyBot()
    monkeypatch.setattr(hawkeye, "bot", bot)
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    monkeypatch.setattr(hawkeye, "get_price", lambda sym: 100.0)
    monkeypatch.setattr(hawkeye, "get_daily_ohlcv", lambda sym, limit=400: object())
    monkeypatch.setattr(hawkeye.strategy, "generate_signals", lambda asset, bench: DummySignals("buy"))
    trader = DummyTrader()
    monkeypatch.setattr(hawkeye, "get_binance_client", lambda cid: trader)
    hawkeye.users = {
        "1": {
            "notifications": True,
            "symbols": {
                "ETHUSDT": {
                    "last_signal": "hold",
                    "trade_percent": 10,
                    "max_percent": 25,
                    "sim_start": 1000,
                    "sim_balance": 1000,
                    "sim_position": 0.0,
                    "sim_actions": [],
                }
            },
        }
    }
    for expected in [1.0, 0.9, 0.6]:
        hawkeye.check_price()
        hawkeye.users["1"]["symbols"]["ETHUSDT"]["last_signal"] = "sell"
    data = hawkeye.users["1"]["symbols"]["ETHUSDT"]
    quantities = [a["qty"] for a in data["sim_actions"]]
    expected = [1.0, 0.9, 0.6]
    assert all(abs(a - b) < 1e-6 for a, b in zip(quantities, expected))
    hawkeye.check_price()
    assert abs(data["sim_position"] - 2.5) < 1e-6
    assert abs(data["sim_balance"] - 750) < 1e-6
