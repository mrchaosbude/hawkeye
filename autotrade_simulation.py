"""Utility for simulating automated trading.

The simulation tracks cash balance and open position based on a sequence
of trade actions.  After each action a notification string containing the
current balance and profit/loss relative to the starting capital is
returned and optionally passed to a callback.
"""
from __future__ import annotations
from typing import Iterable, Callable, Dict, List


def simulate_autotrade(
    actions: Iterable[Dict[str, float]],
    start_balance: float,
    notify: Callable[[str], None] | None = None,
) -> List[str]:
    """Simulate a series of trades and report account status.

    Parameters
    ----------
    actions:
        Iterable of trade dictionaries each containing ``side`` (``"BUY"``
        or ``"SELL"``), ``price`` and ``qty``.
    start_balance:
        Initial amount of cash available for trading.
    notify:
        Optional callback receiving a formatted message after each action.

    Returns
    -------
    list[str]
        Formatted notifications for each processed action.
    """
    balance = float(start_balance)
    position = 0.0
    last_price = 0.0
    notifications: List[str] = []

    for trade in actions:
        side = trade["side"].upper()
        price = float(trade["price"])
        qty = float(trade["qty"])

        if side == "BUY":
            balance -= price * qty
            position += qty
        elif side == "SELL":
            balance += price * qty
            position -= qty
        else:
            raise ValueError(f"unknown trade side: {side}")

        last_price = price
        profit = balance + position * last_price - start_balance
        message = f"Balance: {balance:.2f} | P&L: {profit:+.2f}"
        notifications.append(message)
        if notify:
            notify(message)

    return notifications
