from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RuleError(Exception):
    pass


class Condition(BaseModel):
    field: str
    op: str
    value: Any = None


def evaluate(scene: dict[str, Any], conditions: list[dict[str, Any]]) -> bool:
    for cond in conditions:
        if "any" in cond:
            if not _evaluate_any(scene, cond["any"]):
                return False
        else:
            parsed = Condition(**cond)
            if not _evaluate_one(scene, parsed):
                return False
    return True


def _evaluate_any(scene: dict[str, Any], conditions: list[dict[str, Any]]) -> bool:
    return any(_evaluate_one(scene, Condition(**c)) for c in conditions)


def _evaluate_one(scene: dict[str, Any], cond: Condition) -> bool:
    if cond.field == "always":
        return True

    actual = _resolve_field(scene, cond.field)
    op = cond.op

    if op == "exists":
        return actual is not None

    if actual is None:
        return False

    if op == "eq":
        return actual == cond.value
    if op == "neq":
        return actual != cond.value
    if op == "gt":
        return actual > cond.value
    if op == "gte":
        return actual >= cond.value
    if op == "lt":
        return actual < cond.value
    if op == "lte":
        return actual <= cond.value
    if op == "contains":
        return cond.value in actual

    raise RuleError(f"Unknown operator: {op}")


def _resolve_field(scene: dict[str, Any], field: str) -> Any:
    parts = field.split(".")
    current: Any = scene
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current
