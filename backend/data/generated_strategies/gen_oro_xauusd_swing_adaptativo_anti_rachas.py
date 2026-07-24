# TRADING_LAB_GENERATED
"""
Auto-generated from Pine Script import (best-effort).

Strategy: ORO (XAUUSD) - Swing Adaptativo (Anti-Rachas)
Direction: both
Ticker hint: QQQ · 1d · 1y

Embeds the Strategy Creator rule tree and runs it through the same rule
engine as hand-made configs. NOT a full Pine interpreter — review first.
"""

from __future__ import annotations

import json

import pandas as pd

from app.schemas import StrategyConfig
from app.strategies.base import Strategy
from app.strategies.config_strategy import ConfigStrategy


_CONFIG = json.loads(r"""
{
    "id": "gen_oro_xauusd_swing_adaptativo_anti_rachas",
    "name": "ORO (XAUUSD) - Swing Adaptativo (Anti-Rachas)",
    "broker_ticker": "",
    "yahoo_ticker": "QQQ",
    "interval": "1d",
    "period": "1y",
    "direction": "both",
    "trade_session": "",
    "close_session": "",
    "timezone": "Europe/Madrid",
    "one_trade_per_day": false,
    "entry": {
        "type": "group",
        "left": null,
        "operator": null,
        "right": null,
        "right_scale": null,
        "logic": "all",
        "children": [
            {
                "type": "condition",
                "left": {
                    "kind": "indicator",
                    "field": null,
                    "indicator": "ema",
                    "params": {
                        "length": 50
                    },
                    "output": "EMA",
                    "value": null
                },
                "operator": ">",
                "right": {
                    "kind": "indicator",
                    "field": null,
                    "indicator": "ema",
                    "params": {
                        "length": 200
                    },
                    "output": "EMA",
                    "value": null
                },
                "right_scale": 1.0,
                "logic": null,
                "children": [],
                "risk": null,
                "pct": null,
                "atr_length": null,
                "atr_mult": null,
                "rr_ratio": null
            },
            {
                "type": "condition",
                "left": {
                    "kind": "price",
                    "field": "Close",
                    "indicator": null,
                    "params": {},
                    "output": null,
                    "value": null
                },
                "operator": ">",
                "right": {
                    "kind": "indicator",
                    "field": null,
                    "indicator": "ema",
                    "params": {
                        "length": 50
                    },
                    "output": "EMA",
                    "value": null
                },
                "right_scale": 1.0,
                "logic": null,
                "children": [],
                "risk": null,
                "pct": null,
                "atr_length": null,
                "atr_mult": null,
                "rr_ratio": null
            }
        ],
        "risk": null,
        "pct": null,
        "atr_length": null,
        "atr_mult": null,
        "rr_ratio": null
    },
    "entry_short": {
        "type": "group",
        "left": null,
        "operator": null,
        "right": null,
        "right_scale": null,
        "logic": "all",
        "children": [
            {
                "type": "condition",
                "left": {
                    "kind": "indicator",
                    "field": null,
                    "indicator": "ema",
                    "params": {
                        "length": 50
                    },
                    "output": "EMA",
                    "value": null
                },
                "operator": "<",
                "right": {
                    "kind": "indicator",
                    "field": null,
                    "indicator": "ema",
                    "params": {
                        "length": 200
                    },
                    "output": "EMA",
                    "value": null
                },
                "right_scale": 1.0,
                "logic": null,
                "children": [],
                "risk": null,
                "pct": null,
                "atr_length": null,
                "atr_mult": null,
                "rr_ratio": null
            },
            {
                "type": "condition",
                "left": {
                    "kind": "price",
                    "field": "Close",
                    "indicator": null,
                    "params": {},
                    "output": null,
                    "value": null
                },
                "operator": "<",
                "right": {
                    "kind": "indicator",
                    "field": null,
                    "indicator": "ema",
                    "params": {
                        "length": 50
                    },
                    "output": "EMA",
                    "value": null
                },
                "right_scale": 1.0,
                "logic": null,
                "children": [],
                "risk": null,
                "pct": null,
                "atr_length": null,
                "atr_mult": null,
                "rr_ratio": null
            }
        ],
        "risk": null,
        "pct": null,
        "atr_length": null,
        "atr_mult": null,
        "rr_ratio": null
    },
    "exit": {
        "type": "group",
        "left": null,
        "operator": null,
        "right": null,
        "right_scale": null,
        "logic": "any",
        "children": [
            {
                "type": "risk",
                "left": null,
                "operator": null,
                "right": null,
                "right_scale": null,
                "logic": null,
                "children": [],
                "risk": "structure_atr",
                "pct": null,
                "atr_length": 20,
                "atr_mult": 1.1,
                "rr_ratio": 3.0
            }
        ],
        "risk": null,
        "pct": null,
        "atr_length": null,
        "atr_mult": null,
        "rr_ratio": null
    }
}
""")


class OroXauusdSwingAdaptativoAntiRachasStrategy(Strategy):
    """Generated wrapper around an imported Pine → Creator config."""

    id = 'gen_oro_xauusd_swing_adaptativo_anti_rachas'
    name = 'ORO (XAUUSD) - Swing Adaptativo (Anti-Rachas)'
    description = (
        "Generated from Pine import · both · "
        "QQQ · 1d"
    )
    direction = 'both'
    parameters: dict = {}

    def __init__(self) -> None:
        self._inner = ConfigStrategy(StrategyConfig(**_CONFIG))
        self.parameters = self._inner.parameters
        self.direction = self._inner.direction
        self.name = self._inner.name
        self.description = self._inner.description

    def generate_signals(self, data: pd.DataFrame, params: dict | None = None) -> pd.Series:
        return self._inner.generate_signals(data, params)

    def generate_signal_frame(self, data: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        return self._inner.generate_signal_frame(data, params)


def build() -> Strategy:
    return OroXauusdSwingAdaptativoAntiRachasStrategy()
