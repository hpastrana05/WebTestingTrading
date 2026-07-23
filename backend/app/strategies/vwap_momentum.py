"""VWAP Momentum Pro — approximate port of the Pine Script strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.market_filters import atr_series, day_keys, session_mask, session_vwap
from app.strategies.base import Strategy


class VwapMomentum(Strategy):
    id = "vwap_momentum"
    name = "VWAP Momentum Pro"
    description = (
        "NASDAQ-style VWAP momentum (long+short): session VWAP cross + EMA filter + "
        "bar impulse, structure ATR stop with R:R target, one trade/day, Madrid sessions "
        "15:45–19:30 entry / 21:50–22:00 forced close."
    )
    direction = "both"
    parameters = {
        "ema_length": {"type": "int", "default": 20, "min": 5, "max": 100, "step": 1},
        "atr_length": {"type": "int", "default": 14, "min": 5, "max": 50, "step": 1},
        "atr_mult": {"type": "float", "default": 1.1, "min": 0.5, "max": 3.0, "step": 0.1},
        "rr_ratio": {"type": "float", "default": 2.3, "min": 1.0, "max": 5.0, "step": 0.1},
        "impulse_lookback": {"type": "int", "default": 15, "min": 5, "max": 50, "step": 1},
        "impulse_mult": {"type": "float", "default": 1.1, "min": 1.0, "max": 3.0, "step": 0.1},
    }

    # Matches the Pine defaults (Europe/Madrid)
    trade_session = "1545-1930"
    close_session = "2150-2200"
    timezone = "Europe/Madrid"

    def generate_signal_frame(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        Emit entry events + stop/take levels. SL/TP fills are left to the backtester
        (TradingView-style), including intrabar High/Low checks.
        """
        params = self.resolve_params(params)
        ema_len = int(params["ema_length"])
        atr_len = int(params["atr_length"])
        atr_mult = float(params["atr_mult"])
        rr_ratio = float(params["rr_ratio"])
        impulse_n = int(params["impulse_lookback"])
        impulse_mult = float(params["impulse_mult"])

        close = data["Close"].astype(float)
        high = data["High"].astype(float)
        low = data["Low"].astype(float)

        vwap = session_vwap(data, self.timezone)
        ema = close.ewm(span=ema_len, adjust=False).mean()
        atr = atr_series(data, atr_len)
        bar_range = high - low
        ma_range = bar_range.rolling(impulse_n).mean()
        has_impulse = bar_range > (ma_range * impulse_mult)

        in_trade = session_mask(data.index, self.trade_session, self.timezone)
        in_close = session_mask(data.index, self.close_session, self.timezone)
        days = day_keys(data.index, self.timezone)

        cross_above = (close > vwap) & (close.shift(1) <= vwap.shift(1))
        cross_below = (close < vwap) & (close.shift(1) >= vwap.shift(1))

        long_setup = in_trade & cross_above & (close > ema) & has_impulse
        short_setup = in_trade & cross_below & (close < ema) & has_impulse

        entry = pd.Series(0, index=data.index, dtype=int)
        force_flat = pd.Series(False, index=data.index, dtype=bool)
        flat_reason = pd.Series("", index=data.index, dtype=object)
        stop = pd.Series(np.nan, index=data.index, dtype=float)
        take = pd.Series(np.nan, index=data.index, dtype=float)

        in_position = False
        traded_day = None

        for i in range(len(data)):
            price = float(close.iloc[i])
            day = days.iloc[i]
            atr_i = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else 0.0

            if traded_day is not None and day != traded_day:
                traded_day = None

            # Forced intraday close (market flatten — backtester executes it)
            if in_position and bool(in_close.iloc[i]):
                force_flat.iloc[i] = True
                flat_reason.iloc[i] = "Session"
                in_position = False

            if not in_position and traded_day != day and atr_i > 0:
                if bool(long_setup.iloc[i]):
                    sl_dist = max(price - float(low.iloc[i]), atr_i * atr_mult)
                    if sl_dist > 0:
                        entry.iloc[i] = 1
                        stop.iloc[i] = price - sl_dist
                        take.iloc[i] = price + sl_dist * rr_ratio
                        in_position = True
                        traded_day = day
                elif bool(short_setup.iloc[i]):
                    sl_dist = max(float(high.iloc[i]) - price, atr_i * atr_mult)
                    if sl_dist > 0:
                        entry.iloc[i] = -1
                        stop.iloc[i] = price + sl_dist
                        take.iloc[i] = price - sl_dist * rr_ratio
                        in_position = True
                        traded_day = day

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
        """Approximate held-position series for alerts / legacy callers."""
        frame = self.generate_signal_frame(data, params)
        position = 0
        stops = frame["stop"]
        takes = frame["take"]
        close = data["Close"].astype(float)
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
