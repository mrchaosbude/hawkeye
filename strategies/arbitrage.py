"""Cross-exchange arbitrage strategy implementation."""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd
import requests

from .base import Strategy


@dataclass
class ArbitrageParams:
    """Configuration for the arbitrage strategy."""

    symbol: str = "BTCUSDT"
    threshold: float = 0.01  # 1%


class ArbitrageStrategy(Strategy):
    """Fetch prices from multiple exchanges and emit arbitrage signals."""

    def __init__(self, symbol: str = "BTCUSDT", threshold: float = 0.01) -> None:
        self.params = ArbitrageParams(symbol, threshold)

    def _binance_price(self) -> float:
        url = "https://api.binance.com/api/v3/ticker/price"
        resp = requests.get(url, params={"symbol": self.params.symbol}, timeout=10)
        resp.raise_for_status()
        return float(resp.json()["price"])

    def _coinbase_price(self) -> float:
        pair = self.params.symbol
        pair = pair.replace("USDT", "USD")
        if "-" not in pair:
            pair = pair[:-3] + "-" + pair[-3:]
        url = f"https://api.coinbase.com/v2/prices/{pair}/spot"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return float(resp.json()["data"]["amount"])

    def generate_signals(
        self, df: pd.DataFrame | None = None, benchmark: pd.DataFrame | None = None
    ) -> pd.DataFrame:
        """Return current prices and arbitrage signal."""

        binance = self._binance_price()
        coinbase = self._coinbase_price()

        spread = abs(binance - coinbase) / min(binance, coinbase)
        signal = "hold"
        if spread > self.params.threshold:
            if binance < coinbase:
                signal = "buy_binance_sell_coinbase"
            else:
                signal = "buy_coinbase_sell_binance"

        data = pd.DataFrame(
            [
                {
                    "Binance": binance,
                    "Coinbase": coinbase,
                    "Spread": spread,
                    "Signal": signal,
                }
            ]
        )
        return data
