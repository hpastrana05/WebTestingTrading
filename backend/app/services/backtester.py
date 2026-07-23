"""
TradingView-like backtester.

Defaults aimed at Pine `strategy()` behavior:
  - Entries fill on the next bar open (process_orders_on_close=false)
  - Stop / take-profit can fill intrabar on High/Low
  - If stop and take both touched in the same bar, stop wins (conservative)
  - Optional risk-% position sizing from stop distance
  - Absolute slippage in price units
  - Commission as percent of notional per fill
"""

from __future__ import annotations

import math

import pandas as pd

from app.schemas import BacktestResult, EquityPoint, Trade
from app.strategies.base import Strategy


def _fmt_date(ts, interval: str) -> str:
    stamp = pd.Timestamp(ts)
    if interval in ("1d", "5d", "1wk", "1mo", "3mo"):
        return stamp.strftime("%Y-%m-%d")
    return stamp.strftime("%Y-%m-%d %H:%M")


def _max_drawdown_pct(equities: list[float]) -> float:
    if not equities:
        return 0.0
    peak = equities[0]
    max_dd = 0.0
    for equity in equities:
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = ((equity / peak) - 1.0) * 100.0
            if dd < max_dd:
                max_dd = dd
    return round(max_dd, 2)


def _apply_slippage(side: str, price: float, slippage: float) -> float:
    """Adverse slippage in absolute price units."""
    if slippage <= 0:
        return price
    if side in ("buy", "cover"):
        return price + slippage
    return price - slippage  # sell / short


def _size_shares(
    side: int,
    equity: float,
    cash: float,
    fill_price: float,
    stop_price: float | None,
    size_pct: float,
    risk_percent: float,
) -> float:
    """Risk-% sizing when stop is known; otherwise % of cash."""
    if fill_price <= 0:
        return 0.0

    if risk_percent > 0 and stop_price is not None and not math.isnan(stop_price):
        sl_dist = abs(fill_price - stop_price)
        if sl_dist > 0:
            risk_money = equity * (risk_percent / 100.0)
            return risk_money / sl_dist

    allocate = cash * size_pct
    return allocate / fill_price if allocate > 0 else 0.0


def _intrabar_exit(
    position: int,
    high: float,
    low: float,
    stop: float | None,
    take: float | None,
) -> tuple[float, str] | None:
    """
    Return (fill_price, reason) if stop/take is hit this bar.
    If both touched: prefer SL (TradingView conservative default).
    """
    has_stop = stop is not None and not math.isnan(stop)
    has_take = take is not None and not math.isnan(take)

    if position == 1:
        stop_hit = has_stop and low <= stop  # type: ignore[operator]
        take_hit = has_take and high >= take  # type: ignore[operator]
        if stop_hit:
            return float(stop), "SL"  # type: ignore[arg-type]
        if take_hit:
            return float(take), "TP"  # type: ignore[arg-type]
    elif position == -1:
        stop_hit = has_stop and high >= stop  # type: ignore[operator]
        take_hit = has_take and low <= take  # type: ignore[operator]
        if stop_hit:
            return float(stop), "SL"  # type: ignore[arg-type]
        if take_hit:
            return float(take), "TP"  # type: ignore[arg-type]
    return None


def _pnl(side: str, entry_price: float, exit_price: float, shares: float) -> tuple[float, float]:
    if side == "Long":
        pnl = (exit_price - entry_price) * shares
    else:
        pnl = (entry_price - exit_price) * shares
    pnl_pct = ((exit_price / entry_price) - 1.0) * 100.0 if side == "Long" else (
        ((entry_price / exit_price) - 1.0) * 100.0 if exit_price else 0.0
    )
    if side == "Short":
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0 if entry_price else 0.0
    return round(pnl, 2), round(pnl_pct, 2)


