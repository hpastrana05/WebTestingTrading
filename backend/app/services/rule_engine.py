"""Compute pandas-ta indicators and evaluate nested entry/exit rule trees."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pandas_ta as ta

from app.services.indicator_catalog import get_indicator


def compute_indicator(
    data: pd.DataFrame,
    indicator_id: str,
    params: dict[str, Any],
    output: str,
) -> pd.Series:
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


def resolve_operand(data: pd.DataFrame, operand: dict) -> pd.Series:
    kind = operand.get("kind")
    if kind == "price":
        field = operand.get("field", "Close")
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
        )

    raise ValueError(f"Unknown operand kind: {kind}")


def evaluate_condition(data: pd.DataFrame, condition: dict) -> pd.Series:
    left = resolve_operand(data, condition["left"])
    right = resolve_operand(data, condition["right"])
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


def evaluate_group(data: pd.DataFrame, group: dict) -> pd.Series:
    """Recursively evaluate a group of conditions with ALL/ANY logic."""
    children = group.get("children") or []
    logic = (group.get("logic") or "all").lower()

    if not children:
        return pd.Series(False, index=data.index)

    masks: list[pd.Series] = []
    for child in children:
        child_type = child.get("type", "condition")
        if child_type == "group":
            masks.append(evaluate_group(data, child))
        else:
            masks.append(evaluate_condition(data, child))

    combined = masks[0]
    for mask in masks[1:]:
        if logic in ("all", "and"):
            combined = combined & mask
        else:
            combined = combined | mask

    return combined.fillna(False)


def generate_position_signals(
    data: pd.DataFrame,
    entry_group: dict,
    exit_group: dict,
) -> pd.Series:
    """
    Long-only position series:
      enter when entry rule is true while flat
      exit when exit rule is true while in position
    """
    entry = evaluate_group(data, entry_group)
    exit_ = evaluate_group(data, exit_group)

    position = 0
    signals = []
    for i in range(len(data)):
        if position == 0 and bool(entry.iloc[i]):
            position = 1
        elif position == 1 and bool(exit_.iloc[i]):
            position = 0
        signals.append(position)

    return pd.Series(signals, index=data.index, dtype=int)
