import types

import hawkeye


def test_autotradelimit_command_sets_percent(monkeypatch):
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

    msg = types.SimpleNamespace(text="/autotradelimit ETHUSDT 25%", chat=types.SimpleNamespace(id=1))

    hawkeye.autotradelimit_command(msg)

    sym_cfg = hawkeye.users["1"]["symbols"]["ETHUSDT"]
    assert sym_cfg["max_percent"] == 25
    assert any("ETHUSDT" in m for m in messages)
