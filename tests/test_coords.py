from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.adb.coords import (
    ADBError,
    NormalizedPoint,
    NormalizedSwipe,
    OutOfBoundsError,
    PixelPoint,
)


def test_normalized_to_pixels() -> None:
    p = NormalizedPoint(x=0.5, y=0.25)
    px = p.to_pixels(1280, 720)
    assert px.x == 640
    assert px.y == 180


def test_normalized_to_pixels_origin() -> None:
    p = NormalizedPoint(x=0.0, y=0.0)
    px = p.to_pixels(1280, 720)
    assert px.x == 0
    assert px.y == 0


def test_normalized_to_pixels_max() -> None:
    p = NormalizedPoint(x=1.0, y=1.0)
    px = p.to_pixels(1280, 720)
    assert px.x == 1280
    assert px.y == 720


def test_normalized_to_pixels_rounding() -> None:
    p = NormalizedPoint(x=0.333, y=0.666)
    px = p.to_pixels(1280, 720)
    assert px.x == 426
    assert px.y == 480


def test_pixel_to_normalized() -> None:
    px = PixelPoint(x=640, y=360)
    n = px.to_normalized(1280, 720)
    assert n.x == 0.5
    assert n.y == 0.5


def test_out_of_bounds_negative() -> None:
    with pytest.raises((OutOfBoundsError, ValidationError)):
        NormalizedPoint(x=-0.1, y=0.5)


def test_out_of_bounds_over_one() -> None:
    with pytest.raises((OutOfBoundsError, ValidationError)):
        NormalizedPoint(x=0.5, y=1.1)


def test_boundary_values_valid() -> None:
    p0 = NormalizedPoint(x=0.0, y=0.0)
    p1 = NormalizedPoint(x=1.0, y=1.0)
    assert p0.x == 0.0
    assert p1.y == 1.0


def test_pixel_to_normalized_invalid_dimensions() -> None:
    px = PixelPoint(x=100, y=100)
    with pytest.raises(ADBError):
        px.to_normalized(0, 720)


def test_swipe_to_pixels() -> None:
    swipe = NormalizedSwipe(
        start=NormalizedPoint(x=0.2, y=0.5),
        end=NormalizedPoint(x=0.8, y=0.5),
        duration_ms=500,
    )
    ps = swipe.to_pixels(1280, 720)
    assert ps.start.x == 256
    assert ps.start.y == 360
    assert ps.end.x == 1024
    assert ps.end.y == 360
    assert ps.duration_ms == 500


def test_roundtrip_conversion() -> None:
    original = NormalizedPoint(x=0.5, y=0.75)
    px = original.to_pixels(1280, 720)
    back = px.to_normalized(1280, 720)
    assert abs(back.x - original.x) < 0.001
    assert abs(back.y - original.y) < 0.001
