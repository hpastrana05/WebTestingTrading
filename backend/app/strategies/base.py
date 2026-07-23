from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Strategy(ABC):
    """Base class for all trading strategies."""

    id: str
    name: str
    description: str
    # Example: {"fast": {"type": "int", "default": 10, "min": 2, "max": 50}}
    parameters: dict[str, dict]
    # long | short | both — owned by the strategy (builtins default to long)
    direction: str = "long"

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.Series:
        """
        Return a Series aligned with data.index:
          1  = long
          0  = flat
         -1  = short
        """
        ...

    def generate_signal_frame(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        TradingView-style order plan:
          entry       — 1 / -1 / 0 on the bar the entry signal fires
          force_flat  — True when strategy wants a market flatten
          flat_reason — Session | Signal when force_flat
          stop / take — levels when entry fires
        """
        return position_series_to_frame(self.generate_signals(data, params))

    def resolve_params(self, overrides: dict | None = None) -> dict:
        """Merge user overrides with strategy defaults."""
        resolved = {key: meta["default"] for key, meta in self.parameters.items()}
        if overrides:
            resolved.update(overrides)
        return resolved


def position_series_to_frame(position: pd.Series) -> pd.DataFrame:
    """Convert a held-position series into entry / force_flat events (no stops)."""
    pos = position.fillna(0).astype(int)
    entry = pd.Series(0, index=pos.index, dtype=int)
    force_flat = pd.Series(False, index=pos.index, dtype=bool)
    flat_reason = pd.Series("", index=pos.index, dtype=object)
    prev = 0
    for i, value in enumerate(pos.to_numpy()):
        value = int(value)
        if prev == 0 and value != 0:
            entry.iloc[i] = value
        elif prev != 0 and value == 0:
            force_flat.iloc[i] = True
            flat_reason.iloc[i] = "Signal"
        elif prev != 0 and value != 0 and value != prev:
            force_flat.iloc[i] = True
            flat_reason.iloc[i] = "Signal"
            entry.iloc[i] = value
        prev = value
    return pd.DataFrame(
        {
            "entry": entry,
            "force_flat": force_flat,
            "flat_reason": flat_reason,
            "stop": pd.Series(np.nan, index=pos.index, dtype=float),
            "take": pd.Series(np.nan, index=pos.index, dtype=float),
        }
    )
