import sys
sys.modules.pop("numpy", None)
sys.modules.pop("pandas", None)
import pandas as pd
import importlib

import backtest
importlib.reload(backtest)


def test_run_backtest(monkeypatch):
    # Prepare dummy OHLC data
    from datetime import datetime, timedelta
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(5)]
    df = pd.DataFrame(
        {
            "Open": [1, 2, 3, 2, 4],
            "High": [1, 2, 3, 2, 4],
            "Low": [1, 2, 3, 2, 4],
            "Close": [1, 2, 3, 2, 4],
            "Volume": [1, 1, 1, 1, 1],
        },
        index=dates,
    )

    def fake_fetch(symbol, start, end, interval="1d"):
        return df

    monkeypatch.setattr(backtest, "fetch_candles", fake_fetch)

    class DummyStrategy:
        def generate_signals(self, data, benchmark):
            out = data.copy()
            out["Signal"] = ["buy", "hold", "sell", "buy", "sell"]
            return out

    monkeypatch.setattr(backtest, "get_strategy", lambda name, **kw: DummyStrategy())

    roi, drawdown = backtest.run_backtest("BTCUSDT", "2021-01-01", "2021-01-05")
    assert round(roi, 2) == 5.0
    assert drawdown == 0.0
