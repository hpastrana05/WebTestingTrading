"""Compute pandas-ta indicators and evaluate nested entry/exit rule trees."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta

from app.services.indicator_catalog import get_indicator
from app.services.market_filters import (
    atr_series,
    day_keys,
    session_mask,
    session_vwap,
)


def compute_indicator(
    data: pd.DataFrame,
    indicator_id: str,
    params: dict[str, Any],
    output: str,
    timezone: str = "UTC",
) -> pd.Series:
    # Custom indicators (not plain pandas-ta wrappers)
    if indicator_id == "vwap":
        return session_vwap(data, timezone)

    if indicator_id == "range_sma":
        length = int(params.get("length", 15))
        bar_range = data["High"].astype(float) - data["Low"].astype(float)
        return bar_range.rolling(length).mean()

    meta = get_indicator(indicator_id)
    fn = getattr(ta, indicator_id, None)
    if fn is None:
        raise ValueError(f"pandas-ta has no function '{indicator_id}'")

    kwargs: dict[str, Any] = {}
    for inp in meta["inputs"]:
        col = inp.capitalize() if inp != "close" else "Close"
        # pandas_ta uses open_/high/low/close/volume kwargs
        key = "open_" if inp == "open" else inp
        kwargs[key] = data[col if col in data.columns else inp.capitalize()]

    # Merge defaults then overrides
    for p in meta["params"]:
        kwargs[p["name"]] = params.get(p["name"], p["default"])

    result = fn(**kwargs)
    series = _pick_output(result, output, indicator_id)
    return series.reindex(data.index)


def _pick_output(result: pd.Series | pd.DataFrame, output: str, indicator_id: str) -> pd.Series:
    if isinstance(result, pd.Series):
        return result

    # Prefer columns that start with the logical output id (MACD, BBU, RSI, ...)
    matches = [c for c in result.columns if str(c).upper().startswith(output.upper())]
    if matches:
        return result[matches[0]]

    # Fallback: first column
    if len(result.columns) == 1:
        return result.iloc[:, 0]

    raise ValueError(
        f"Could not resolve output '{output}' for {indicator_id}. "
        f"Available: {list(result.columns)}"
    )


def resolve_operand(
    data: pd.DataFrame,
    operand: dict,
    timezone: str = "UTC",
) -> pd.Series:
    kind = operand.get("kind")
    if kind == "price":
        field = operand.get("field", "Close")
        if field == "HLC3":
            return (
                data["High"].astype(float)
                + data["Low"].astype(float)
                + data["Close"].astype(float)
            ) / 3.0
        if field == "BarRange":
            return data["High"].astype(float) - data["Low"].astype(float)
        if field not in data.columns:
            raise ValueError(f"Unknown price field: {field}")
        return data[field].astype(float)

    if kind == "value":
        value = float(operand.get("value", 0))
        return pd.Series(value, index=data.index, dtype=float)

    if kind == "indicator":
        return compute_indicator(
            data,
            indicator_id=operand["indicator"],
            params=operand.get("params") or {},
            output=operand.get("output") or get_indicator(operand["indicator"])["outputs"][0]["id"],
            timezone=timezone,
        )

    raise ValueError(f"Unknown operand kind: {kind}")


def evaluate_condition(
    data: pd.DataFrame,
    condition: dict,
    timezone: str = "UTC",
) -> pd.Series:
    left = resolve_operand(data, condition["left"], timezone)
    right = resolve_operand(data, condition["right"], timezone)
    scale = float(condition.get("right_scale") or 1.0)
    if scale != 1.0:
        right = right * scale
    op = condition.get("operator", ">")

    if op == ">":
        mask = left > right
    elif op == "<":
        mask = left < right
    elif op == ">=":
        mask = left >= right
    elif op == "<=":
        mask = left <= right
    elif op == "==":
        mask = left == right
    elif op == "cross_above":
        mask = (left > right) & (left.shift(1) <= right.shift(1))
    elif op == "cross_below":
        mask = (left < right) & (left.shift(1) >= right.shift(1))
    else:
        raise ValueError(f"Unknown operator: {op}")

    return mask.fillna(False)


def _risk_hit(risk: str, pct: float, position: int, entry_price: float, price: float) -> bool:
    if pct <= 0 or entry_price <= 0 or position == 0:
        return False
    move = pct / 100.0
    if risk == "stop_loss":
        if position == 1:
            return price <= entry_price * (1.0 - move)
        return price >= entry_price * (1.0 + move)
    if risk == "take_profit":
        if position == 1:
            return price >= entry_price * (1.0 + move)
        return price <= entry_price * (1.0 - move)
    return False


def _structure_hit(position: int, price: float, entry_sl: float, entry_tp: float) -> bool:
    if position == 0 or entry_sl == 0 and entry_tp == 0:
        return False
    if position == 1:
        return price <= entry_sl or price >= entry_tp
    return price >= entry_sl or price <= entry_tp


def evaluate_exit_node(
    node: dict,
    index: int,
    position: int,
    entry_price: float,
    price: float,
    condition_cache: dict[int, pd.Series],
    entry_sl: float = 0.0,
    entry_tp: float = 0.0,
) -> bool:
    """Evaluate one exit tree node at a single bar (supports risk nodes)."""
    node_type = node.get("type", "condition")

    if node_type == "risk":
        risk = node.get("risk") or ""
        if risk == "structure_atr":
            return _structure_hit(position, price, entry_sl, entry_tp)
        return _risk_hit(
            risk=risk,
            pct=float(node.get("pct") or 0),
            position=position,
            entry_price=entry_price,
            price=price,
        )

    if node_type == "group":
        children = node.get("children") or []
        if not children:
            return False
        logic = (node.get("logic") or "any").lower()
        results = [
            evaluate_exit_node(
                child, index, position, entry_price, price, condition_cache, entry_sl, entry_tp
            )
            for child in children
        ]
        return all(results) if logic in ("all", "and") else any(results)

    # Regular condition — use precomputed mask
    mask = condition_cache.get(id(node))
    if mask is None:
        return False
    return bool(mask.iloc[index])


def _cache_conditions(
    data: pd.DataFrame,
    node: dict,
    cache: dict[int, pd.Series],
    timezone: str,
) -> None:
    node_type = node.get("type", "condition")
    if node_type == "group":
        for child in node.get("children") or []:
            _cache_conditions(data, child, cache, timezone)
    elif node_type == "condition":
        cache[id(node)] = evaluate_condition(data, node, timezone)


def evaluate_group(
    data: pd.DataFrame,
    group: dict,
    timezone: str = "UTC",
) -> pd.Series:
    """Recursively evaluate a group of conditions with ALL/ANY logic (no risk nodes)."""
    children = group.get("children") or []
    logic = (group.get("logic") or "all").lower()

    if not children:
        return pd.Series(False, index=data.index)

    masks: list[pd.Series] = []
    for child in children:
        child_type = child.get("type", "condition")
        if child_type == "risk":
            continue
        if child_type == "group":
            masks.append(evaluate_group(data, child, timezone))
        else:
            masks.append(evaluate_condition(data, child, timezone))

    if not masks:
        return pd.Series(False, index=data.index)

    combined = masks[0]
    for mask in masks[1:]:
        if logic in ("all", "and"):
            combined = combined & mask
        else:
            combined = combined | mask

    return combined.fillna(False)


def find_structure_atr(node: dict | None) -> dict | None:
    if not node:
        return None
    if node.get("type") == "risk" and node.get("risk") == "structure_atr":
        return node
    for child in node.get("children") or []:
        found = find_structure_atr(child)
        if found:
            return found
    return None


def _structure_levels(
    position: int,
    price: float,
    high: float,
    low: float,
    atr_value: float,
    atr_mult: float,
    rr_ratio: float,
) -> tuple[float, float]:
    if atr_value <= 0:
        return 0.0, 0.0
    if position == 1:
        sl_dist = max(price - low, atr_value * atr_mult)
        return price - sl_dist, price + sl_dist * rr_ratio
    sl_dist = max(high - price, atr_value * atr_mult)
    return price + sl_dist, price - sl_dist * rr_ratio


def _pct_levels(side: int, price: float, stop_pct: float, take_pct: float) -> tuple[float, float]:
    stop = take = float("nan")
    if stop_pct > 0:
        stop = price * (1.0 - stop_pct / 100.0) if side == 1 else price * (1.0 + stop_pct / 100.0)
    if take_pct > 0:
        take = price * (1.0 + take_pct / 100.0) if side == 1 else price * (1.0 - take_pct / 100.0)
    return stop, take


def find_risk_pct(node: dict | None, risk_kind: str) -> float:
    if not node:
        return 0.0
    if node.get("type") == "risk" and node.get("risk") == risk_kind:
        return float(node.get("pct") or 0)
    for child in node.get("children") or []:
        value = find_risk_pct(child, risk_kind)
        if value > 0:
            return value
    return 0.0


def _indicator_exit_only(
    node: dict,
    index: int,
    position: int,
    entry_price: float,
    price: float,
    condition_cache: dict[int, pd.Series],
) -> bool:
    """Exit rules excluding risk nodes (SL/TP handled by the backtester)."""
    node_type = node.get("type", "condition")
    if node_type == "risk":
        return False
    if node_type == "group":
        children = node.get("children") or []
        if not children:
            return False
        logic = (node.get("logic") or "any").lower()
        results = [
            _indicator_exit_only(child, index, position, entry_price, price, condition_cache)
            for child in children
        ]
        # Ignore risk-only children that always return False
        if not any(
            child.get("type") != "risk" for child in children
        ):
            return False
        filtered = []
        for child, result in zip(children, results):
            if child.get("type") == "risk":
                continue
            filtered.append(result)
        if not filtered:
            return False
        return all(filtered) if logic in ("all", "and") else any(filtered)
    mask = condition_cache.get(id(node))
    if mask is None:
        return False
    return bool(mask.iloc[index])


def generate_signal_frame(
    data: pd.DataFrame,
    entry_group: dict,
    exit_group: dict,
    direction: str = "long",
    entry_short_group: dict | None = None,
    trade_session: str = "",
    close_session: str = "",
    timezone: str = "Europe/Madrid",
    one_trade_per_day: bool = False,
) -> pd.DataFrame:
    """
    TradingView-style plan: entry events + stop/take levels + force_flat.
    Risk exits are not applied here — the backtester fills them intrabar.
    """
    if direction not in ("long", "short", "both"):
        raise ValueError("direction must be 'long', 'short', or 'both'")

    long_entry = evaluate_group(data, entry_group, timezone) if direction in ("long", "both") else None
    if direction == "short":
        short_entry = evaluate_group(data, entry_group, timezone)
    elif direction == "both":
        short_entry = evaluate_group(
            data, entry_short_group or {"type": "group", "children": []}, timezone
        )
    else:
        short_entry = None

    if trade_session:
        trade_mask = session_mask(data.index, trade_session, timezone)
        if long_entry is not None:
            long_entry = long_entry & trade_mask
        if short_entry is not None:
            short_entry = short_entry & trade_mask

    close_mask = (
        session_mask(data.index, close_session, timezone)
        if close_session
        else pd.Series(False, index=data.index)
    )
    days = day_keys(data.index, timezone) if one_trade_per_day else None

    exit_cache: dict[int, pd.Series] = {}
    _cache_conditions(data, exit_group, exit_cache, timezone)
    structure = find_structure_atr(exit_group)
    stop_pct = find_risk_pct(exit_group, "stop_loss")
    take_pct = find_risk_pct(exit_group, "take_profit")
    atr = atr_series(data, int(structure.get("atr_length") or 14)) if structure else None
    atr_mult = float(structure.get("atr_mult") or 1.1) if structure else 1.1
    rr_ratio = float(structure.get("rr_ratio") or 2.0) if structure else 2.0

    entry = pd.Series(0, index=data.index, dtype=int)
    force_flat = pd.Series(False, index=data.index, dtype=bool)
    flat_reason = pd.Series("", index=data.index, dtype=object)
    stop = pd.Series(np.nan, index=data.index, dtype=float)
    take = pd.Series(np.nan, index=data.index, dtype=float)

    in_position = False
    side = 0
    entry_price = 0.0
    traded_day = None
    closes = data["Close"].astype(float)
    highs = data["High"].astype(float)
    lows = data["Low"].astype(float)

    for i in range(len(data)):
        price = float(closes.iloc[i])
        high = float(highs.iloc[i])
        low = float(lows.iloc[i])
        day = days.iloc[i] if days is not None else None

        if one_trade_per_day and traded_day is not None and day != traded_day:
            traded_day = None

        if in_position and bool(close_mask.iloc[i]):
            force_flat.iloc[i] = True
            flat_reason.iloc[i] = "Session"
            in_position = False
            side = 0
            entry_price = 0.0

        if in_position and _indicator_exit_only(
            exit_group, i, side, entry_price, price, exit_cache
        ):
            force_flat.iloc[i] = True
            flat_reason.iloc[i] = "Signal"
            in_position = False
            side = 0
            entry_price = 0.0

        if not in_position:
            can_trade = (not one_trade_per_day) or (traded_day != day)
            side_to_open = 0
            if can_trade and long_entry is not None and bool(long_entry.iloc[i]):
                side_to_open = 1
            elif can_trade and short_entry is not None and bool(short_entry.iloc[i]):
                side_to_open = -1

            if side_to_open != 0:
                entry.iloc[i] = side_to_open
                in_position = True
                side = side_to_open
                entry_price = price
                if structure is not None and atr is not None:
                    atr_i = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else 0.0
                    sl, tp = _structure_levels(
                        side_to_open, price, high, low, atr_i, atr_mult, rr_ratio
                    )
                    if sl != 0:
                        stop.iloc[i] = sl
                        take.iloc[i] = tp
                else:
                    sl, tp = _pct_levels(side_to_open, price, stop_pct, take_pct)
                    stop.iloc[i] = sl
                    take.iloc[i] = tp
                if one_trade_per_day:
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


def generate_position_signals(
    data: pd.DataFrame,
    entry_group: dict,
    exit_group: dict,
    direction: str = "long",
    entry_short_group: dict | None = None,
    trade_session: str = "",
    close_session: str = "",
    timezone: str = "Europe/Madrid",
    one_trade_per_day: bool = False,
) -> pd.Series:
    """Legacy held-position series (approx) built from the signal frame."""
    frame = generate_signal_frame(
        data,
        entry_group,
        exit_group,
        direction=direction,
        entry_short_group=entry_short_group,
        trade_session=trade_session,
        close_session=close_session,
        timezone=timezone,
        one_trade_per_day=one_trade_per_day,
    )
    position = 0
    entry_sl = entry_tp = 0.0
    out: list[int] = []
    highs = data["High"].astype(float)
    lows = data["Low"].astype(float)

    for i in range(len(data)):
        if position != 0 and bool(frame["force_flat"].iloc[i]):
            position = 0
            entry_sl = entry_tp = 0.0

        if position == 1:
            if entry_sl and float(lows.iloc[i]) <= entry_sl:
                position = 0
                entry_sl = entry_tp = 0.0
            elif entry_tp and float(highs.iloc[i]) >= entry_tp:
                position = 0
                entry_sl = entry_tp = 0.0
        elif position == -1:
            if entry_sl and float(highs.iloc[i]) >= entry_sl:
                position = 0
                entry_sl = entry_tp = 0.0
            elif entry_tp and float(lows.iloc[i]) <= entry_tp:
                position = 0
                entry_sl = entry_tp = 0.0

        e = int(frame["entry"].iloc[i])
        if position == 0 and e != 0:
            position = e
            entry_sl = float(frame["stop"].iloc[i]) if pd.notna(frame["stop"].iloc[i]) else 0.0
            entry_tp = float(frame["take"].iloc[i]) if pd.notna(frame["take"].iloc[i]) else 0.0
        out.append(position)

    return pd.Series(out, index=data.index, dtype=int)
