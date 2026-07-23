import pandas as pd

from app.schemas import BacktestResult, EquityPoint, Trade
from app.strategies.base import Strategy


def run_backtest(
    strategy: Strategy,
    data: pd.DataFrame,
    parameters: dict | None = None,
    initial_cash: float = 10_000.0,
    symbol: str = "",
) -> BacktestResult:
    """
    Simple long-only backtester.
    Buys all-in when signal goes 0 -> 1, sells all when signal goes 1 -> 0.
    """
    params = strategy.resolve_params(parameters)
    signals = strategy.generate_signals(data, params)

    cash = float(initial_cash)
    shares = 0.0
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    prev_signal = 0
    for date, row in data.iterrows():
        price = float(row["Close"])
        signal = int(signals.loc[date]) if date in signals.index else 0
        date_str = pd.Timestamp(date).strftime("%Y-%m-%d")

        if prev_signal == 0 and signal == 1 and cash > 0:
            shares = cash / price
            trades.append(Trade(date=date_str, side="buy", price=price, shares=shares))
            cash = 0.0
        elif prev_signal == 1 and signal == 0 and shares > 0:
            cash = shares * price
            trades.append(Trade(date=date_str, side="sell", price=price, shares=shares))
            shares = 0.0

        equity = cash + shares * price
        equity_curve.append(EquityPoint(date=date_str, equity=round(equity, 2)))
        prev_signal = signal

    final_equity = equity_curve[-1].equity if equity_curve else initial_cash
    total_return_pct = ((final_equity / initial_cash) - 1.0) * 100.0

    return BacktestResult(
        strategy_id=strategy.id,
        symbol=symbol,
        parameters=params,
        initial_cash=initial_cash,
        final_equity=round(final_equity, 2),
        total_return_pct=round(total_return_pct, 2),
        num_trades=len(trades),
        trades=trades,
        equity_curve=equity_curve,
    )
