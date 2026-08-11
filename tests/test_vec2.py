"""Vector maths. Small surface, but everything else is built on it."""

from __future__ import annotations

import math

import pytest

from hack_and_slash.core.vec2 import ZERO, Vec2, angle_difference, from_angle


def test_arithmetic_returns_vectors_not_tuples() -> None:
    # Vec2 is a tuple subclass, so `+` would concatenate unless overridden --
    # and a silently 4-long "vector" would fail somewhere far from here.
    total = Vec2(1, 2) + Vec2(3, 4)
    assert total == Vec2(4, 6)
    assert len(total) == 2


def test_scalar_multiply_from_either_side() -> None:
    assert Vec2(2, 3) * 2 == Vec2(4, 6)
    assert 2 * Vec2(2, 3) == Vec2(4, 6)


def test_normalized_zero_vector_is_zero_not_an_error() -> None:
    # "No input this frame" is an ordinary frame. It must not raise.
    assert ZERO.normalized() == ZERO
    assert Vec2(0, 0).with_length(5) == ZERO


def test_clamped_stops_diagonal_input_being_faster() -> None:
    # The bug this prevents: holding two keys gives a 1.41x speed boost.
    diagonal = Vec2(1, 1).clamped(1.0)
    assert diagonal.length() == pytest.approx(1.0)
    # Something already short is left alone rather than stretched.
    assert Vec2(0.3, 0.0).clamped(1.0) == Vec2(0.3, 0.0)


def test_angle_and_from_angle_round_trip() -> None:
    for degrees in (0, 45, 90, 179, -90, -135):
        radians = math.radians(degrees)
        assert from_angle(radians).angle() == pytest.approx(radians)


def test_angle_difference_takes_the_short_way_round() -> None:
    # The wrap case: 350 degrees and 10 degrees are 20 apart, not 340.
    near_full = math.radians(350)
    just_past = math.radians(10)
    assert angle_difference(near_full, just_past) == pytest.approx(math.radians(20))
    assert angle_difference(just_past, near_full) == pytest.approx(math.radians(-20))


def test_rotated_preserves_length() -> None:
    rotated = Vec2(3, 4).rotated(math.radians(37))
    assert rotated.length() == pytest.approx(5.0)


def test_rounded_is_nearest_pixel() -> None:
    assert Vec2(3.6, -2.4).rounded() == (4, -2)
