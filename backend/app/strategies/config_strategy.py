"""Wrap a saved StrategyConfig so it works like a built-in Strategy."""

from __future__ import annotations

import pandas as pd

from app.schemas import StrategyConfig
from app.services.rule_engine import generate_position_signals, generate_signal_frame
from app.strategies.base import Strategy


class ConfigStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.id = config.id or "custom"
        self.name = config.name
        self.direction = config.direction
        self.description = (
            f"Custom {config.direction} strategy for {config.yahoo_ticker} "
            f"({config.interval}, {config.period})"
        )
        self.parameters = {}

    def _kwargs(self) -> dict:
        return dict(
            entry_group=self.config.entry.model_dump(),
            exit_group=self.config.exit.model_dump(),
            direction=self.config.direction,
            entry_short_group=self.config.entry_short.model_dump(),
            trade_session=self.config.trade_session,
            close_session=self.config.close_session,
            timezone=self.config.timezone,
            one_trade_per_day=self.config.one_trade_per_day,
        )

    def generate_signals(self, data: pd.DataFrame, params: dict | None = None) -> pd.Series:
        return generate_position_signals(data, **self._kwargs())

    def generate_signal_frame(self, data: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        return generate_signal_frame(data, **self._kwargs())
