"""Trend following strategy implementation."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from .base import Strategy


@dataclass
class TrendParams:
    """Parameters for the trend following strategy."""

    short_window: int = 20
    long_window: int = 50
    donchian_window: int = 20


class TrendFollowingStrategy(Strategy):
    """Generate signals based on EMA crossovers and Donchian channel breakouts."""

    def __init__(
        self,
        short_window: int = 20,
        long_window: int = 50,
        donchian_window: int = 20,
    ) -> None:
        self.params = TrendParams(short_window, long_window, donchian_window)

    def generate_signals(self, df: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:  # noqa: D401
        data = df.copy()

        # Exponential moving averages
        data["EMA_short"] = (
            data["Close"].ewm(span=self.params.short_window, adjust=False).mean()
        )
        data["EMA_long"] = (
            data["Close"].ewm(span=self.params.long_window, adjust=False).mean()
        )
        data["EMA_diff"] = data["EMA_short"] - data["EMA_long"]

        # Donchian channel
        data["Donchian_high"] = data["High"].rolling(self.params.donchian_window).max()
        data["Donchian_low"] = data["Low"].rolling(self.params.donchian_window).min()

        # Signals
        crossover_buy = (data["EMA_diff"] > 0) & (data["EMA_diff"].shift(1) <= 0)
        crossover_sell = (data["EMA_diff"] < 0) & (data["EMA_diff"].shift(1) >= 0)
        breakout_buy = data["Close"] > data["Donchian_high"].shift(1)
        breakout_sell = data["Close"] < data["Donchian_low"].shift(1)

        conditions = [
            crossover_buy | breakout_buy,
            crossover_sell | breakout_sell,
        ]
        choices = ["buy", "sell"]
        data["Signal"] = np.select(conditions, choices, default="hold")

        return data
