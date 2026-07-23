"""
Best-effort Pine Script → StrategyConfig converter.

This is NOT a full Pine interpreter. It extracts common patterns we support
in the Strategy Creator (indicators, crosses, sessions, ATR/R:R, long/short).
Unsupported logic is reported in `warnings`.
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas import Operand, RuleNode, StrategyConfig, _empty_group


def _strip_comments(code: str) -> str:
    # Remove // line comments (keep strings roughly intact for simplicity)
    lines = []
    for line in code.splitlines():
        if "//" in line:
            in_str = False
            out = []
            i = 0
            while i < len(line):
                ch = line[i]
                if ch == '"' and (i == 0 or line[i - 1] != "\\"):
                    in_str = not in_str
                    out.append(ch)
                elif not in_str and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    break
                else:
                    out.append(ch)
                i += 1
            lines.append("".join(out))
        else:
            lines.append(line)
    return "\n".join(lines)


def _first_match(pattern: str, text: str, flags: int = 0) -> re.Match[str] | None:
    return re.search(pattern, text, flags)


def _all_assigns(code: str) -> dict[str, str]:
    """Map simple `name = expr` assignments (last wins)."""
    assigns: dict[str, str] = {}
    for match in re.finditer(
        r"^(?:(?:var|const)\s+)?(?:(?:int|float|bool|string|color|label|line|box|table|array|matrix|map)\s+)?"
        r"([A-Za-z_][\w]*)\s*=\s*(.+)$",
        code,
        flags=re.MULTILINE,
    ):
        name = match.group(1)
        expr = match.group(2).strip()
        if name in ("if", "for", "while", "switch", "type", "method", "import", "export"):
            continue
        # Skip Pine reassignment :=
        if match.group(0).find(":=") != -1:
            continue
        assigns[name] = expr
    return assigns


def _parse_number(text: str, default: float | None = None) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", text or "")
    if not match:
        return default
    try:
        return float(match.group(0))
    except ValueError:
        return default


def _resolve_numeric(expr: str, assigns: dict[str, str], default: float) -> float:
    """Resolve a Pine number or input.int/float / variable to a float."""
    expr = (expr or "").strip()
    if not expr:
        return default
    if re.fullmatch(r"-?\d+(?:\.\d+)?", expr):
        return float(expr)
    if expr in assigns:
        return _resolve_numeric(assigns[expr], assigns, default)
    # input.int(20, "…") / input.float(1.1, …)
    m = re.match(r"input\.(?:int|float)\s*\(\s*(-?\d+(?:\.\d+)?)", expr)
    if m:
        return float(m.group(1))
    return _parse_number(expr, default) if _parse_number(expr, None) is not None else default


def _indicator_operand(indicator: str, params: dict[str, Any], output: str) -> Operand:
    return Operand(kind="indicator", indicator=indicator, params=params, output=output)


def _price_operand(field: str = "Close") -> Operand:
    return Operand(kind="price", field=field)


def _value_operand(value: float) -> Operand:
    return Operand(kind="value", value=value)


def _condition(
    left: Operand,
    operator: str,
    right: Operand,
    right_scale: float = 1.0,
) -> RuleNode:
    return RuleNode(
        type="condition",
        left=left,
        operator=operator,
        right=right,
        right_scale=right_scale,
    )


def _resolve_indicator_expr(
    expr: str,
    assigns: dict[str, str],
    warnings: list[str],
    _depth: int = 0,
) -> Operand | None:
    """Resolve an expression to an Operand when possible."""
    if _depth > 12:
        warnings.append(f"Too deep while resolving: {expr[:60]}")
        return None

    expr = expr.strip().rstrip(",;")
    # Variable reference
    if re.fullmatch(r"[A-Za-z_][\w]*", expr):
        if expr in ("close", "open", "high", "low", "volume", "hlc3"):
            field = {
                "close": "Close",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
                "hlc3": "HLC3",
            }[expr]
            return _price_operand(field)
        if expr in assigns:
            return _resolve_indicator_expr(assigns[expr], assigns, warnings, _depth + 1)
        warnings.append(f"Unknown variable '{expr}' — skipped.")
        return None

    # Numeric literal / input.*
    if re.fullmatch(r"-?\d+(?:\.\d+)?", expr) or expr.startswith("input."):
        return _value_operand(_resolve_numeric(expr, assigns, 0.0))

    # ta.ema(close, 20) / ta.vwap(...)
    m = re.match(r"ta\.(ema|sma|wma|rsi|atr|vwap|macd|mom|roc)\s*\((.*)\)\s*$", expr, re.I)
    if m:
        fn = m.group(1).lower()
        args = [a.strip() for a in _split_args(m.group(2))]
        if fn == "vwap":
            return _indicator_operand("vwap", {}, "VWAP")
        if fn in ("ema", "sma", "wma", "rsi", "atr", "mom", "roc"):
            length_src = args[1] if len(args) > 1 else (args[0] if args else "14")
            # For atr(14) the only arg is length; for ema(close, len) it's args[1]
            if fn == "atr" and len(args) == 1:
                length_src = args[0]
            length = int(_resolve_numeric(length_src, assigns, 14))
            # Range SMA: ta.sma(high-low, n) already handled below; if source is barRange var
            if fn == "sma" and args:
                src = args[0]
                src_resolved = assigns.get(src, src)
                if re.search(r"high\s*-\s*low", src_resolved, re.I):
                    return _indicator_operand(
                        "range_sma", {"length": length}, "RANGE_SMA"
                    )
            outputs = {
                "ema": "EMA",
                "sma": "SMA",
                "wma": "WMA",
                "rsi": "RSI",
                "atr": "ATR",
                "mom": "MOM",
                "roc": "ROC",
            }
            return _indicator_operand(fn, {"length": length}, outputs[fn])
        if fn == "macd":
            fast = int(_resolve_numeric(args[1] if len(args) > 1 else "12", assigns, 12))
            slow = int(_resolve_numeric(args[2] if len(args) > 2 else "26", assigns, 26))
            signal = int(_resolve_numeric(args[3] if len(args) > 3 else "9", assigns, 9))
            return _indicator_operand(
                "macd", {"fast": fast, "slow": slow, "signal": signal}, "MACD"
            )

    # high - low  → BarRange
    if re.fullmatch(r"high\s*-\s*low", expr, re.I):
        return _price_operand("BarRange")

    # ta.sma(high - low, 15)
    m = re.match(r"ta\.sma\s*\(\s*(.+?)\s*,\s*(.+?)\s*\)\s*$", expr, re.I)
    if m:
        inner = m.group(1).strip()
        length = int(_resolve_numeric(m.group(2), assigns, 15))
        inner_src = assigns.get(inner, inner) if re.fullmatch(r"[A-Za-z_][\w]*", inner) else inner
        if re.search(r"high\s*-\s*low", inner_src, re.I):
            return _indicator_operand("range_sma", {"length": length}, "RANGE_SMA")
        return _indicator_operand("sma", {"length": length}, "SMA")

    warnings.append(f"Could not map expression: {expr[:80]}")
    return None


def _split_args(argstr: str) -> list[str]:
    args: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in argstr:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append("".join(current).strip())
    return [a for a in args if a]


def _parse_bool_condition(
    expr: str,
    assigns: dict[str, str],
    warnings: list[str],
) -> list[RuleNode]:
    """
    Split `a and b and c` into condition nodes.
    Handles ta.crossover / ta.crossunder / comparisons / scaled compares.
    """
    expr = expr.strip()
    # Expand one level of variable aliases that are pure and-chains
    if re.fullmatch(r"[A-Za-z_][\w]*", expr) and expr in assigns:
        expr = assigns[expr]

    parts = re.split(r"\s+and\s+", expr, flags=re.I)
    conditions: list[RuleNode] = []

    for part in parts:
        part = part.strip()
        # Unwrap a single outer (...) pair only
        if part.startswith("(") and part.endswith(")"):
            depth = 0
            balanced = True
            for i, ch in enumerate(part):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and i != len(part) - 1:
                        balanced = False
                        break
            if balanced and depth == 0:
                part = part[1:-1].strip()
        if not part:
            continue

        # Skip strategy.position_size / tradedToday / session helpers — handled elsewhere
        if re.search(
            r"strategy\.position_size|tradedToday|inTradeWindow|inCloseWindow|not\s+na\s*\(\s*time",
            part,
            re.I,
        ):
            continue
        if re.fullmatch(r"not\s+[A-Za-z_][\w]*", part, re.I):
            continue

        # ta.crossover(a, b)
        m = re.match(r"ta\.crossover\s*\(\s*(.+?)\s*,\s*(.+?)\s*\)\s*$", part, re.I)
        if m:
            left = _resolve_indicator_expr(m.group(1), assigns, warnings)
            right = _resolve_indicator_expr(m.group(2), assigns, warnings)
            if left and right:
                conditions.append(_condition(left, "cross_above", right))
            continue

        m = re.match(r"ta\.crossunder\s*\(\s*(.+?)\s*,\s*(.+?)\s*\)\s*$", part, re.I)
        if m:
            left = _resolve_indicator_expr(m.group(1), assigns, warnings)
            right = _resolve_indicator_expr(m.group(2), assigns, warnings)
            if left and right:
                conditions.append(_condition(left, "cross_below", right))
            continue

        # a > b * 1.1   or  a > b * multVar  or  a > b
        m = re.match(
            r"(.+?)\s*(>=|<=|==|>|<)\s*(.+)\s*$",
            part,
        )
        if m:
            left = _resolve_indicator_expr(m.group(1), assigns, warnings)
            op = m.group(2)
            right_expr = m.group(3).strip()
            scale = 1.0
            # right * scale (number or input/var resolving to number)
            m2 = re.match(r"(.+?)\s*\*\s*(.+)$", right_expr)
            if m2:
                right_expr = m2.group(1).strip()
                scale = _resolve_numeric(m2.group(2).strip(), assigns, 1.0)
            right = _resolve_indicator_expr(right_expr, assigns, warnings)
            op_map = {">": ">", "<": "<", ">=": ">=", "<=": "<=", "==": "=="}
            if left and right:
                conditions.append(_condition(left, op_map[op], right, scale))
            continue

        # Bare boolean var like hasImpulse
        if re.fullmatch(r"[A-Za-z_][\w]*", part) and part in assigns:
            nested = _parse_bool_condition(assigns[part], assigns, warnings)
            conditions.extend(nested)
            continue

        warnings.append(f"Skipped condition fragment: {part[:100]}")

    return conditions


def convert_pinescript(code: str) -> dict[str, Any]:
    """
    Convert Pine Script source into a StrategyConfig draft + warnings.
    """
    warnings: list[str] = []
    if not code or not code.strip():
        raise ValueError("Pine Script code is empty")

    raw = code
    text = _strip_comments(code)
    assigns = _all_assigns(text)

    # --- Name ---
    name = "Imported Pine Strategy"
    m = _first_match(r'strategy\s*\(\s*"([^"]+)"', text)
    if m:
        name = m.group(1).strip()

    # --- Direction ---
    has_long = bool(
        re.search(r"strategy\.entry\s*\([^)]*strategy\.long", text, re.I)
        or re.search(r"strategy\.long", text)
    )
    has_short = bool(
        re.search(r"strategy\.entry\s*\([^)]*strategy\.short", text, re.I)
        or re.search(r"strategy\.short", text)
    )
    if has_long and has_short:
        direction: str = "both"
    elif has_short and not has_long:
        direction = "short"
    else:
        direction = "long"

    # --- Sessions ---
    trade_session = ""
    close_session = ""
    timezone = "Europe/Madrid"

    # input.session("1545-1930", ...)
    sessions = re.findall(
        r'input\.session\s*\(\s*"(\d{3,4}-\d{3,4}|\d{2}:\d{2}-\d{2}:\d{2})"',
        text,
    )
    # Heuristic: first session = trade, second = close if two exist
    if len(sessions) >= 1:
        trade_session = sessions[0].replace(":", "")
    if len(sessions) >= 2:
        close_session = sessions[1].replace(":", "")

    # Named variables tradeWindow / closeWindow
    for var, target in (("tradeWindow", "trade"), ("closeWindow", "close")):
        if var in assigns:
            sm = re.search(r'input\.session\s*\(\s*"([^"]+)"', assigns[var])
            if sm:
                val = sm.group(1).replace(":", "")
                if target == "trade":
                    trade_session = val
                else:
                    close_session = val

    tz_m = _first_match(r'input\.string\s*\(\s*"(Europe/[^"]+|UTC|America/[^"]+)"', text)
    if tz_m:
        timezone = tz_m.group(1)
    elif "Europe/Madrid" in text:
        timezone = "Europe/Madrid"

    # --- One trade per day ---
    one_trade = bool(
        re.search(r"tradedToday", text) or re.search(r"once\s*per\s*day", text, re.I)
    )

    # --- ATR / R:R structure exit ---
    atr_length = 14
    atr_mult = 1.1
    rr_ratio = 2.0
    found_structure = False

    atr_m = _first_match(r"ta\.atr\s*\(\s*(\d+)\s*\)", text)
    if atr_m:
        atr_length = int(atr_m.group(1))

    # atr14 * 1.1  or atr * atr_mult
    mult_m = _first_match(r"atr\w*\s*\*\s*(\d+(?:\.\d+)?)", text, re.I)
    if mult_m:
        atr_mult = float(mult_m.group(1))
        found_structure = True

    rr_m = (
        _first_match(r"rrRatio\s*=\s*input\.float\s*\(\s*(\d+(?:\.\d+)?)", text)
        or _first_match(r"slDist\s*\*\s*rrRatio", text)
        or _first_match(r"rrRatio\s*=\s*(\d+(?:\.\d+)?)", text)
    )
    if "rrRatio" in assigns:
        rr_val = _parse_number(assigns["rrRatio"], None)
        if rr_val is None and "input.float" in assigns["rrRatio"]:
            rr_val = _parse_number(assigns["rrRatio"], 2.0)
        if rr_val is not None:
            rr_ratio = float(rr_val)
            found_structure = True
    elif rr_m and rr_m.lastindex:
        maybe = _parse_number(rr_m.group(1), None)
        if maybe is not None:
            rr_ratio = float(maybe)
            found_structure = True

    if re.search(r"strategy\.exit\s*\([^)]*stop\s*=", text, re.I):
        found_structure = True

    # --- Entry conditions ---
    long_children: list[RuleNode] = []
    short_children: list[RuleNode] = []

    long_keys = [k for k in assigns if re.search(r"long", k, re.I)]
    short_keys = [k for k in assigns if re.search(r"short", k, re.I)]

    # Prefer *Cond / *Entry / *Signal names; otherwise first long*/short* bool-like assign
    def _pick_entry_key(keys: list[str]) -> str | None:
        preferred = [
            k
            for k in keys
            if re.search(r"cond|entry|signal|setup", k, re.I)
            or k.lower() in ("bull", "bear", "long", "short")
        ]
        return (preferred or keys or [None])[0]

    long_key = _pick_entry_key(long_keys)
    short_key = _pick_entry_key(short_keys)
    if long_key:
        long_children = _parse_bool_condition(assigns[long_key], assigns, warnings)
    if short_key:
        short_children = _parse_bool_condition(assigns[short_key], assigns, warnings)

    # Fallback: look for crossover/crossunder usage directly
    if not long_children and not short_children:
        for match in re.finditer(
            r"ta\.crossover\s*\(\s*([^,]+)\s*,\s*([^)]+)\)", text, re.I
        ):
            left = _resolve_indicator_expr(match.group(1), assigns, warnings)
            right = _resolve_indicator_expr(match.group(2), assigns, warnings)
            if left and right:
                long_children.append(_condition(left, "cross_above", right))
        for match in re.finditer(
            r"ta\.crossunder\s*\(\s*([^,]+)\s*,\s*([^)]+)\)", text, re.I
        ):
            left = _resolve_indicator_expr(match.group(1), assigns, warnings)
            right = _resolve_indicator_expr(match.group(2), assigns, warnings)
            if left and right:
                short_children.append(_condition(left, "cross_below", right))

    if not long_children and direction in ("long", "both"):
        warnings.append(
            "Could not detect long entry rules — add them manually in the Strategy Creator."
        )
        # Provide a placeholder so the form can be saved after edit
        long_children = [
            _condition(_price_operand("Close"), "cross_above", _indicator_operand("vwap", {}, "VWAP"))
        ]
        warnings.append("Added a placeholder Close crosses above VWAP long rule.")

    if direction == "both" and not short_children:
        warnings.append(
            "Could not detect short entry rules — add them manually in the Strategy Creator."
        )
        short_children = [
            _condition(_price_operand("Close"), "cross_below", _indicator_operand("vwap", {}, "VWAP"))
        ]
        warnings.append("Added a placeholder Close crosses below VWAP short rule.")

    if direction == "short" and not short_children and long_children:
        short_children = long_children
        long_children = []

    entry = RuleNode(type="group", logic="all", children=long_children or [])
    entry_short = RuleNode(type="group", logic="all", children=short_children or [])
    if direction == "short":
        entry = RuleNode(type="group", logic="all", children=short_children or long_children)
        entry_short = _empty_group("all")

    exit_children: list[RuleNode] = []
    if found_structure:
        exit_children.append(
            RuleNode(
                type="risk",
                risk="structure_atr",
                atr_length=atr_length,
                atr_mult=atr_mult,
                rr_ratio=rr_ratio,
            )
        )
    else:
        # Default mild exits so the config is valid
        exit_children.append(RuleNode(type="risk", risk="stop_loss", pct=2.0))
        exit_children.append(RuleNode(type="risk", risk="take_profit", pct=4.0))
        warnings.append(
            "No ATR/R:R exit detected — added default 2% SL / 4% TP. Adjust in the creator."
        )

    exit_group = RuleNode(type="group", logic="any", children=exit_children)

    # Interval / ticker hints
    interval = "5m" if re.search(r"intraday|session|1545|15:45", text, re.I) else "1d"
    period = "5d" if interval.endswith("m") or interval.endswith("h") else "1y"
    yahoo = "QQQ"
    if re.search(r"NASDAQ|NAS100|QQQ|IXIC", raw, re.I):
        yahoo = "QQQ"

    config = StrategyConfig(
        name=name[:120],
        broker_ticker="",
        yahoo_ticker=yahoo,
        interval=interval,
        period=period,
        direction=direction,  # type: ignore[arg-type]
        trade_session=trade_session,
        close_session=close_session,
        timezone=timezone,
        one_trade_per_day=one_trade,
        entry=entry,
        entry_short=entry_short,
        exit=exit_group,
    )

    warnings.insert(
        0,
        "Best-effort import only — review every rule in the Strategy Creator before backtesting.",
    )
    if "pine_tradingview" not in "".join(warnings):
        pass

    # Deduplicate warnings
    uniq: list[str] = []
    for w in warnings:
        if w not in uniq:
            uniq.append(w)

    return {"config": config, "warnings": uniq}
