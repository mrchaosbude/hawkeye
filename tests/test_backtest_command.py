import types

import hawkeye


def test_backtest_command_normalizes_symbol(monkeypatch):
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
    monkeypatch.setattr(hawkeye, "translate", lambda cid, key, **kwargs: key)

    called = {}

    def fake_run_backtest(symbol, start, end):
        called["symbol"] = symbol
        return 0.1, 0.2

    monkeypatch.setattr(hawkeye, "run_backtest", fake_run_backtest)

    msg = types.SimpleNamespace(
        text="/backtest doge 2021-01-01 2021-02-01",
        chat=types.SimpleNamespace(id=1),
    )

    hawkeye.backtest_command(msg)

    assert called["symbol"] == "DOGEUSDT"
    assert "backtest_result" in messages
