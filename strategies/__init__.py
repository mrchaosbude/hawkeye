"""Strategy package with factory for available strategies."""

from .base import Strategy
from .momentum import MomentumStrategy
from .trend_following import TrendFollowingStrategy

STRATEGY_CLASSES = {
    "momentum": MomentumStrategy,
    "trend_following": TrendFollowingStrategy,
}


def get_strategy(name: str, **params) -> Strategy:
    """Return an instance of the strategy specified by ``name``."""
    try:
        cls = STRATEGY_CLASSES[name.lower()]
        return cls(**params)
    except KeyError as exc:
        raise ValueError(f"Unknown strategy: {name}") from exc

__all__ = [
    "Strategy",
    "MomentumStrategy",
    "TrendFollowingStrategy",
    "get_strategy",
    "STRATEGY_CLASSES",
]
