"""Extract / apply tunable numeric fields from Strategy Creator rule trees."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _param_meta(value: float | int, *, is_float: bool) -> dict[str, Any]:
    if is_float:
        default = float(value)
        step = 0.1 if abs(default) < 10 else 0.5
        return {
            "type": "float",
            "default": default,
            "min": max(0.01, default * 0.25),
            "max": max(default * 4, default + 5),
            "step": step,
        }
    default = int(value)
    return {
        "type": "int",
        "default": default,
        "min": max(1, default // 4 or 1),
        "max": max(default * 4, default + 20),
        "step": 1,
    }


def _walk_operand(
    operand: dict | None,
    prefix: str,
    params: dict[str, dict],
) -> None:
    if not operand or operand.get("kind") != "indicator":
        return
    for name, raw in (operand.get("params") or {}).items():
        if not isinstance(raw, (int, float)):
            continue
        key = f"{prefix}_{name}"
        params[key] = _param_meta(raw, is_float=isinstance(raw, float) and not float(raw).is_integer())


def _walk_node(node: dict | None, prefix: str, params: dict[str, dict]) -> None:
    if not node:
        return
    ntype = node.get("type")
    if ntype == "condition":
        _walk_operand(node.get("left"), f"{prefix}_L", params)
        _walk_operand(node.get("right"), f"{prefix}_R", params)
        scale = node.get("right_scale")
        if scale is not None and float(scale) != 1.0:
            params[f"{prefix}_scale"] = _param_meta(float(scale), is_float=True)
        return
    if ntype == "risk":
        risk = node.get("risk")
        if risk in ("stop_loss", "take_profit") and node.get("pct") is not None:
            label = "sl_pct" if risk == "stop_loss" else "tp_pct"
            params[f"{prefix}_{label}"] = _param_meta(float(node["pct"]), is_float=True)
        if risk == "structure_atr":
            if node.get("atr_length") is not None:
                params[f"{prefix}_atr_length"] = _param_meta(int(node["atr_length"]), is_float=False)
            if node.get("atr_mult") is not None:
                params[f"{prefix}_atr_mult"] = _param_meta(float(node["atr_mult"]), is_float=True)
            if node.get("rr_ratio") is not None:
                params[f"{prefix}_rr_ratio"] = _param_meta(float(node["rr_ratio"]), is_float=True)
        return
    if ntype == "group":
        for i, child in enumerate(node.get("children") or []):
            _walk_node(child, f"{prefix}{i}", params)


def extract_tunable_parameters(
    entry: dict,
    exit_group: dict,
    entry_short: dict | None = None,
    direction: str = "long",
) -> dict[str, dict]:
    """Build Strategy.parameters-style dict from rule trees."""
    params: dict[str, dict] = {}
    _walk_node(entry, "entry", params)
    if direction == "both" and entry_short:
        _walk_node(entry_short, "short", params)
    _walk_node(exit_group, "exit", params)
    return params


def _apply_operand(operand: dict | None, prefix: str, values: dict[str, Any]) -> None:
    if not operand or operand.get("kind") != "indicator":
        return
    raw_params = dict(operand.get("params") or {})
    changed = False
    for name in list(raw_params.keys()):
        key = f"{prefix}_{name}"
        if key not in values:
            continue
        original = raw_params[name]
        if isinstance(original, bool):
            continue
        if isinstance(original, int) and not isinstance(original, bool):
            raw_params[name] = int(values[key])
        else:
            raw_params[name] = float(values[key])
        changed = True
    if changed:
        operand["params"] = raw_params


def _apply_node(node: dict | None, prefix: str, values: dict[str, Any]) -> None:
    if not node:
        return
    ntype = node.get("type")
    if ntype == "condition":
        _apply_operand(node.get("left"), f"{prefix}_L", values)
        _apply_operand(node.get("right"), f"{prefix}_R", values)
        scale_key = f"{prefix}_scale"
        if scale_key in values:
            node["right_scale"] = float(values[scale_key])
        return
    if ntype == "risk":
        risk = node.get("risk")
        if risk == "stop_loss" and f"{prefix}_sl_pct" in values:
            node["pct"] = float(values[f"{prefix}_sl_pct"])
        if risk == "take_profit" and f"{prefix}_tp_pct" in values:
            node["pct"] = float(values[f"{prefix}_tp_pct"])
        if risk == "structure_atr":
            if f"{prefix}_atr_length" in values:
                node["atr_length"] = int(values[f"{prefix}_atr_length"])
            if f"{prefix}_atr_mult" in values:
                node["atr_mult"] = float(values[f"{prefix}_atr_mult"])
            if f"{prefix}_rr_ratio" in values:
                node["rr_ratio"] = float(values[f"{prefix}_rr_ratio"])
        return
    if ntype == "group":
        for i, child in enumerate(node.get("children") or []):
            _apply_node(child, f"{prefix}{i}", values)


def apply_tunable_parameters(
    entry: dict,
    exit_group: dict,
    values: dict[str, Any],
    entry_short: dict | None = None,
) -> tuple[dict, dict, dict | None]:
    """Return deep-copied rule trees with tuned values applied."""
    entry_c = deepcopy(entry)
    exit_c = deepcopy(exit_group)
    short_c = deepcopy(entry_short) if entry_short is not None else None
    _apply_node(entry_c, "entry", values)
    if short_c is not None:
        _apply_node(short_c, "short", values)
    _apply_node(exit_c, "exit", values)
    return entry_c, exit_c, short_c


def suggest_param_grid(parameters: dict[str, dict], max_values: int = 3) -> dict[str, list]:
    """Small default grid around each parameter's default."""
    grid: dict[str, list] = {}
    for name, meta in parameters.items():
        default = meta["default"]
        lo = meta.get("min", default)
        hi = meta.get("max", default)
        step = meta.get("step") or (1 if meta.get("type") == "int" else 0.1)
        if meta.get("type") == "int":
            candidates = [
                int(default),
                int(max(lo, default - 2 * step)),
                int(min(hi, default + 2 * step)),
            ]
            # Prefer shorter grids for high-cardinality length params when many exist
            values = sorted({int(v) for v in candidates if lo <= v <= hi})
        else:
            candidates = [
                float(default),
                float(max(lo, round(default - 2 * step, 6))),
                float(min(hi, round(default + 2 * step, 6))),
            ]
            values = sorted({round(float(v), 6) for v in candidates if lo <= v <= hi})
        grid[name] = values[:max_values] if len(values) > max_values else values
        if not grid[name]:
            grid[name] = [default]
    return grid
