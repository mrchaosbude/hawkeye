import types

import hawkeye


def _setup_dummy_bot(monkeypatch):
    messages = []

    class DummyBot:
        def reply_to(self, message, text):
            messages.append(text)

        def send_message(self, *args, **kwargs):
            messages.append(args[1] if len(args) > 1 else kwargs.get("text"))

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
    return messages


def test_autotradesim_command_sets_amount(monkeypatch):
    messages = _setup_dummy_bot(monkeypatch)
    msg = types.SimpleNamespace(
        text="/autotradesim 1000 ETHUSDT 200",
        chat=types.SimpleNamespace(id=1),
    )
    hawkeye.autotradesim_command(msg)
    sym_cfg = hawkeye.users["1"]["symbols"]["ETHUSDT"]
    assert sym_cfg["sim_start"] == 1000
    assert sym_cfg["sim_balance"] == 1000
    assert sym_cfg["trade_amount"] == 200
    assert sym_cfg["trade_percent"] is None
    assert any("ETHUSDT" in m for m in messages)


def test_autotradesim_command_sets_percent(monkeypatch):
    messages = _setup_dummy_bot(monkeypatch)
    msg = types.SimpleNamespace(
        text="/autotradesim 500 ETHUSDT 10%",
        chat=types.SimpleNamespace(id=1),
    )
    hawkeye.autotradesim_command(msg)
    sym_cfg = hawkeye.users["1"]["symbols"]["ETHUSDT"]
    assert sym_cfg["trade_percent"] == 10
    assert sym_cfg["trade_amount"] == 0.0
    assert sym_cfg["sim_start"] == 500
    assert sym_cfg["sim_balance"] == 500
    assert any("ETHUSDT" in m for m in messages)


def test_record_simulated_trade(monkeypatch):
    cfg = {"sim_start": 1000, "sim_balance": 1000, "sim_position": 0.0, "sim_actions": []}
    msg1 = hawkeye.record_simulated_trade(cfg, "BUY", 100, 2)
    assert cfg["sim_balance"] == 1000 - 100 * 2
    assert "Balance" in msg1
    msg2 = hawkeye.record_simulated_trade(cfg, "SELL", 110, 2)
    assert cfg["sim_balance"] == 1000 - 100 * 2 + 110 * 2
    assert "+" in msg2 or "-" in msg2
