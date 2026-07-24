import json
import uuid
from pathlib import Path

from app.config import settings
from app.schemas import AlertRule, AlertRuleUpdate, StrategyConfig, StrategyConfigUpdate


def _data_dir() -> Path:
    path = Path(settings.data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(name: str) -> list[dict]:
    path = _data_dir() / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(name: str, rows: list[dict]) -> None:
    (_data_dir() / name).write_text(json.dumps(rows, indent=2), encoding="utf-8")


# --- Alert rules ---

def list_alert_rules() -> list[AlertRule]:
    return [AlertRule(**rule) for rule in _read_json("alert_rules.json")]


def get_alert_rule(rule_id: str) -> AlertRule:
    for rule in list_alert_rules():
        if rule.id == rule_id:
            return rule
    raise KeyError(f"Alert rule not found: {rule_id}")


def create_alert_rule(rule: AlertRule) -> AlertRule:
    rules = _read_json("alert_rules.json")
    stored = rule.model_dump()
    stored["id"] = str(uuid.uuid4())
    rules.append(stored)
    _write_json("alert_rules.json", rules)
    return AlertRule(**stored)


def update_alert_rule(rule_id: str, update: AlertRuleUpdate) -> AlertRule:
    rules = _read_json("alert_rules.json")
    for index, rule in enumerate(rules):
        if rule.get("id") == rule_id:
            patched = {**rule, **update.model_dump(exclude_none=True)}
            rules[index] = patched
            _write_json("alert_rules.json", rules)
            return AlertRule(**patched)
    raise KeyError(f"Alert rule not found: {rule_id}")


def delete_alert_rule(rule_id: str) -> None:
    rules = _read_json("alert_rules.json")
    filtered = [rule for rule in rules if rule.get("id") != rule_id]
    if len(filtered) == len(rules):
        raise KeyError(f"Alert rule not found: {rule_id}")
    _write_json("alert_rules.json", filtered)
    clear_alert_notify_state(rule_id)


# --- Alert notify dedupe (avoid re-sending the same bar transition) ---

def get_alert_notify_fingerprints() -> dict[str, str]:
    path = _data_dir() / "alert_notify_state.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    return {}


def set_alert_notify_fingerprint(rule_id: str, fingerprint: str) -> None:
    state = get_alert_notify_fingerprints()
    state[rule_id] = fingerprint
    (_data_dir() / "alert_notify_state.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )


def clear_alert_notify_state(rule_id: str) -> None:
    state = get_alert_notify_fingerprints()
    if rule_id in state:
        del state[rule_id]
        (_data_dir() / "alert_notify_state.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )


# --- Custom strategy configs ---

def list_strategy_configs() -> list[StrategyConfig]:
    return [StrategyConfig(**row) for row in _read_json("strategies.json")]


def get_strategy_config(strategy_id: str) -> StrategyConfig:
    for row in _read_json("strategies.json"):
        if row.get("id") == strategy_id:
            return StrategyConfig(**row)
    raise KeyError(f"Strategy config not found: {strategy_id}")


def create_strategy_config(config: StrategyConfig) -> StrategyConfig:
    rows = _read_json("strategies.json")
    stored = config.model_dump()
    stored["id"] = str(uuid.uuid4())
    rows.append(stored)
    _write_json("strategies.json", rows)
    return StrategyConfig(**stored)


def update_strategy_config(strategy_id: str, update: StrategyConfigUpdate) -> StrategyConfig:
    rows = _read_json("strategies.json")
    for index, row in enumerate(rows):
        if row.get("id") == strategy_id:
            patched = {**row, **update.model_dump(exclude_none=True)}
            rows[index] = patched
            _write_json("strategies.json", rows)
            return StrategyConfig(**patched)
    raise KeyError(f"Strategy config not found: {strategy_id}")


def delete_strategy_config(strategy_id: str) -> None:
    rows = _read_json("strategies.json")
    filtered = [row for row in rows if row.get("id") != strategy_id]
    if len(filtered) == len(rows):
        raise KeyError(f"Strategy config not found: {strategy_id}")
    _write_json("strategies.json", filtered)
