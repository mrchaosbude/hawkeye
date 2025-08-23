import types

import hawkeye


def test_portfolio_command(monkeypatch):
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

    class DummyClient:
        def balance(self):
            return 500

    monkeypatch.setattr(hawkeye, "get_binance_client", lambda chat_id: DummyClient())

    hawkeye.users = {
        "1": {
            "symbols": {
                "ETHUSDT": {
                    "sim_balance": 1000,
                    "sim_actions": [{"side": "BUY", "price": 100, "qty": 1}],
                }
            }
        }
    }

    msg = types.SimpleNamespace(text="/portfolio", chat=types.SimpleNamespace(id=1))
    hawkeye.cmd_portfolio(msg)

    assert any("1500.00" in m for m in messages)
