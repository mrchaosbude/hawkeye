"""Compatibility wrapper around the momentum strategy.

The original standalone script has been refactored into the
``strategies`` package.  This module preserves a small CLI for
ad-hoc signal generation from the command line.
"""

from __future__ import annotations

import argparse
import pandas as pd

from strategies.momentum import MomentumStrategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate trading signals")
    parser.add_argument("data", help="CSV with asset OHLCV data")
    parser.add_argument("--benchmark", required=True, help="CSV with benchmark data")
    parser.add_argument(
        "--stress-threshold",
        type=float,
        default=0.08,
        help="ATR ratio threshold to flag market stress (default: 0.08)",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.data, parse_dates=["Date"], index_col="Date")
    bench = pd.read_csv(args.benchmark, parse_dates=["Date"], index_col="Date")

    signals = MomentumStrategy().generate_signals(
        df, bench, stress_threshold=args.stress_threshold
    )
    print(signals[["Score", "Signal"]].tail())


if __name__ == "__main__":
    main()
