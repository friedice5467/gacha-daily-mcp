from __future__ import annotations

import time

import pytest

from src.safety.emergency import EmergencyStop, EmergencyStopError
from src.safety.guards import (
    BoundsChecker,
    BoundsError,
    CurrencyGuard,
    CurrencyGuardTriggered,
    UnknownScreenGuard,
    UnknownScreenGuardTriggered,
)
from src.safety.rate_limiter import RateLimiter


async def test_rate_limiter_allows_burst() -> None:
    rl = RateLimiter(max_per_minute=60)
    for _ in range(10):
        await rl.acquire()


async def test_rate_limiter_tracks_tokens() -> None:
    rl = RateLimiter(max_per_minute=10)
    initial = rl.available
    await rl.acquire()
    assert rl.available < initial


def test_bounds_checker_valid() -> None:
    BoundsChecker.check_point(0.0, 0.0)
    BoundsChecker.check_point(1.0, 1.0)
    BoundsChecker.check_point(0.5, 0.5)


def test_bounds_checker_invalid() -> None:
    with pytest.raises(BoundsError):
        BoundsChecker.check_point(-0.1, 0.5)
    with pytest.raises(BoundsError):
        BoundsChecker.check_point(0.5, 1.1)


def test_bounds_checker_tap_tool() -> None:
    BoundsChecker.check_tool_call("tap", {"x": 0.5, "y": 0.5})
    with pytest.raises(BoundsError):
        BoundsChecker.check_tool_call("tap", {"x": 1.5, "y": 0.5})


def test_bounds_checker_swipe_tool() -> None:
    BoundsChecker.check_tool_call("swipe", {
        "start_x": 0.1, "start_y": 0.5, "end_x": 0.9, "end_y": 0.5
    })
    with pytest.raises(BoundsError):
        BoundsChecker.check_tool_call("swipe", {
            "start_x": 0.1, "start_y": 0.5, "end_x": 1.5, "end_y": 0.5
        })


def test_currency_guard_safe_scene() -> None:
    guard = CurrencyGuard()
    guard.check({"screen": "main_menu", "state": {"stamina": 100}})


def test_currency_guard_triggers() -> None:
    guard = CurrencyGuard()
    with pytest.raises(CurrencyGuardTriggered):
        guard.check({"screen": "shop", "state": {"premium_currency_dialog": True}})


def test_currency_guard_disabled() -> None:
    guard = CurrencyGuard(enabled=False)
    guard.check({"screen": "shop", "state": {"premium_currency_dialog": True}})


def test_unknown_screen_guard_known() -> None:
    guard = UnknownScreenGuard()
    guard.check({"screen": "main_menu", "confidence": 0.9})


def test_unknown_screen_guard_unknown() -> None:
    guard = UnknownScreenGuard()
    with pytest.raises(UnknownScreenGuardTriggered):
        guard.check({"screen": "unknown", "confidence": 0.1})


def test_unknown_screen_guard_low_confidence() -> None:
    guard = UnknownScreenGuard()
    with pytest.raises(UnknownScreenGuardTriggered):
        guard.check({"screen": "maybe_menu", "confidence": 0.2})


def test_unknown_screen_guard_disabled() -> None:
    guard = UnknownScreenGuard(enabled=False)
    guard.check({"screen": "unknown", "confidence": 0.0})


async def test_emergency_stop() -> None:
    stop = EmergencyStop()
    assert not stop.is_stopped
    stop.trigger()
    assert stop.is_stopped
    with pytest.raises(EmergencyStopError):
        await stop.check()
    stop.reset()
    assert not stop.is_stopped
    await stop.check()
