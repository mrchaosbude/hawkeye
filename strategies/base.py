from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Abstract base class for trading strategies."""

    @abstractmethod
    def generate_signals(
        self, df: pd.DataFrame, benchmark: pd.DataFrame
    ) -> pd.DataFrame:
        """Return trading signals for ``df`` relative to ``benchmark``."""
        raise NotImplementedError
