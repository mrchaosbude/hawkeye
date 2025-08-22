"""Test configuration providing minimal stubs for optional dependencies."""

import os
import sys
import types


def _ensure_stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules.setdefault(name, module)
    return module


# Provide very small stubs so that strategy modules can be imported without
# Provide very small stubs so that strategy modules can be imported without
# heavy third-party dependencies. These stubs are sufficient because the tests
# only exercise object construction and never call functions that rely on these
# libraries.

# Ensure the repository root is on the import path for tests executed from the
# ``tests`` directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pandas = _ensure_stub("pandas")
setattr(pandas, "DataFrame", type("DataFrame", (), {}))
setattr(pandas, "Series", type("Series", (), {}))

_ensure_stub("numpy")
_ensure_stub("requests")

telebot = _ensure_stub("telebot")


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
telebot.TeleBot = _StubBot
telebot.apihelper = _apihelper
sys.modules.setdefault("telebot.apihelper", _apihelper)

schedule_mod = _ensure_stub("schedule")


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


schedule_mod.clear = lambda: None
schedule_mod.every = _every
schedule_mod.run_pending = lambda: None

matplotlib = _ensure_stub("matplotlib")
plt = types.SimpleNamespace()
mdates = types.SimpleNamespace()
matplotlib.pyplot = plt
matplotlib.dates = mdates
sys.modules.setdefault("matplotlib.pyplot", plt)
sys.modules.setdefault("matplotlib.dates", mdates)

mplfinance = _ensure_stub("mplfinance")
mplfinance.original_flavor = types.SimpleNamespace(
    candlestick_ohlc=lambda *a, **k: None
)
sys.modules.setdefault("mplfinance.original_flavor", mplfinance.original_flavor)

threading = _ensure_stub("threading")


class _DummyThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


threading.Thread = _DummyThread

