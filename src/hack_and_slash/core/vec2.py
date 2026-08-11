"""Immutable 2D float vector, and the angle helpers the combat code leans on.

A NamedTuple rather than a dataclass: it unpacks (`x, y = v`), compares by value
for free, and stays cheap enough to allocate a few hundred times a tick without
thinking about it. Immutability is the point -- entity positions get replaced,
never mutated in place, so a stale reference can never silently become a live one.
"""

from __future__ import annotations

import math
from typing import NamedTuple

#: Below this a vector counts as zero. Guards every normalise and every division
#: by a length, so a zero-length input returns a defined value instead of raising.
EPSILON = 1e-9


class Vec2(NamedTuple):
    x: float = 0.0
    y: float = 0.0

    # --- arithmetic ----------------------------------------------------------
    def __add__(self, other: "Vec2") -> "Vec2":  # type: ignore[override]
        return Vec2(self.x + other[0], self.y + other[1])

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other[0], self.y - other[1])

    def __mul__(self, scalar: float) -> "Vec2":  # type: ignore[override]
        return Vec2(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> "Vec2":
        return Vec2(self.x / scalar, self.y / scalar)

    def __neg__(self) -> "Vec2":
        return Vec2(-self.x, -self.y)

    # --- measurement ---------------------------------------------------------
    def length_sq(self) -> float:
        """Squared length. Prefer this for comparisons -- no sqrt, exact."""
        return self.x * self.x + self.y * self.y

    def length(self) -> float:
        return math.sqrt(self.length_sq())

    def dot(self, other: "Vec2") -> float:
        return self.x * other[0] + self.y * other[1]

    def distance_to(self, other: "Vec2") -> float:
        return (self - other).length()

    def distance_sq_to(self, other: "Vec2") -> float:
        return (self - other).length_sq()

    def is_zero(self) -> bool:
        return self.length_sq() < EPSILON * EPSILON

    # --- direction -----------------------------------------------------------
    def normalized(self) -> "Vec2":
        """Unit vector, or ZERO if there is no direction to speak of.

        Returning zero rather than raising is deliberate: "the player is not
        pushing a stick" is an ordinary frame, not an error, and every caller
        would otherwise need the same guard.
        """
        length = self.length()
        if length < EPSILON:
            return ZERO
        return Vec2(self.x / length, self.y / length)

    def with_length(self, length: float) -> "Vec2":
        return self.normalized() * length

    def clamped(self, max_length: float) -> "Vec2":
        """Shorten to `max_length` if longer, otherwise leave alone.

        This is what stops diagonal input being 1.41x faster than cardinal input.
        """
        if self.length_sq() <= max_length * max_length:
            return self
        return self.with_length(max_length)

    def angle(self) -> float:
        """Direction in radians, measured the way screen space runs: +x is 0,
        +y is a quarter turn *down*, because y grows downward on a surface."""
        return math.atan2(self.y, self.x)

    def rotated(self, radians: float) -> "Vec2":
        cos_r, sin_r = math.cos(radians), math.sin(radians)
        return Vec2(self.x * cos_r - self.y * sin_r, self.x * sin_r + self.y * cos_r)

    def perpendicular(self) -> "Vec2":
        return Vec2(-self.y, self.x)

    # --- interpolation -------------------------------------------------------
    def lerp(self, other: "Vec2", t: float) -> "Vec2":
        return Vec2(self.x + (other[0] - self.x) * t, self.y + (other[1] - self.y) * t)

    def rounded(self) -> tuple[int, int]:
        """Nearest whole pixel. Only the renderer should need this -- the sim
        stays in floats so slow movement does not quantise away to nothing."""
        return (int(round(self.x)), int(round(self.y)))


ZERO = Vec2(0.0, 0.0)


def from_angle(radians: float, length: float = 1.0) -> Vec2:
    return Vec2(math.cos(radians) * length, math.sin(radians) * length)


def angle_difference(a: float, b: float) -> float:
    """Signed shortest turn from angle `a` to angle `b`, in (-pi, pi].

    Wrapping is the whole reason this exists: 350 degrees and 10 degrees are 20
    apart, not 340, and every arc test gets that wrong if it just subtracts.
    """
    return (b - a + math.pi) % (2.0 * math.pi) - math.pi
