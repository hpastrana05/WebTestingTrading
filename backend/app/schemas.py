from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Built-in strategy info (legacy list) ---

class StrategyInfo(BaseModel):
    id: str
    name: str
    description: str
    parameters: dict[str, dict]
    source: str = "builtin"  # builtin | custom


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
    """Condition or nested group. type=condition|group"""
    type: Literal["condition", "group"] = "condition"
    # condition fields
    left: Operand | None = None
    operator: str | None = None
    right: Operand | None = None
    # group fields
    logic: Literal["all", "any"] | None = None
    children: list[RuleNode] = Field(default_factory=list)


class StrategyConfig(BaseModel):
    id: str | None = None
    name: str
    broker_ticker: str = ""
    yahoo_ticker: str = "AAPL"
    interval: str = "1d"
    period: str = "1y"
    action: Literal["buy"] = "buy"
    entry: RuleNode = Field(
        default_factory=lambda: RuleNode(type="group", logic="all", children=[])
    )
    exit: RuleNode = Field(
        default_factory=lambda: RuleNode(type="group", logic="any", children=[])
    )


class StrategyConfigUpdate(BaseModel):
    name: str | None = None
    broker_ticker: str | None = None
    yahoo_ticker: str | None = None
    interval: str | None = None
    period: str | None = None
    action: Literal["buy"] | None = None
    entry: RuleNode | None = None
    exit: RuleNode | None = None


# --- Backtest / tuning / alerts ---

class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str | None = None
    period: str | None = None
    interval: str | None = None
    parameters: dict = Field(default_factory=dict)
    initial_cash: float = 10_000.0


class Trade(BaseModel):
    date: str
    side: str
    price: float
    shares: float


class EquityPoint(BaseModel):
    date: str
    equity: float


class BacktestResult(BaseModel):
    strategy_id: str
    symbol: str
    parameters: dict
    initial_cash: float
    final_equity: float
    total_return_pct: float
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
    parameters: dict = Field(default_factory=dict)
    enabled: bool = True
    notify_on: list[str] = Field(default_factory=lambda: ["entry", "exit"])


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    strategy_id: str | None = None
    symbol: str | None = None
    parameters: dict | None = None
    enabled: bool | None = None
    notify_on: list[str] | None = None
