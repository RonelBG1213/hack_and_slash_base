"""Collision maths.

Every failure mode named here is one that turns an action game unplayable:
sticking on a seam, tunnelling through a wall on a dash, a swing that misses
something the player is standing next to.
"""

from __future__ import annotations

import math

import pytest

from hack_and_slash.core.collision import (
    circle_separation,
    circles_overlap,
    cone_hits,
    line_of_sight,
    move_and_collide,
    path_is_clear,
    resolve_circle_vs_tiles,
    segment_distance,
)
from hack_and_slash.core.vec2 import Vec2

TILE = 16


def solid_map(rows: list[str]):
    """Build an `is_solid` from ASCII. '#' is wall, anything else is floor.

    Outside the map reads as solid, matching the real level: the arena is closed
    by the absence of floor, not by a ring of drawn wall tiles.
    """

    def is_solid(tx: int, ty: int) -> bool:
        if ty < 0 or ty >= len(rows) or tx < 0 or tx >= len(rows[ty]):
            return True
        return rows[ty][tx] == "#"

    return is_solid


# A room with a wall along the top and open floor below.
FLAT_WALL = solid_map(
    [
        "#####",
        "#...#",
        "#...#",
        "#...#",
        "#####",
    ]
)


# --- pushing out of walls ----------------------------------------------------
def test_body_overlapping_a_wall_is_pushed_flush_against_it() -> None:
    radius = 5.0
    # Centre 2px into the wall row (which ends at y=16), so it must end at y=21.
    pushed = resolve_circle_vs_tiles(Vec2(40, 18), radius, FLAT_WALL, TILE)
    assert pushed.y == pytest.approx(16 + radius)
    assert pushed.x == pytest.approx(40), "a vertical contact must not shift x"


def test_body_clear_of_every_wall_is_left_exactly_where_it_is() -> None:
    pos = Vec2(40, 40)
    assert resolve_circle_vs_tiles(pos, 5.0, FLAT_WALL, TILE) == pos


def test_body_wedged_in_a_corner_ends_clear_of_both_walls() -> None:
    radius = 5.0
    # Inside the top-left corner, overlapping the top wall and the left wall.
    pushed = resolve_circle_vs_tiles(Vec2(18, 18), radius, FLAT_WALL, TILE)
    assert pushed.x >= 16 + radius - 1e-6
    assert pushed.y >= 16 + radius - 1e-6


def test_body_fully_inside_a_wall_escapes_by_the_nearest_open_face() -> None:
    # Spawned in the top wall, nearer its underside -- it should drop into the room.
    escaped = resolve_circle_vs_tiles(Vec2(40, 14), 5.0, FLAT_WALL, TILE)
    assert escaped.y == pytest.approx(16 + 5.0)


# --- sliding -----------------------------------------------------------------
def test_diagonal_into_a_wall_keeps_the_tangent_and_loses_the_normal() -> None:
    """Sliding. Without this, running at a wall at an angle stops you dead."""
    start = Vec2(40, 24)
    moved = move_and_collide(start, 5.0, Vec2(4, -8), FLAT_WALL, TILE)
    assert moved.x == pytest.approx(44), "horizontal motion must survive"
    assert moved.y == pytest.approx(21), "vertical motion must stop at the wall"


def test_sliding_along_a_tiled_wall_does_not_snag_on_the_seams() -> None:
    """The internal-edge case.

    A wall three tiles wide is three separate boxes. If the seams between them
    are treated as surfaces, a body sliding along the wall catches on each one.
    Here the body hugs the wall and travels the full distance every step.
    """
    wide = solid_map(
        [
            "######",
            "#....#",
            "#....#",
            "######",
        ]
    )
    radius = 5.0
    pos = Vec2(20, 16 + radius)  # already flush against the top wall
    for _ in range(20):
        before_x = pos.x
        pos = move_and_collide(pos, radius, Vec2(2.0, -1.0), wide, TILE)
        assert pos.x - before_x == pytest.approx(2.0), "snagged on a seam"
        assert pos.y == pytest.approx(16 + radius), "should stay hugging the wall"


# --- tunnelling --------------------------------------------------------------
def test_a_fast_body_cannot_hop_through_a_wall() -> None:
    """A dash covers real distance in one tick. Resolution only sees where the
    body landed, so without substepping it lands past the wall and stays there."""
    thin = solid_map(
        [
            ".....",
            ".....",
            "#####",
            ".....",
            ".....",
        ]
    )
    # 100px of downward travel in one call, straight through a one-tile wall.
    moved = move_and_collide(Vec2(40, 20), 5.0, Vec2(0, 100), thin, TILE)
    assert moved.y < 32, f"tunnelled through the wall to y={moved.y}"
    assert moved.y == pytest.approx(32 - 5.0)


# --- bodies against each other -----------------------------------------------
def test_circles_overlap_is_exclusive_at_exactly_touching() -> None:
    assert circles_overlap(Vec2(0, 0), 5, Vec2(9, 0), 5)
    assert not circles_overlap(Vec2(0, 0), 5, Vec2(10, 0), 5)


def test_separation_pushes_just_far_enough_to_touch() -> None:
    # `a` sits left of `b`, so clearing it means moving further left, not right.
    offset = circle_separation(Vec2(0, 0), 5, Vec2(6, 0), 5)
    assert offset.x == pytest.approx(-4.0)
    assert offset.y == pytest.approx(0.0)
    assert circle_separation(Vec2(0, 0), 5, Vec2(20, 0), 5).is_zero()


def test_separation_of_exactly_stacked_bodies_is_deterministic() -> None:
    # No direction to read off the geometry, but the sim must still replay.
    first = circle_separation(Vec2(7, 7), 5, Vec2(7, 7), 5)
    second = circle_separation(Vec2(7, 7), 5, Vec2(7, 7), 5)
    assert first == second
    assert not first.is_zero()


