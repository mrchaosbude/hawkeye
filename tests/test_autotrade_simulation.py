import autotrade_simulation


def test_simulation_generates_notifications():
    trades = [
        {"side": "BUY", "price": 100.0, "qty": 1},
        {"side": "SELL", "price": 120.0, "qty": 1},
    ]
    messages = []
    notifications = autotrade_simulation.simulate_autotrade(
        trades, start_balance=1000.0, notify=messages.append
    )
    assert notifications == messages
    assert messages[0] == "Balance: 900.00 | P&L: +0.00"
    assert messages[1] == "Balance: 1020.00 | P&L: +20.00"
