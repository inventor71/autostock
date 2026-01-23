from __future__ import annotations

from typing import Type

from loguru import logger

from src.strategy.base import BaseStrategy


_REGISTRY: dict[str, Type[BaseStrategy]] = {}


def register_strategy(name: str):
    """Decorator to register a strategy class."""
    def decorator(cls: Type[BaseStrategy]):
        cls.name = name
        _REGISTRY[name] = cls
        logger.debug(f"Registered strategy: {name}")
        return cls
    return decorator


def get_strategy_class(name: str) -> Type[BaseStrategy]:
    """Get a strategy class by name."""
    if name not in _REGISTRY:
        raise KeyError(f"Strategy '{name}' not found. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]


def create_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    """Create a strategy instance by name."""
    cls = get_strategy_class(name)
    return cls(params=params)


def list_strategies() -> list[str]:
    """List all registered strategy names."""
    return list(_REGISTRY.keys())