# --- swings ------------------------------------------------------------------
def test_cone_hits_inside_the_arc_and_misses_outside_it() -> None:
    arc = math.radians(90)  # 45 degrees either side of facing
    origin, facing, reach = Vec2(0, 0), 0.0, 60.0

    inside = Vec2(math.cos(math.radians(40)), math.sin(math.radians(40))) * 50
    outside = Vec2(math.cos(math.radians(50)), math.sin(math.radians(50))) * 50

    assert cone_hits(origin, facing, arc, reach, inside, 1.0)
    assert not cone_hits(origin, facing, arc, reach, outside, 1.0)


def test_cone_misses_what_is_behind_you() -> None:
    assert not cone_hits(Vec2(0, 0), 0.0, math.radians(90), 60.0, Vec2(-30, 0), 5.0)


def test_cone_reach_measures_to_the_near_edge_of_the_target() -> None:
    arc, reach = math.radians(90), 40.0
    # Centre at 44 is out of reach, but a body of radius 6 reaches in to 38.
    assert cone_hits(Vec2(0, 0), 0.0, arc, reach, Vec2(44, 0), 6.0)
    assert not cone_hits(Vec2(0, 0), 0.0, arc, reach, Vec2(44, 0), 1.0)


def test_cone_always_hits_something_standing_on_you() -> None:
    # At zero distance there is no meaningful angle, and "it is inside me" must
    # never read as a miss regardless of which way the player happens to face.
    assert cone_hits(Vec2(10, 10), math.pi, math.radians(45), 30.0, Vec2(11, 10), 8.0)


def test_a_wide_arc_covers_everything() -> None:
    full = math.radians(360)
    for degrees in (0, 90, 180, 270):
        target = Vec2(math.cos(math.radians(degrees)), math.sin(math.radians(degrees))) * 20
        assert cone_hits(Vec2(0, 0), 0.0, full, 40.0, target, 4.0)


# --- swept paths -------------------------------------------------------------
def test_a_path_is_swept_not_sampled_at_its_endpoints() -> None:
    """What makes this usable for a fast projectile.

    Both ends of the jump below sit on open floor; only the middle is wall. A
    check that looks at where something *landed* sees nothing wrong, which is
    exactly how a bolt ends up on the far side of a wall with no error.
    """
    thin_wall = solid_map(
        [
            ".....",
            ".....",
            "#####",
            ".....",
            ".....",
        ]
    )
    start, end = Vec2(40, 20), Vec2(40, 60)
    assert not thin_wall(*(int(start.x // TILE), int(start.y // TILE)))
    assert not thin_wall(*(int(end.x // TILE), int(end.y // TILE)))
    assert not path_is_clear(start, end, thin_wall, TILE)


def test_a_path_across_open_floor_is_clear() -> None:
    assert path_is_clear(Vec2(20, 40), Vec2(60, 40), FLAT_WALL, TILE)


def test_a_very_long_path_is_still_sampled_densely_enough() -> None:
    # Sampling is per half tile, so the step count has to grow with distance --
    # a fixed number of samples would thin out until walls leaked through.
    thin_wall = solid_map(["." * 40] * 10 + ["#" * 40] + ["." * 40] * 10)
    assert not path_is_clear(Vec2(80, 40), Vec2(80, 320), thin_wall, TILE)


def test_a_zero_length_path_checks_where_it_stands() -> None:
    assert path_is_clear(Vec2(40, 40), Vec2(40, 40), FLAT_WALL, TILE)
    assert not path_is_clear(Vec2(40, 8), Vec2(40, 8), FLAT_WALL, TILE)


# --- sight -------------------------------------------------------------------
def test_line_of_sight_is_blocked_by_a_wall_between_two_points() -> None:
    blocked = solid_map(
        [
            ".....",
            ".....",
            ".#...",
            ".....",
            ".....",
        ]
    )
    # Straight through the solid tile at (1, 2).
    assert not line_of_sight(Vec2(8, 40), Vec2(56, 40), blocked, TILE)
    # A route that passes below it is clear.
    assert line_of_sight(Vec2(8, 56), Vec2(56, 56), blocked, TILE)


# --- point against a segment -------------------------------------------------
def test_a_point_on_the_segment_is_no_distance_from_it() -> None:
    a, b = Vec2(0, 0), Vec2(100, 0)
    assert segment_distance(a, a, b) == pytest.approx(0.0)
    assert segment_distance(b, a, b) == pytest.approx(0.0)
    assert segment_distance(Vec2(50, 0), a, b) == pytest.approx(0.0)


def test_distance_is_measured_to_the_perpendicular_foot() -> None:
    # Straight out from the middle of the span.
    assert segment_distance(Vec2(50, 30), Vec2(0, 0), Vec2(100, 0)) == pytest.approx(30.0)


def test_a_point_past_the_end_measures_to_the_end_not_the_line() -> None:
    """The clamp, and the whole reason this is not a line test.

    A blade that has swept past you is behind you. Projected onto the infinite
    line, the point below is 3 away; on the segment it is 5, and 5 is the answer
    that stops a blade hitting things it has already gone by.
    """
    assert segment_distance(Vec2(104, 3), Vec2(0, 0), Vec2(100, 0)) == pytest.approx(5.0)
    assert segment_distance(Vec2(-4, 3), Vec2(0, 0), Vec2(100, 0)) == pytest.approx(5.0)


def test_a_segment_of_no_length_falls_back_to_point_to_point() -> None:
    """Reached every tick a blade sits at the end of its travel and turns."""
    still = Vec2(20, 20)
    assert segment_distance(Vec2(20, 25), still, still) == pytest.approx(5.0)
