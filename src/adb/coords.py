from __future__ import annotations

from pydantic import BaseModel, field_validator


class ADBError(Exception):
    pass


class OutOfBoundsError(ADBError):
    pass


class NormalizedPoint(BaseModel):
    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def check_bounds(cls, v: float, info) -> float:
        if not 0.0 <= v <= 1.0:
            raise OutOfBoundsError(
                f"Coordinate {info.field_name}={v} out of bounds (must be 0.0–1.0)"
            )
        return v

    def to_pixels(self, width: int, height: int) -> PixelPoint:
        return PixelPoint(x=round(self.x * width), y=round(self.y * height))


class PixelPoint(BaseModel):
    x: int
    y: int

    def to_normalized(self, width: int, height: int) -> NormalizedPoint:
        if width <= 0 or height <= 0:
            raise ADBError(f"Invalid screen dimensions: {width}x{height}")
        return NormalizedPoint(x=self.x / width, y=self.y / height)


class NormalizedSwipe(BaseModel):
    start: NormalizedPoint
    end: NormalizedPoint
    duration_ms: int = 300

    def to_pixels(self, width: int, height: int) -> PixelSwipe:
        return PixelSwipe(
            start=self.start.to_pixels(width, height),
            end=self.end.to_pixels(width, height),
            duration_ms=self.duration_ms,
        )


class PixelSwipe(BaseModel):
    start: PixelPoint
    end: PixelPoint
    duration_ms: int = 300
