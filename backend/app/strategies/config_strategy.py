"""Wrap a saved StrategyConfig so it works like a built-in Strategy."""

from __future__ import annotations

import pandas as pd

from app.schemas import StrategyConfig
from app.services.config_params import apply_tunable_parameters, extract_tunable_parameters
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
        self.parameters = extract_tunable_parameters(
            entry=config.entry.model_dump(),
            exit_group=config.exit.model_dump(),
            entry_short=config.entry_short.model_dump(),
            direction=config.direction,
        )

    def _kwargs(self, params: dict | None = None) -> dict:
        entry = self.config.entry.model_dump()
        exit_group = self.config.exit.model_dump()
        entry_short = self.config.entry_short.model_dump()
        resolved = self.resolve_params(params)
        if resolved:
            entry, exit_group, entry_short = apply_tunable_parameters(
                entry, exit_group, resolved, entry_short=entry_short
            )
        return dict(
            entry_group=entry,
            exit_group=exit_group,
            direction=self.config.direction,
            entry_short_group=entry_short,
            trade_session=self.config.trade_session,
            close_session=self.config.close_session,
            timezone=self.config.timezone,
            one_trade_per_day=self.config.one_trade_per_day,
        )

    def generate_signals(self, data: pd.DataFrame, params: dict | None = None) -> pd.Series:
        return generate_position_signals(data, **self._kwargs(params))

    def generate_signal_frame(self, data: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        return generate_signal_frame(data, **self._kwargs(params))
