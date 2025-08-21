"""Momentum-based trading strategy implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .base import Strategy


@dataclass
class Scores:
    """Container for scoring weights."""

    trend: float = 0.5
    volume: float = 0.2
    rel_strength: float = 0.2
    fundamentals: float = 0.1


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    diff = series.diff()
    up = diff.clip(lower=0)
    down = -diff.clip(upper=0)
    avg_gain = up.rolling(period).mean()
    avg_loss = down.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series) -> pd.Series:
    ema12 = ema(series, 12)
    ema26 = ema(series, 26)
    return ema12 - ema26


def on_balance_volume(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["Close"].diff()).fillna(0)
    return (direction * df["Volume"]).cumsum()


def volume_percentile(series: pd.Series, window: int = 126) -> pd.Series:
    """Ratio of volume to its rolling 60th percentile."""
    q60 = series.rolling(window).quantile(0.6)
    return series / q60


def relative_strength(asset: pd.Series, benchmark: pd.Series) -> pd.Series:
    aligned = pd.concat([asset, benchmark], axis=1).ffill()
    asset_aligned = aligned.iloc[:, 0]
    bench_aligned = aligned.iloc[:, 1]
    return (
        (asset_aligned / asset_aligned.shift(252))
        / (bench_aligned / bench_aligned.shift(252))
        - 1
    )


def compute_features(
    df: pd.DataFrame, benchmark: pd.DataFrame, stress_threshold: float = 0.08
) -> pd.DataFrame:
    """Compute technical features used by the strategy.

    Parameters
    ----------
    df : pd.DataFrame
        Asset OHLCV data.
    benchmark : pd.DataFrame
        Benchmark OHLCV data used to determine market regime.
    stress_threshold : float, optional
        Maximum acceptable ``ATR_ratio`` (as a decimal) before the market is
        considered stressed.  Default is ``0.08`` (8%).

    Returns
    -------
    pd.DataFrame
        Feature-enriched DataFrame including the regime flag.
    """

    df = df.copy()
    bench = benchmark["Close"].reindex(df.index).ffill()

    df["EMA50"] = ema(df["Close"], 50)
    df["EMA200"] = ema(df["Close"], 200)
    df["EMA50_slope"] = df["EMA50"].diff()

    weekly = df["Close"].resample("W").last()
    weekly_macd = macd(weekly)
    df["Weekly_MACD"] = weekly_macd.reindex(df.index, method="ffill")

    df["ROC63"] = df["Close"].pct_change(63)
    df["ROC126"] = df["Close"].pct_change(126)
    df["Weekly_RSI"] = rsi(weekly).reindex(df.index, method="ffill")

    df["ATR14"] = atr(df)
    df["ATR_ratio"] = df["ATR14"] / df["Close"]

    df["OBV"] = on_balance_volume(df)
    df["OBV_slope"] = df["OBV"].diff()
    df["Volume_pct"] = volume_percentile(df["Volume"])

    df["Rel_Strength"] = relative_strength(df["Close"], bench)

    bench_ema200 = ema(bench, 200)
    df["Regime"] = (bench > bench_ema200) & (df["ATR_ratio"] < stress_threshold)

    return df


def compute_score(row: pd.Series, weights: Scores) -> float:
    trend_checks = [
        row["Close"] > row["EMA200"],
        row["EMA50_slope"] > 0,
        row["Weekly_MACD"] > 0,
    ]
    trend_score = weights.trend * (sum(trend_checks) / len(trend_checks))

    vol_score = (
        weights.volume
        if 1 <= row["Volume_pct"] <= 1.5 and row["OBV_slope"] > 0
        else 0
    )

    rs_score = weights.rel_strength if row["Rel_Strength"] > 0 else 0

    # Fundamentals placeholder: assume neutral 0.5 if not provided.
    # This mirrors the Hawkeye blueprint's default assumption.
    fund_score = weights.fundamentals * row.get("Fundamental", 0.5)

    return (trend_score + vol_score + rs_score + fund_score) * 100


class MomentumStrategy(Strategy):
    """Replicates the previous momentum/trend strategy."""

    def __init__(self, weights: Optional[Scores] = None) -> None:
        self.weights = weights or Scores()

    def generate_signals(
        self,
        df: pd.DataFrame,
        benchmark: pd.DataFrame,
        stress_threshold: float = 0.08,
    ) -> pd.DataFrame:
        """Generate momentum-based trading signals.

        Parameters
        ----------
        df : pd.DataFrame
            Asset OHLCV data.
        benchmark : pd.DataFrame
            Benchmark data.
        stress_threshold : float, optional
            Maximum ``ATR_ratio`` before the regime is considered stressed.
            Defaults to ``0.08`` (8%).
        """

        features = compute_features(df, benchmark, stress_threshold)
        features["Score"] = features.apply(
            compute_score, axis=1, weights=self.weights
        )

        conditions = [
            (features["Regime"]) & (features["Score"] >= 60),
            (features["Score"] < 45) | (features["Close"] < features["EMA50"]),
        ]
        choices = ["buy", "sell"]
        features["Signal"] = np.select(conditions, choices, default="hold")

        return features
