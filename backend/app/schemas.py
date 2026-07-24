from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# --- Built-in strategy info (legacy list) ---

class StrategyInfo(BaseModel):
    id: str
    name: str
    description: str
    parameters: dict[str, dict]
    source: str = "builtin"  # builtin | custom | generated
    direction: str = "long"  # long | short | both


# --- Rule tree for Strategy Creator ---

class Operand(BaseModel):
    kind: Literal["price", "indicator", "value"]
    # price
    field: str | None = None
    # indicator
    indicator: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    output: str | None = None
    # value
    value: float | None = None


class RuleNode(BaseModel):
    """Condition, nested group, or risk exit (stop_loss / take_profit / structure_atr)."""
    type: Literal["condition", "group", "risk"] = "condition"
    # condition fields
    left: Operand | None = None
    operator: str | None = None
    right: Operand | None = None
    # Multiply the right operand before comparing (e.g. impulse: range > SMA * 1.1)
    right_scale: float | None = None
    # group fields
    logic: Literal["all", "any"] | None = None
    children: list[RuleNode] = Field(default_factory=list)
    # risk exit fields (used when type=risk)
    risk: Literal["stop_loss", "take_profit", "structure_atr"] | None = None
    pct: float | None = None
    # structure_atr params (Pine-style SL from bar/ATR, TP = SL * rr)
    atr_length: int | None = None
    atr_mult: float | None = None
    rr_ratio: float | None = None


def _empty_group(logic: Literal["all", "any"] = "all") -> RuleNode:
    return RuleNode(type="group", logic=logic, children=[])


class StrategyConfig(BaseModel):
    id: str | None = None
    name: str
    broker_ticker: str = ""
    yahoo_ticker: str = "AAPL"
    interval: str = "1d"
    period: str = "1y"
    direction: Literal["long", "short", "both"] = "long"
    # Session filters (empty = no filter). Format: 1545-1930 or 15:45-19:30
    trade_session: str = ""
    close_session: str = ""
    timezone: str = "Europe/Madrid"
    one_trade_per_day: bool = False
    # Long entry (also used as the only entry when direction is long or short)
    entry: RuleNode = Field(default_factory=lambda: _empty_group("all"))
    # Short entry — required when direction is both
    entry_short: RuleNode = Field(default_factory=lambda: _empty_group("all"))
    exit: RuleNode = Field(default_factory=lambda: _empty_group("any"))

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_action(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "direction" not in data and "action" in data:
            legacy = data.pop("action")
            data["direction"] = {"buy": "long", "sell": "short"}.get(legacy, legacy)
        else:
            data.pop("action", None)
        return data


class StrategyConfigUpdate(BaseModel):
    name: str | None = None
    broker_ticker: str | None = None
    yahoo_ticker: str | None = None
    interval: str | None = None
    period: str | None = None
    direction: Literal["long", "short", "both"] | None = None
    trade_session: str | None = None
    close_session: str | None = None
    timezone: str | None = None
    one_trade_per_day: bool | None = None
    entry: RuleNode | None = None
    entry_short: RuleNode | None = None
    exit: RuleNode | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_action(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "direction" not in data and "action" in data:
            legacy = data.pop("action")
            data["direction"] = {"buy": "long", "sell": "short"}.get(legacy, legacy)
        else:
            data.pop("action", None)
        return data


class PineImportRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Pine Script source")


class PineImportResult(BaseModel):
    config: StrategyConfig
    warnings: list[str] = Field(default_factory=list)
    python_code: str = ""
    python_filename: str = ""
    strategy_id: str = ""
    reliability: str = "low"

class PineSavePythonResult(BaseModel):
    id: str
    name: str
    filename: str
    python_code: str
    warnings: list[str] = Field(default_factory=list)


class GeneratedRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


# --- Backtest / tuning / alerts ---

class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    period: str | None = None
    interval: str | None = None
    parameters: dict = Field(default_factory=dict)
    initial_cash: float = 10_000.0
    position_size_pct: float = 100.0
    commission_pct: float = 0.0
    # TradingView-like extras
    risk_percent: float = 2.0  # 0 = use position_size_pct instead
    slippage: float = 0.0  # absolute price units (TV slippage ticks × tick size)
    fill_on: Literal["next_open", "close"] = "next_open"


class Trade(BaseModel):
    """One completed round-trip (entry + exit on the same row)."""
    entry_date: str
    exit_date: str
    side: str  # Long | Short
    exit_reason: str  # TP | SL | Session | Signal | End
    entry_price: float
    exit_price: float
    shares: float
    pnl: float = 0.0
    pnl_pct: float = 0.0


class EquityPoint(BaseModel):
    date: str
    equity: float
    buy_hold: float = 0.0
    price: float = 0.0


class BacktestResult(BaseModel):
    strategy_id: str
    symbol: str
    parameters: dict
    direction: str = "long"
    initial_cash: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float = 0.0
    buy_hold_return_pct: float = 0.0
    num_trades: int
    trades: list[Trade]
    equity_curve: list[EquityPoint]


class TuningRequest(BaseModel):
    strategy_id: str
    symbol: str = "AAPL"
    period: str = "1y"
    interval: str = "1d"
    param_grid: dict[str, list] = Field(default_factory=dict)
    initial_cash: float = 10_000.0
    position_size_pct: float = 100.0
    commission_pct: float = 0.0
    risk_percent: float = 2.0
    slippage: float = 0.0
    fill_on: Literal["next_open", "close"] = "next_open"
    metric: str = "total_return_pct"


class TuningTrial(BaseModel):
    parameters: dict
    total_return_pct: float
    final_equity: float
    num_trades: int


class TuningResult(BaseModel):
    strategy_id: str
    symbol: str
    metric: str
    best_parameters: dict
    best_score: float
    trials: list[TuningTrial]


class AlertRequest(BaseModel):
    message: str


class AlertRule(BaseModel):
    id: str | None = None
    name: str
    strategy_id: str
    symbol: str
    # Candle timeframe for signal evaluation (Yahoo interval)
    interval: str = "1d"
    # Lookback window for market data fetch
    period: str = "3mo"
    parameters: dict = Field(default_factory=dict)
    enabled: bool = True
    notify_on: list[str] = Field(default_factory=lambda: ["entry", "exit"])


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    strategy_id: str | None = None
    symbol: str | None = None
    interval: str | None = None
    period: str | None = None
    parameters: dict | None = None
    enabled: bool | None = None
    notify_on: list[str] | None = None
