"""The broadphase index. It may over-report; it must never under-report."""

from __future__ import annotations

from hack_and_slash.core.spatial import SpatialHash
from hack_and_slash.core.vec2 import Vec2


def test_query_finds_everything_within_the_radius() -> None:
    grid = SpatialHash(cell=32)
    positions = {
        "near": Vec2(10, 10),
        "edge": Vec2(45, 10),
        "far": Vec2(400, 400),
    }
    for name, pos in positions.items():
        grid.insert(pos, name)

    found = set(grid.query(Vec2(10, 10), 40))
    assert "near" in found
    assert "edge" in found, "a broadphase that misses a real neighbour is a bug"
    assert "far" not in found


def test_rebuild_drops_the_previous_tick_entirely() -> None:
    # Stale entries are the failure that shows up as hits landing on corpses.
    grid = SpatialHash(cell=32)
    grid.rebuild([Vec2(5, 5)], lambda item: item)
    assert len(grid) == 1
    grid.rebuild([], lambda item: item)
    assert len(grid) == 0
    assert list(grid.query(Vec2(5, 5), 100)) == []


def test_query_order_is_stable_for_the_same_input() -> None:
    # The sim must replay identically from a seed, so iteration order matters.
    items = [(Vec2(x * 7, x * 5), f"e{x}") for x in range(20)]
    first = SpatialHash(cell=32)
    second = SpatialHash(cell=32)
    for pos, name in items:
        first.insert(pos, name)
        second.insert(pos, name)
    assert list(first.query(Vec2(30, 30), 60)) == list(second.query(Vec2(30, 30), 60))


def test_negative_coordinates_bucket_correctly() -> None:
    # Floor division, not truncation: -1 and 1 must not share a bucket.
    grid = SpatialHash(cell=32)
    grid.insert(Vec2(-10, -10), "left")
    assert "left" in set(grid.query(Vec2(-10, -10), 5))
    assert "left" not in set(grid.query(Vec2(100, 100), 5))
