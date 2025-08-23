"""Backtesting utilities for Hawkeye strategies."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Tuple

import pandas as pd
import requests

from strategies import get_strategy

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def fetch_candles(symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """Fetch historical candlestick data from Binance."""
    start_ms = int(datetime.fromisoformat(start).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(end).timestamp() * 1000)
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
    }
    try:
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch candles for %s: %s", symbol, exc)
        raise
    data = resp.json()
    if not data:
        logger.error("No candlestick data returned for %s", symbol)
        return pd.DataFrame()
    rows = [
        {
            "Date": datetime.fromtimestamp(int(item[0]) / 1000),
            "Open": float(item[1]),
            "High": float(item[2]),
            "Low": float(item[3]),
            "Close": float(item[4]),
            "Volume": float(item[5]),
        }
        for item in data
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.set_index("Date", inplace=True)
    return df


def run_backtest(
    symbol: str,
    start: str,
    end: str,
    strategy_name: str = "momentum",
    interval: str = "1d",
    **strategy_params,
) -> Tuple[float, float]:
    """Run backtest for ``symbol`` and return ROI and drawdown."""
    df = fetch_candles(symbol, start, end, interval)
    if df.empty:
        raise ValueError("No data returned from Binance")
    benchmark = df  # simplistic benchmark
    strategy = get_strategy(strategy_name, **strategy_params)
    signals = strategy.generate_signals(df, benchmark)
    signals["Return"] = signals["Close"].pct_change().fillna(0)
    mapping = {"buy": 1, "sell": 0}
    signals["Position"] = signals["Signal"].map(mapping).ffill().fillna(0)
    signals["Strategy_Return"] = signals["Return"] * signals["Position"].shift().fillna(0)
    signals["Equity"] = (1 + signals["Strategy_Return"]).cumprod()
    roi = float(signals["Equity"].iloc[-1] - 1)
    cummax = signals["Equity"].cummax()
    drawdown = float(((cummax - signals["Equity"]) / cummax).max())
    logger.info("%s backtest ROI %.2f%%, drawdown %.2f%%", symbol, roi * 100, drawdown * 100)
    print(f"ROI: {roi:.2%}, Max Drawdown: {drawdown:.2%}")
    return roi, drawdown

__all__ = ["run_backtest", "fetch_candles"]
