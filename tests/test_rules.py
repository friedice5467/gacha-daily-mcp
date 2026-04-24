from __future__ import annotations

import pytest

from src.engine.rules import RuleError, evaluate

SCENE = {
    "screen": "quest_select",
    "elements": [
        {"label": "Auto Battle", "type": "button", "position": [0.72, 0.88]},
        {"label": "Stamina: 47/120", "type": "text", "position": [0.85, 0.04]},
    ],
    "state": {
        "stamina_current": 47,
        "stamina_max": 120,
        "quest_available": True,
        "loading": False,
    },
}


def test_eq_match() -> None:
    assert evaluate(SCENE, [{"field": "screen", "op": "eq", "value": "quest_select"}])


def test_eq_no_match() -> None:
    assert not evaluate(SCENE, [{"field": "screen", "op": "eq", "value": "main_menu"}])


def test_neq() -> None:
    assert evaluate(SCENE, [{"field": "screen", "op": "neq", "value": "main_menu"}])


def test_gt() -> None:
    assert evaluate(SCENE, [{"field": "state.stamina_current", "op": "gt", "value": 30}])
    assert not evaluate(SCENE, [{"field": "state.stamina_current", "op": "gt", "value": 50}])


def test_gte() -> None:
    assert evaluate(SCENE, [{"field": "state.stamina_current", "op": "gte", "value": 47}])
    assert not evaluate(SCENE, [{"field": "state.stamina_current", "op": "gte", "value": 48}])


def test_lt() -> None:
    assert evaluate(SCENE, [{"field": "state.stamina_current", "op": "lt", "value": 50}])


def test_lte() -> None:
    assert evaluate(SCENE, [{"field": "state.stamina_current", "op": "lte", "value": 47}])


def test_contains() -> None:
    assert evaluate(SCENE, [{"field": "screen", "op": "contains", "value": "quest"}])


def test_exists_present() -> None:
    assert evaluate(SCENE, [{"field": "state.stamina_current", "op": "exists"}])


def test_exists_missing() -> None:
    assert not evaluate(SCENE, [{"field": "state.nonexistent", "op": "exists"}])


def test_dot_path_nested() -> None:
    assert evaluate(SCENE, [{"field": "state.quest_available", "op": "eq", "value": True}])


def test_dot_path_missing_returns_false() -> None:
    assert not evaluate(SCENE, [{"field": "state.deep.missing.path", "op": "eq", "value": "x"}])


def test_always_field() -> None:
    assert evaluate(SCENE, [{"field": "always", "op": "eq", "value": True}])


def test_always_with_any_op() -> None:
    assert evaluate(SCENE, [{"field": "always", "op": "gt", "value": 999}])


def test_multiple_conditions_and() -> None:
    conds = [
        {"field": "screen", "op": "eq", "value": "quest_select"},
        {"field": "state.stamina_current", "op": "gte", "value": 30},
    ]
    assert evaluate(SCENE, conds)


def test_multiple_conditions_one_fails() -> None:
    conds = [
        {"field": "screen", "op": "eq", "value": "quest_select"},
        {"field": "state.stamina_current", "op": "gte", "value": 100},
    ]
    assert not evaluate(SCENE, conds)


def test_or_logic() -> None:
    conds = [
        {
            "any": [
                {"field": "screen", "op": "eq", "value": "main_menu"},
                {"field": "screen", "op": "eq", "value": "quest_select"},
            ]
        }
    ]
    assert evaluate(SCENE, conds)


def test_or_logic_none_match() -> None:
    conds = [
        {
            "any": [
                {"field": "screen", "op": "eq", "value": "main_menu"},
                {"field": "screen", "op": "eq", "value": "loading"},
            ]
        }
    ]
    assert not evaluate(SCENE, conds)


def test_empty_conditions() -> None:
    assert evaluate(SCENE, [])


def test_unknown_operator_raises() -> None:
    with pytest.raises(RuleError):
        evaluate(SCENE, [{"field": "screen", "op": "regex", "value": ".*"}])


def test_boolean_eq() -> None:
    assert evaluate(SCENE, [{"field": "state.loading", "op": "eq", "value": False}])
