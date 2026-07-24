"""Load / save auto-generated Python strategies under data/generated_strategies/."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.config import settings
from app.schemas import StrategyConfig
from app.services.pine_to_python import generate_python_strategy
from app.strategies.base import Strategy
from app.strategies.config_strategy import ConfigStrategy

_MARKER = "TRADING_LAB_GENERATED"
_PYTHON_PREFIX = "[Python]"


def generated_dir() -> Path:
    path = Path(settings.data_dir) / "generated_strategies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_id(strategy_id: str) -> str:
    sid = re.sub(r"[^a-zA-Z0-9_]+", "_", strategy_id).strip("_").lower()
    if not sid.startswith("gen_"):
        sid = f"gen_{sid}"
    return sid[:64]


def strip_python_prefix(name: str) -> str:
    clean = (name or "").strip()
    while clean.lower().startswith("[python]"):
        clean = clean[8:].strip()
    return clean


def with_python_prefix(name: str) -> str:
    clean = strip_python_prefix(name)
    return f"{_PYTHON_PREFIX} {clean}" if clean else f"{_PYTHON_PREFIX} Strategy"


def save_generated_strategy(config: StrategyConfig) -> tuple[Path, Strategy, str]:
    """Write generated Python to disk and return (path, instance, source)."""
    named = config.model_copy(update={"name": with_python_prefix(config.name)})
    meta = generate_python_strategy(named, strategy_id=_safe_id(named.id or named.name))
    sid = meta["strategy_id"]
    path = generated_dir() / meta["filename"]
    config_with_id = named.model_copy(update={"id": sid})
    meta = generate_python_strategy(config_with_id, strategy_id=sid)
    path.write_text(meta["python_code"], encoding="utf-8")
    strategy = _load_module(path)
    return path, strategy, meta["python_code"]


def list_generated_strategies() -> list[Strategy]:
    items: list[Strategy] = []
    for path in sorted(generated_dir().glob("*.py")):
        try:
            items.append(_load_module(path))
        except Exception:
            continue
    return items


def get_generated_strategy(strategy_id: str) -> Strategy:
    return _load_module(_find_generated_path(strategy_id))


def _find_generated_path(strategy_id: str) -> Path:
    candidates = [
        generated_dir() / f"{_safe_id(strategy_id)}.py",
        generated_dir() / f"{strategy_id}.py",
        generated_dir() / f"{strategy_id.replace('-', '_')}.py",
    ]
    for path in candidates:
        if path.exists() and path.suffix == ".py":
            return path

    for path in generated_dir().glob("*.py"):
        try:
            strategy = _load_module(path)
        except Exception:
            continue
        if strategy.id == strategy_id or path.stem == strategy_id:
            return path

    raise KeyError(f"Generated strategy not found: {strategy_id}")


def delete_generated_strategy(strategy_id: str) -> None:
    """Remove a generated .py by id or filename stem."""
    _find_generated_path(strategy_id).unlink()


def rename_generated_strategy(strategy_id: str, new_name: str) -> Strategy:
    """Change the display name of a generated Python strategy (id stays the same)."""
    name = strip_python_prefix(new_name)
    if not name:
        raise ValueError("Name is required")
    name = with_python_prefix(name[:120])

    path = _find_generated_path(strategy_id)
    strategy = _load_module(path)

    # Prefer rewriting from the embedded ConfigStrategy config
    inner = getattr(strategy, "_inner", None)
    if isinstance(inner, ConfigStrategy):
        cfg = inner.config.model_copy(update={"name": name, "id": strategy.id})
    else:
        cfg = StrategyConfig(
            id=strategy.id,
            name=name,
            yahoo_ticker="QQQ",
            direction=getattr(strategy, "direction", "long"),
        )

    meta = generate_python_strategy(cfg, strategy_id=strategy.id)
    path.write_text(meta["python_code"], encoding="utf-8")
    return _load_module(path)


def _load_module(path: Path) -> Strategy:
    text = path.read_text(encoding="utf-8")
    if _MARKER not in text:
        raise ValueError(f"Refusing to load non-generated module: {path.name}")

    mod_name = f"trading_lab_generated_{path.stem}"
    spec = importlib.util.spec_from_loader(mod_name, loader=None)
    if spec is None:
        raise ImportError(f"Cannot create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    exec(compile(text, str(path), "exec"), module.__dict__)  # noqa: S102 — trusted generated files only

    if hasattr(module, "build") and callable(module.build):
        strategy = module.build()
        if isinstance(strategy, Strategy):
            strategy.name = with_python_prefix(strategy.name)
            return strategy

    for value in module.__dict__.values():
        if isinstance(value, type) and issubclass(value, Strategy) and value is not Strategy:
            inst = value()
            if isinstance(inst, Strategy):
                inst.name = with_python_prefix(inst.name)
                return inst

    raise ImportError(f"No Strategy found in {path.name}")