def run_backtest(
    strategy: Strategy,
    data: pd.DataFrame,
    parameters: dict | None = None,
    initial_cash: float = 10_000.0,
    symbol: str = "",
    interval: str = "1d",
    position_size_pct: float = 100.0,
    commission_pct: float = 0.0,
    risk_percent: float = 0.0,
    slippage: float = 0.0,
    fill_on: str = "next_open",
) -> BacktestResult:
    if fill_on not in ("next_open", "close"):
        raise ValueError("fill_on must be 'next_open' or 'close'")

    size_pct = max(0.0, min(float(position_size_pct), 100.0)) / 100.0
    commission_rate = max(0.0, float(commission_pct)) / 100.0
    risk_pct = max(0.0, float(risk_percent))
    slip = max(0.0, float(slippage))

    params = strategy.resolve_params(parameters)
    frame = strategy.generate_signal_frame(data, params)
    direction = getattr(strategy, "direction", "long")

    cash = float(initial_cash)
    shares = 0.0
    position = 0
    stop_price: float | None = None
    take_price: float | None = None
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    # Open trade tracking (paired into one row on exit)
    open_side = ""
    open_date = ""
    open_price = 0.0
    open_shares = 0.0

    pending_side = 0
    pending_stop: float | None = None
    pending_take: float | None = None

    first_price = float(data.iloc[0]["Close"])
    buy_hold_shares = initial_cash / first_price if first_price > 0 else 0.0
    index = list(data.index)

    def close_trade(exit_date: str, exit_fill: float, reason: str) -> None:
        nonlocal cash, shares, position, stop_price, take_price
        nonlocal open_side, open_date, open_price, open_shares

        if shares <= 0 or position == 0:
            return

        notional = shares * exit_fill
        fee = notional * commission_rate
        if position == 1:
            cash += notional - fee
        else:
            cash -= notional + fee

        pnl, pnl_pct = _pnl(open_side, open_price, exit_fill, shares)
        # Approximate commission drag on pnl
        entry_fee = open_shares * open_price * commission_rate
        pnl = round(pnl - entry_fee - fee, 2)

        trades.append(
            Trade(
                entry_date=open_date,
                exit_date=exit_date,
                side=open_side,
                exit_reason=reason,
                entry_price=round(open_price, 4),
                exit_price=round(exit_fill, 4),
                shares=round(shares, 6),
                pnl=pnl,
                pnl_pct=pnl_pct,
            )
        )
        shares = 0.0
        position = 0
        stop_price = take_price = None
        open_side = ""
        open_date = ""
        open_price = 0.0
        open_shares = 0.0

    def open_trade(side: int, date_str: str, fill: float, stop: float | None, take: float | None) -> None:
        nonlocal cash, shares, position, stop_price, take_price
        nonlocal open_side, open_date, open_price, open_shares

        qty = _size_shares(side, cash, cash, fill, stop, size_pct, risk_pct)
        if qty <= 0:
            return
        if side == 1:
            max_qty = cash / (fill * (1.0 + commission_rate)) if fill > 0 else 0.0
            qty = min(qty, max_qty)
        if qty <= 0:
            return

        notional = qty * fill
        fee = notional * commission_rate
        if side == 1:
            if notional + fee > cash + 1e-9:
                return
            cash -= notional + fee
            position = 1
            open_side = "Long"
        else:
            cash += notional - fee
            position = -1
            open_side = "Short"

        shares = qty
        open_date = date_str
        open_price = fill
        open_shares = qty
        stop_price, take_price = stop, take

    for date in index:
        row = data.loc[date]
        open_ = float(row["Open"])
        high = float(row["High"])
        low = float(row["Low"])
        close = float(row["Close"])
        date_str = _fmt_date(date, interval)

        entry_sig = int(frame["entry"].loc[date]) if date in frame.index else 0
        force_flat = bool(frame["force_flat"].loc[date]) if date in frame.index else False
        flat_reason = "Signal"
        if date in frame.index and "flat_reason" in frame.columns:
            raw_reason = frame["flat_reason"].loc[date]
            if isinstance(raw_reason, str) and raw_reason:
                flat_reason = raw_reason
        raw_stop = frame["stop"].loc[date] if date in frame.index else float("nan")
        raw_take = frame["take"].loc[date] if date in frame.index else float("nan")
        sig_stop = float(raw_stop) if pd.notna(raw_stop) else None
        sig_take = float(raw_take) if pd.notna(raw_take) else None

        # --- 1) Fill pending entry at open ---
        if pending_side != 0 and position == 0:
            side_name = "buy" if pending_side == 1 else "short"
            fill = _apply_slippage(side_name, open_, slip)
            open_trade(pending_side, date_str, fill, pending_stop, pending_take)
            pending_side = 0
            pending_stop = pending_take = None

        # --- 2) Intrabar stop / take ---
        if position != 0:
            hit = _intrabar_exit(position, high, low, stop_price, take_price)
            if hit is not None:
                exit_px, reason = hit
                side_name = "sell" if position == 1 else "cover"
                fill = _apply_slippage(side_name, exit_px, slip)
                close_trade(date_str, fill, reason)

        # --- 3) Force flat (session / indicator) ---
        if position != 0 and force_flat:
            side_name = "sell" if position == 1 else "cover"
            fill = _apply_slippage(side_name, close, slip)
            close_trade(date_str, fill, flat_reason)
            pending_side = 0
            pending_stop = pending_take = None

        # --- 4) New entry signal ---
        if entry_sig != 0 and position == 0 and pending_side == 0:
            if fill_on == "close":
                side_name = "buy" if entry_sig == 1 else "short"
                fill = _apply_slippage(side_name, close, slip)
                open_trade(entry_sig, date_str, fill, sig_stop, sig_take)
            else:
                pending_side = entry_sig
                pending_stop = sig_stop
                pending_take = sig_take

        if position == 1:
            equity = cash + shares * close
        elif position == -1:
            equity = cash - shares * close
        else:
            equity = cash

        equity_curve.append(
            EquityPoint(
                date=date_str,
                equity=round(equity, 2),
                buy_hold=round(buy_hold_shares * close, 2),
                price=round(close, 4),
            )
        )

    # Close any open position at the last bar
    if position != 0 and len(index) > 0:
        last = data.loc[index[-1]]
        last_date = _fmt_date(index[-1], interval)
        side_name = "sell" if position == 1 else "cover"
        fill = _apply_slippage(side_name, float(last["Close"]), slip)
        close_trade(last_date, fill, "End")

    final_equity = equity_curve[-1].equity if equity_curve else initial_cash
    total_return_pct = ((final_equity / initial_cash) - 1.0) * 100.0
    buy_hold_final = equity_curve[-1].buy_hold if equity_curve else initial_cash
    buy_hold_return_pct = ((buy_hold_final / initial_cash) - 1.0) * 100.0

    return BacktestResult(
        strategy_id=strategy.id,
        symbol=symbol,
        parameters=params,
        direction=direction,
        initial_cash=initial_cash,
        final_equity=round(final_equity, 2),
        total_return_pct=round(total_return_pct, 2),
        max_drawdown_pct=_max_drawdown_pct([p.equity for p in equity_curve]),
        buy_hold_return_pct=round(buy_hold_return_pct, 2),
        num_trades=len(trades),
        trades=trades,
        equity_curve=equity_curve,
    )
