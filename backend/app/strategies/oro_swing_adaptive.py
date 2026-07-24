"""ORO / XAUUSD — Adaptive Swing (anti-streak). Port of the Pine strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategies.base import Strategy


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))
    # Wilder / RMA-style smoothing (closer to Pine ta.rsi)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_wilder(data: pd.DataFrame, length: int) -> pd.Series:
    """Pine ta.atr uses RMA; fall back to SMA ATR if needed."""
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    close = data["Close"].astype(float)
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev).abs(), (low - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / int(length), adjust=False).mean()


class OroSwingAdaptive(Strategy):
    id = "oro_swing_adaptive"
    name = "ORO Swing Adaptativo (Anti-Rachas)"
    description = (
        "XAUUSD/Gold swing: EMA50/200 trend + RSI cross of adaptive thresholds. "
        "After 2+ consecutive losses, RSI filter tightens and ATR stop widens. "
        "SL = ATR(20)×mult, TP = SL×R:R. Use ticker GC=F or XAUUSD=X; set Risk % ≈ 2 in backtest."
    )
    direction = "both"
    parameters = {
        "ema_fast": {"type": "int", "default": 50, "min": 10, "max": 100, "step": 1},
        "ema_slow": {"type": "int", "default": 200, "min": 100, "max": 300, "step": 5},
        "rsi_period": {"type": "int", "default": 14, "min": 5, "max": 30, "step": 1},
        "atr_length": {"type": "int", "default": 20, "min": 5, "max": 50, "step": 1},
        "rr_ratio": {"type": "float", "default": 3.0, "min": 1.5, "max": 5.0, "step": 0.5},
        "atr_mult_normal": {"type": "float", "default": 2.5, "min": 1.0, "max": 5.0, "step": 0.1},
        "atr_mult_strict": {"type": "float", "default": 3.0, "min": 1.0, "max": 6.0, "step": 0.1},
        "loss_streak": {"type": "int", "default": 2, "min": 1, "max": 5, "step": 1},
        "rsi_long_normal": {"type": "int", "default": 45, "min": 30, "max": 60, "step": 1},
        "rsi_long_strict": {"type": "int", "default": 50, "min": 35, "max": 65, "step": 1},
        "rsi_short_normal": {"type": "int", "default": 55, "min": 40, "max": 70, "step": 1},
        "rsi_short_strict": {"type": "int", "default": 50, "min": 35, "max": 65, "step": 1},
    }

    def generate_signal_frame(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        Emit entry + ATR stop/take. Anti-streak state is simulated here so later
        entries tighten filters after losing exits (same idea as the Pine script).
        Actual fills / risk-% sizing are handled by the backtester.
        """
        params = self.resolve_params(params)
        ema_fast_n = int(params["ema_fast"])
        ema_slow_n = int(params["ema_slow"])
        rsi_n = int(params["rsi_period"])
        atr_n = int(params["atr_length"])
        rr = float(params["rr_ratio"])
        atr_mult_n = float(params["atr_mult_normal"])
        atr_mult_s = float(params["atr_mult_strict"])
        streak_trigger = int(params["loss_streak"])
        rsi_long_n = float(params["rsi_long_normal"])
        rsi_long_s = float(params["rsi_long_strict"])
        rsi_short_n = float(params["rsi_short_normal"])
        rsi_short_s = float(params["rsi_short_strict"])

        if ema_fast_n >= ema_slow_n:
            raise ValueError("ema_fast must be < ema_slow")

        close = data["Close"].astype(float)
        high = data["High"].astype(float)
        low = data["Low"].astype(float)

        fast = close.ewm(span=ema_fast_n, adjust=False).mean()
        slow = close.ewm(span=ema_slow_n, adjust=False).mean()
        rsi = _rsi(close, rsi_n)
        atr = _atr_wilder(data, atr_n)

        entry = pd.Series(0, index=data.index, dtype=int)
        force_flat = pd.Series(False, index=data.index, dtype=bool)
        flat_reason = pd.Series("", index=data.index, dtype=object)
        stop = pd.Series(np.nan, index=data.index, dtype=float)
        take = pd.Series(np.nan, index=data.index, dtype=float)

        consecutive_losses = 0
        in_position = False
        side = 0
        entry_sl = 0.0
        entry_tp = 0.0
        entry_price = 0.0

        for i in range(len(data)):
            price = float(close.iloc[i])
            hi = float(high.iloc[i])
            lo = float(low.iloc[i])
            atr_i = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else 0.0
            rsi_i = float(rsi.iloc[i]) if pd.notna(rsi.iloc[i]) else float("nan")
            rsi_prev = float(rsi.iloc[i - 1]) if i > 0 and pd.notna(rsi.iloc[i - 1]) else float("nan")
            fast_i = float(fast.iloc[i]) if pd.notna(fast.iloc[i]) else float("nan")
            slow_i = float(slow.iloc[i]) if pd.notna(slow.iloc[i]) else float("nan")

            # --- Manage open trade (intrabar SL preferred over TP, like the backtester) ---
            if in_position:
                exit_px = None
                won = False
                if side == 1:
                    if lo <= entry_sl:
                        exit_px = entry_sl
                        won = exit_px > entry_price
                    elif hi >= entry_tp:
                        exit_px = entry_tp
                        won = exit_px > entry_price
                else:
                    if hi >= entry_sl:
                        exit_px = entry_sl
                        won = exit_px < entry_price
                    elif lo <= entry_tp:
                        exit_px = entry_tp
                        won = exit_px < entry_price

                if exit_px is not None:
                    consecutive_losses = 0 if won else consecutive_losses + 1
                    in_position = False
                    side = 0
                    entry_sl = entry_tp = entry_price = 0.0

            # --- Entries only when flat (strategy.position_size == 0) ---
            if in_position or atr_i <= 0 or np.isnan(rsi_i) or np.isnan(rsi_prev):
                continue
            if np.isnan(fast_i) or np.isnan(slow_i):
                continue

            strict = consecutive_losses >= streak_trigger
            rsi_long_th = rsi_long_s if strict else rsi_long_n
            rsi_short_th = rsi_short_s if strict else rsi_short_n
            sl_mult = atr_mult_s if strict else atr_mult_n

            cross_up = rsi_prev <= rsi_long_th and rsi_i > rsi_long_th
            cross_dn = rsi_prev >= rsi_short_th and rsi_i < rsi_short_th

            long_cond = fast_i > slow_i and cross_up and price > fast_i
            short_cond = fast_i < slow_i and cross_dn and price < fast_i

            if long_cond:
                sl_dist = atr_i * sl_mult
                if sl_dist > 0:
                    entry.iloc[i] = 1
                    stop.iloc[i] = price - sl_dist
                    take.iloc[i] = price + sl_dist * rr
                    in_position = True
                    side = 1
                    entry_price = price
                    entry_sl = float(stop.iloc[i])
                    entry_tp = float(take.iloc[i])
            elif short_cond:
                sl_dist = atr_i * sl_mult
                if sl_dist > 0:
                    entry.iloc[i] = -1
                    stop.iloc[i] = price + sl_dist
                    take.iloc[i] = price - sl_dist * rr
                    in_position = True
                    side = -1
                    entry_price = price
                    entry_sl = float(stop.iloc[i])
                    entry_tp = float(take.iloc[i])

        return pd.DataFrame(
            {
                "entry": entry,
                "force_flat": force_flat,
                "flat_reason": flat_reason,
                "stop": stop,
                "take": take,
            }
        )

    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.Series:
        """Held-position series for alerts / legacy callers."""
        frame = self.generate_signal_frame(data, params)
        position = 0
        stops = frame["stop"]
        takes = frame["take"]
        high = data["High"].astype(float)
        low = data["Low"].astype(float)
        out: list[int] = []
        entry_sl = entry_tp = 0.0

        for i in range(len(data)):
            if position == 1:
                if float(low.iloc[i]) <= entry_sl or float(high.iloc[i]) >= entry_tp:
                    position = 0
                    entry_sl = entry_tp = 0.0
            elif position == -1:
                if float(high.iloc[i]) >= entry_sl or float(low.iloc[i]) <= entry_tp:
                    position = 0
                    entry_sl = entry_tp = 0.0

            e = int(frame["entry"].iloc[i])
            if position == 0 and e != 0:
                position = e
                entry_sl = float(stops.iloc[i]) if pd.notna(stops.iloc[i]) else 0.0
                entry_tp = float(takes.iloc[i]) if pd.notna(takes.iloc[i]) else 0.0

            out.append(position)

        return pd.Series(out, index=data.index, dtype=int)
