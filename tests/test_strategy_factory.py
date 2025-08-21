"""Tests for the strategy factory."""

from strategies import get_strategy, MomentumStrategy, TrendFollowingStrategy


def test_get_strategy_ignores_extra_params_momentum():
    """Extraneous parameters should be ignored without raising."""

    strategy = get_strategy("momentum", weights=None, foo="bar")

    assert isinstance(strategy, MomentumStrategy)
    assert not hasattr(strategy, "foo")


def test_get_strategy_ignores_extra_params_trend_following():
    """Ensure extra params do not raise for trend following strategy."""

    strategy = get_strategy("trend_following", long_window=60, extra=123)

    assert isinstance(strategy, TrendFollowingStrategy)
    assert strategy.params.long_window == 60
    assert not hasattr(strategy, "extra")

