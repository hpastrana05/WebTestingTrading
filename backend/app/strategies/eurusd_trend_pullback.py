"""EURUSD — Trend Pullback Simple. Port of the Pine strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.market_filters import session_mask
from app.strategies.base import Strategy


def _atr_wilder(data: pd.DataFrame, length: int) -> pd.Series:
    """Pine ta.atr uses RMA (Wilder)."""
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    close = data["Close"].astype(float)
    prev = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev).abs(), (low - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / int(length), adjust=False).mean()


class EurUsdTrendPullback(Strategy):
    id = "eurusd_trend_pullback"
    name = "EURUSD Trend Pullback Simple"
    description = (
        "EURUSD trend-pullback: EMA slope filter + pullback to EMA + continuation candle. "
        "SL = ATR×sl_mult, TP = ATR×tp_mult. Session Europe/Madrid 08:00–17:30 entry, "
        "21:55–22:00 forced close. Use ticker EURUSD=X; set Risk % ≈ 1 in backtest."
    )
    direction = "both"
    parameters = {
        "ema_length": {"type": "int", "default": 50, "min": 10, "max": 200, "step": 1},
        "slope_bars": {"type": "int", "default": 5, "min": 1, "max": 20, "step": 1},
        "atr_length": {"type": "int", "default": 14, "min": 5, "max": 50, "step": 1},
        "min_atr": {"type": "float", "default": 0.0003, "min": 0.00005, "max": 0.005, "step": 0.00005},
        "sl_atr": {"type": "float", "default": 1.2, "min": 0.5, "max": 3.0, "step": 0.1},
        "tp_atr": {"type": "float", "default": 2.0, "min": 1.0, "max": 5.0, "step": 0.1},
        "use_session_filter": {"type": "int", "default": 1, "min": 0, "max": 1, "step": 1},
    }

    trade_session = "0800-1730"
    close_session = "2155-2200"
    timezone = "Europe/Madrid"

    def generate_signal_frame(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        Emit entry + ATR stop/take. Session flatten is force_flat.
        Actual fills / risk-% sizing are handled by the backtester.
        """
        params = self.resolve_params(params)
        ema_len = int(params["ema_length"])
        slope_n = int(params["slope_bars"])
        atr_len = int(params["atr_length"])
        min_atr = float(params["min_atr"])
        sl_mult = float(params["sl_atr"])
        tp_mult = float(params["tp_atr"])
        use_session = bool(int(params["use_session_filter"]))

        open_ = data["Open"].astype(float)
        close = data["Close"].astype(float)
        high = data["High"].astype(float)
        low = data["Low"].astype(float)

        ema = close.ewm(span=ema_len, adjust=False).mean()
        atr = _atr_wilder(data, atr_len)

        ema_up = ema > ema.shift(slope_n)
        ema_down = ema < ema.shift(slope_n)
        bull_trend = (close > ema) & ema_up
        bear_trend = (close < ema) & ema_down
        enough_vol = atr >= min_atr

        # Pullback touched EMA on either of the previous two bars
        pullback_long = (low.shift(1) <= ema.shift(1)) | (low.shift(2) <= ema.shift(2))
        pullback_short = (high.shift(1) >= ema.shift(1)) | (high.shift(2) >= ema.shift(2))

        # Continuation candle
        bull_cont = (close > open_) & (close > high.shift(1))
        bear_cont = (close < open_) & (close < low.shift(1))

        if use_session:
            in_trade = session_mask(data.index, self.trade_session, self.timezone)
            in_close = session_mask(data.index, self.close_session, self.timezone)
        else:
            in_trade = pd.Series(True, index=data.index)
            in_close = pd.Series(False, index=data.index)

        long_setup = in_trade & bull_trend & pullback_long & bull_cont & enough_vol
        short_setup = in_trade & bear_trend & pullback_short & bear_cont & enough_vol

        entry = pd.Series(0, index=data.index, dtype=int)
        force_flat = pd.Series(False, index=data.index, dtype=bool)
        flat_reason = pd.Series("", index=data.index, dtype=object)
        stop = pd.Series(np.nan, index=data.index, dtype=float)
        take = pd.Series(np.nan, index=data.index, dtype=float)

        in_position = False
        side = 0
        entry_sl = 0.0
        entry_tp = 0.0

        for i in range(len(data)):
            price = float(close.iloc[i])
            hi = float(high.iloc[i])
            lo = float(low.iloc[i])
            atr_i = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else 0.0

            # Manage open trade (SL preferred over TP, like the backtester)
            if in_position:
                exited = False
                if side == 1:
                    if lo <= entry_sl or hi >= entry_tp:
                        exited = True
                else:
                    if hi >= entry_sl or lo <= entry_tp:
                        exited = True
                if exited:
                    in_position = False
                    side = 0
                    entry_sl = entry_tp = 0.0

            # Forced end-of-day close
            if in_position and bool(in_close.iloc[i]):
                force_flat.iloc[i] = True
                flat_reason.iloc[i] = "Session"
                in_position = False
                side = 0
                entry_sl = entry_tp = 0.0
                continue

            if in_position or atr_i <= 0:
                continue

            if bool(long_setup.iloc[i]):
                sl_dist = atr_i * sl_mult
                tp_dist = atr_i * tp_mult
                if sl_dist > 0 and tp_dist > 0:
                    entry.iloc[i] = 1
                    stop.iloc[i] = price - sl_dist
                    take.iloc[i] = price + tp_dist
                    in_position = True
                    side = 1
                    entry_sl = float(stop.iloc[i])
                    entry_tp = float(take.iloc[i])
            elif bool(short_setup.iloc[i]):
                sl_dist = atr_i * sl_mult
                tp_dist = atr_i * tp_mult
                if sl_dist > 0 and tp_dist > 0:
                    entry.iloc[i] = -1
                    stop.iloc[i] = price + sl_dist
                    take.iloc[i] = price - tp_dist
                    in_position = True
                    side = -1
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
            if position != 0 and bool(frame["force_flat"].iloc[i]):
                position = 0
                entry_sl = entry_tp = 0.0

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
