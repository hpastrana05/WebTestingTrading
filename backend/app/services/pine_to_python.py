"""Generate a runnable Strategy Python module from an imported StrategyConfig."""

from __future__ import annotations

import json
import re
from typing import Any

from app.schemas import StrategyConfig


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        slug = "imported"
    if slug[0].isdigit():
        slug = f"s_{slug}"
    return slug[:48]


def _class_name(slug: str) -> str:
    parts = [p for p in slug.split("_") if p]
    name = "".join(p[:1].upper() + p[1:] for p in parts) or "ImportedStrategy"
    if not name.endswith("Strategy"):
        name = f"{name}Strategy"
    return name


def generate_python_strategy(config: StrategyConfig, *, strategy_id: str | None = None) -> dict[str, str]:
    """
    Emit a Python module that wraps the converted rule tree via ConfigStrategy.

    Best-effort fidelity (same as Creator import), but executable by the backtester.
    """
    slug = _slug(config.name)
    sid = strategy_id or f"gen_{slug}"
    class_name = _class_name(slug)

    payload = config.model_dump()
    payload["id"] = sid
    config_literal = json.dumps(payload, indent=4)

    lines = [
        "# TRADING_LAB_GENERATED",
        '"""',
        "Auto-generated from Pine Script import (best-effort).",
        "",
        f"Strategy: {config.name}",
        f"Direction: {config.direction}",
        f"Ticker hint: {config.yahoo_ticker} · {config.interval} · {config.period}",
        "",
        "Embeds the Strategy Creator rule tree and runs it through the same rule",
        "engine as hand-made configs. NOT a full Pine interpreter — review first.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import json",
        "",
        "import pandas as pd",
        "",
        "from app.schemas import StrategyConfig",
        "from app.strategies.base import Strategy",
        "from app.strategies.config_strategy import ConfigStrategy",
        "",
        "",
        "_CONFIG = json.loads(r\"\"\"",
        config_literal,
        "\"\"\")",
        "",
        "",
        f"class {class_name}(Strategy):",
        '    """Generated wrapper around an imported Pine → Creator config."""',
        "",
        f"    id = {sid!r}",
        f"    name = {config.name!r}",
        "    description = (",
        f'        "Generated from Pine import · {config.direction} · "',
        f'        "{config.yahoo_ticker} · {config.interval}"',
        "    )",
        f"    direction = {config.direction!r}",
        "    parameters: dict = {}",
        "",
        "    def __init__(self) -> None:",
        "        self._inner = ConfigStrategy(StrategyConfig(**_CONFIG))",
        "        self.parameters = self._inner.parameters",
        "        self.direction = self._inner.direction",
        "        self.name = self._inner.name",
        "        self.description = self._inner.description",
        "",
        "    def generate_signals(self, data: pd.DataFrame, params: dict | None = None) -> pd.Series:",
        "        return self._inner.generate_signals(data, params)",
        "",
        "    def generate_signal_frame(self, data: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:",
        "        return self._inner.generate_signal_frame(data, params)",
        "",
        "",
        "def build() -> Strategy:",
        f"    return {class_name}()",
        "",
    ]

    return {
        "strategy_id": sid,
        "class_name": class_name,
        "filename": f"{sid}.py",
        "python_code": "\n".join(lines),
    }


def generate_from_import_result(config: StrategyConfig) -> dict[str, Any]:
    return generate_python_strategy(config)
