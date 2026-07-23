"""Session helpers and shared market computations for rule-based strategies."""

from __future__ import annotations

from datetime import time

import pandas as pd


def parse_hhmm(token: str) -> time:
    token = token.strip().replace(":", "")
    if len(token) != 4 or not token.isdigit():
        raise ValueError(f"Invalid time '{token}'. Use HHMM or HH:MM.")
    hour = int(token[:2])
    minute = int(token[2:])
    if hour > 23 or minute > 59:
        raise ValueError(f"Invalid time '{token}'.")
    return time(hour, minute)


def parse_session(session: str) -> tuple[time, time] | None:
    """Parse '1545-1930' or '15:45-19:30'. Empty => None (always open)."""
    session = (session or "").strip()
    if not session:
        return None
    if "-" not in session:
        raise ValueError("Session must look like 1545-1930 or 15:45-19:30")
    left, right = session.split("-", 1)
    return parse_hhmm(left), parse_hhmm(right)


def localize_index(index: pd.DatetimeIndex, timezone: str) -> pd.DatetimeIndex:
    """Return index converted to the given timezone."""
    tz = timezone or "UTC"
    if index.tz is None:
        # Yahoo intraday is typically UTC; daily is naive date.
        try:
            return index.tz_localize("UTC").tz_convert(tz)
        except Exception:
            return index.tz_localize(tz)
    return index.tz_convert(tz)


def session_mask(
    index: pd.DatetimeIndex,
    session: str,
    timezone: str,
) -> pd.Series:
    """True when bar timestamp (in timezone) falls inside session."""
    bounds = parse_session(session)
    if bounds is None:
        return pd.Series(True, index=index)
    start, end = bounds
    local = localize_index(index, timezone)
    times = pd.Series([ts.time() for ts in local], index=index)
    if start <= end:
        mask = (times >= start) & (times <= end)
    else:
        mask = (times >= start) | (times <= end)
    return mask.fillna(False)


def day_keys(index: pd.DatetimeIndex, timezone: str) -> pd.Series:
    local = localize_index(index, timezone)
    return pd.Series([ts.date() for ts in local], index=index)


def session_vwap(data: pd.DataFrame, timezone: str = "UTC") -> pd.Series:
    """Daily session VWAP from HLC3 * Volume (resets each local day)."""
    hlc3 = (data["High"] + data["Low"] + data["Close"]) / 3.0
    volume = data["Volume"].astype(float).clip(lower=0)
    pv = hlc3 * volume
    days = day_keys(data.index, timezone)
    cum_pv = pv.groupby(days).cumsum()
    cum_vol = volume.groupby(days).cumsum()
    vwap = cum_pv / cum_vol.where(cum_vol > 0)
    return vwap.astype("float64")


def atr_series(data: pd.DataFrame, length: int = 14) -> pd.Series:
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    close = data["Close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(int(length)).mean()
