"""Wrap a saved StrategyConfig so it works like a built-in Strategy."""

from __future__ import annotations

import pandas as pd

from app.schemas import StrategyConfig
from app.services.rule_engine import generate_position_signals
from app.strategies.base import Strategy


class ConfigStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.id = config.id or "custom"
        self.name = config.name
        self.description = (
            f"Custom strategy for {config.yahoo_ticker} "
            f"({config.interval}, {config.period})"
        )
        self.parameters = {}

    def generate_signals(self, data: pd.DataFrame, params: dict | None = None) -> pd.Series:
        entry = self.config.entry.model_dump()
        exit_ = self.config.exit.model_dump()
        return generate_position_signals(data, entry, exit_)
