"""Curated pandas-ta indicators exposed to the Strategy Creator."""

from __future__ import annotations

# Each entry maps to a pandas_ta function name (ta.<id>).
# outputs: logical names the UI can pick; the engine resolves the real column.
INDICATOR_CATALOG: list[dict] = [
    {
        "id": "sma",
        "label": "SMA — Simple Moving Average",
        "category": "overlap",
        "inputs": ["close"],
        "params": [
            {"name": "length", "type": "int", "default": 20, "min": 2, "max": 300, "step": 1},
        ],
        "outputs": [{"id": "SMA", "label": "SMA"}],
    },
    {
        "id": "ema",
        "label": "EMA — Exponential Moving Average",
        "category": "overlap",
        "inputs": ["close"],
        "params": [
            {"name": "length", "type": "int", "default": 20, "min": 2, "max": 300, "step": 1},
        ],
        "outputs": [{"id": "EMA", "label": "EMA"}],
    },
    {
        "id": "wma",
        "label": "WMA — Weighted Moving Average",
        "category": "overlap",
        "inputs": ["close"],
        "params": [
            {"name": "length", "type": "int", "default": 20, "min": 2, "max": 300, "step": 1},
        ],
        "outputs": [{"id": "WMA", "label": "WMA"}],
    },
    {
        "id": "rsi",
        "label": "RSI — Relative Strength Index",
        "category": "momentum",
        "inputs": ["close"],
        "params": [
            {"name": "length", "type": "int", "default": 14, "min": 2, "max": 100, "step": 1},
        ],
        "outputs": [{"id": "RSI", "label": "RSI"}],
    },
    {
        "id": "macd",
        "label": "MACD",
        "category": "momentum",
        "inputs": ["close"],
        "params": [
            {"name": "fast", "type": "int", "default": 12, "min": 2, "max": 100, "step": 1},
            {"name": "slow", "type": "int", "default": 26, "min": 5, "max": 200, "step": 1},
            {"name": "signal", "type": "int", "default": 9, "min": 2, "max": 50, "step": 1},
        ],
        "outputs": [
            {"id": "MACD", "label": "MACD line"},
            {"id": "MACDh", "label": "MACD histogram"},
            {"id": "MACDs", "label": "MACD signal"},
        ],
    },
    {
        "id": "stoch",
        "label": "Stochastic Oscillator",
        "category": "momentum",
        "inputs": ["high", "low", "close"],
        "params": [
            {"name": "k", "type": "int", "default": 14, "min": 2, "max": 100, "step": 1},
            {"name": "d", "type": "int", "default": 3, "min": 1, "max": 50, "step": 1},
            {"name": "smooth_k", "type": "int", "default": 3, "min": 1, "max": 50, "step": 1},
        ],
        "outputs": [
            {"id": "STOCHk", "label": "%K"},
            {"id": "STOCHd", "label": "%D"},
        ],
    },
    {
        "id": "cci",
        "label": "CCI — Commodity Channel Index",
        "category": "momentum",
        "inputs": ["high", "low", "close"],
        "params": [
            {"name": "length", "type": "int", "default": 20, "min": 2, "max": 100, "step": 1},
        ],
        "outputs": [{"id": "CCI", "label": "CCI"}],
    },
    {
        "id": "willr",
        "label": "Williams %R",
        "category": "momentum",
        "inputs": ["high", "low", "close"],
        "params": [
            {"name": "length", "type": "int", "default": 14, "min": 2, "max": 100, "step": 1},
        ],
        "outputs": [{"id": "WILLR", "label": "Williams %R"}],
    },
    {
        "id": "roc",
        "label": "ROC — Rate of Change",
        "category": "momentum",
        "inputs": ["close"],
        "params": [
            {"name": "length", "type": "int", "default": 10, "min": 1, "max": 100, "step": 1},
        ],
        "outputs": [{"id": "ROC", "label": "ROC"}],
    },
    {
        "id": "mom",
        "label": "Momentum",
        "category": "momentum",
        "inputs": ["close"],
        "params": [
            {"name": "length", "type": "int", "default": 10, "min": 1, "max": 100, "step": 1},
        ],
        "outputs": [{"id": "MOM", "label": "Momentum"}],
    },
    {
        "id": "bbands",
        "label": "Bollinger Bands",
        "category": "volatility",
        "inputs": ["close"],
        "params": [
            {"name": "length", "type": "int", "default": 20, "min": 2, "max": 100, "step": 1},
            {"name": "std", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1},
        ],
        "outputs": [
            {"id": "BBL", "label": "Lower band"},
            {"id": "BBM", "label": "Middle band"},
            {"id": "BBU", "label": "Upper band"},
        ],
    },
    {
        "id": "atr",
        "label": "ATR — Average True Range",
        "category": "volatility",
        "inputs": ["high", "low", "close"],
        "params": [
            {"name": "length", "type": "int", "default": 14, "min": 2, "max": 100, "step": 1},
        ],
        "outputs": [{"id": "ATR", "label": "ATR"}],
    },
    {
        "id": "vwap",
        "label": "VWAP — Session Volume Weighted Avg (daily reset)",
        "category": "overlap",
        "inputs": ["high", "low", "close", "volume"],
        "params": [],
        "outputs": [{"id": "VWAP", "label": "VWAP"}],
    },
    {
        "id": "range_sma",
        "label": "Bar Range SMA — SMA of (High−Low)",
        "category": "volatility",
        "inputs": ["high", "low"],
        "params": [
            {"name": "length", "type": "int", "default": 15, "min": 2, "max": 100, "step": 1},
        ],
        "outputs": [{"id": "RANGE_SMA", "label": "Range SMA"}],
    },
    {
        "id": "adx",
        "label": "ADX — Average Directional Index",
        "category": "trend",
        "inputs": ["high", "low", "close"],
        "params": [
            {"name": "length", "type": "int", "default": 14, "min": 2, "max": 100, "step": 1},
        ],
        "outputs": [
            {"id": "ADX", "label": "ADX"},
            {"id": "DMP", "label": "+DI"},
            {"id": "DMN", "label": "-DI"},
        ],
    },
    {
        "id": "supertrend",
        "label": "Supertrend",
        "category": "trend",
        "inputs": ["high", "low", "close"],
        "params": [
            {"name": "length", "type": "int", "default": 7, "min": 2, "max": 50, "step": 1},
            {"name": "multiplier", "type": "float", "default": 3.0, "min": 1.0, "max": 10.0, "step": 0.1},
        ],
        "outputs": [
            {"id": "SUPERT", "label": "Supertrend"},
            {"id": "SUPERTd", "label": "Direction (+1/-1)"},
        ],
    },
]

PRICE_FIELDS = [
    {"id": "Open", "label": "Open"},
    {"id": "High", "label": "High"},
    {"id": "Low", "label": "Low"},
    {"id": "Close", "label": "Close"},
    {"id": "Volume", "label": "Volume"},
    {"id": "HLC3", "label": "HLC3 ((H+L+C)/3)"},
    {"id": "BarRange", "label": "Bar Range (High−Low)"},
]

OPERATORS = [
    {"id": ">", "label": "greater than"},
    {"id": "<", "label": "less than"},
    {"id": ">=", "label": "greater or equal"},
    {"id": "<=", "label": "less or equal"},
    {"id": "==", "label": "equal"},
    {"id": "cross_above", "label": "crosses above"},
    {"id": "cross_below", "label": "crosses below"},
]


def get_indicator(indicator_id: str) -> dict:
    for item in INDICATOR_CATALOG:
        if item["id"] == indicator_id:
            return item
    raise KeyError(f"Unknown indicator: {indicator_id}")
