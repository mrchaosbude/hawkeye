import types

import hawkeye


def test_autotrade_command_sets_amount(monkeypatch):
    messages = []

    class DummyBot:
        def reply_to(self, message, text):
            messages.append(text)

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
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    hawkeye.users = {}

    msg = types.SimpleNamespace(text="/autotrade ETHUSDT 200", chat=types.SimpleNamespace(id=1))

    hawkeye.autotrade_command(msg)

    sym_cfg = hawkeye.users["1"]["symbols"]["ETHUSDT"]
    assert sym_cfg["trade_amount"] == 200
    assert sym_cfg["trade_percent"] is None
    assert any("ETHUSDT" in m for m in messages)


def test_autotrade_command_sets_percent(monkeypatch):
    messages = []

    class DummyBot:
        def reply_to(self, message, text):
            messages.append(text)

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
    monkeypatch.setattr(hawkeye, "save_config", lambda: None)
    hawkeye.users = {}

    msg = types.SimpleNamespace(text="/autotrade ETHUSDT 10%", chat=types.SimpleNamespace(id=1))

    hawkeye.autotrade_command(msg)

    sym_cfg = hawkeye.users["1"]["symbols"]["ETHUSDT"]
    assert sym_cfg["trade_percent"] == 10
    assert sym_cfg["trade_amount"] == 0.0
    assert any("ETHUSDT" in m for m in messages)

