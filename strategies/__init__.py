"""Strategy package with factory for available strategies."""

from __future__ import annotations

import inspect
import logging

from .base import Strategy
from .momentum import MomentumStrategy
from .trend_following import TrendFollowingStrategy
from .arbitrage import ArbitrageStrategy

STRATEGY_CLASSES = {
    "momentum": MomentumStrategy,
    "trend_following": TrendFollowingStrategy,
    "arbitrage": ArbitrageStrategy,
}
logger = logging.getLogger(__name__)


def get_strategy(name: str, **params) -> Strategy:
    """Return an instance of the strategy specified by ``name``."""
    try:
        cls = STRATEGY_CLASSES[name.lower()]
        signature = inspect.signature(cls.__init__)
        valid_params = {
            p.name
            for p in signature.parameters.values()
            if p.name != "self"
        }
        filtered_params = {k: v for k, v in params.items() if k in valid_params}
        ignored = set(params) - set(filtered_params)
        if ignored:
            logger.warning(
                "Ignoring unsupported parameters for %s: %s",
                name,
                ", ".join(sorted(ignored)),
            )
        return cls(**filtered_params)
    except KeyError as exc:
        raise ValueError(f"Unknown strategy: {name}") from exc

__all__ = [
    "Strategy",
    "MomentumStrategy",
    "TrendFollowingStrategy",
    "ArbitrageStrategy",
    "get_strategy",
    "STRATEGY_CLASSES",
]
