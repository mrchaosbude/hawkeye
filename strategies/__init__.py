"""Strategy package with factory for available strategies."""

from .base import Strategy
from .momentum import MomentumStrategy

STRATEGY_CLASSES = {
    "momentum": MomentumStrategy,
}


def get_strategy(name: str) -> Strategy:
    """Return an instance of the strategy specified by ``name``."""
    try:
        return STRATEGY_CLASSES[name.lower()]()
    except KeyError as exc:
        raise ValueError(f"Unknown strategy: {name}") from exc

__all__ = ["Strategy", "MomentumStrategy", "get_strategy", "STRATEGY_CLASSES"]
