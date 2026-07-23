from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Base class for all trading strategies."""

    id: str
    name: str
    description: str
    # Example: {"fast": {"type": "int", "default": 10, "min": 2, "max": 50}}
    parameters: dict[str, dict]

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.Series:
        """
        Return a Series aligned with data.index:
          1  = long / buy
          0  = flat / sell (exit)
         -1  = short (optional; current backtester treats -1 like 0)
        """
        ...

    def resolve_params(self, overrides: dict | None = None) -> dict:
        """Merge user overrides with strategy defaults."""
        resolved = {key: meta["default"] for key, meta in self.parameters.items()}
        if overrides:
            resolved.update(overrides)
        return resolved
