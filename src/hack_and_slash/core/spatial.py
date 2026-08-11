"""Uniform-grid spatial hash: "what is near this point" without asking everything.

A swing tests one cone against every enemy; separation tests every body against
every other. Both are quadratic in the entity count, and an arena with fifty
things in it does that maths sixty times a second. Bucketing by cell turns the
second one into a handful of neighbour lookups.

The grid is rebuilt from scratch each tick rather than updated incrementally.
Everything moves every tick anyway, so incremental bookkeeping would cost more
than it saves -- and a rebuilt grid cannot go stale, which is the failure mode
that produces hits landing on things that are no longer there.
"""

from __future__ import annotations

import math
from typing import Iterator, TypeVar

from .vec2 import Vec2

T = TypeVar("T")


class SpatialHash:
    """Maps world positions to buckets of whatever you put in them.

    `cell` wants to be a little larger than the biggest query radius. Too small
    and a query sweeps many buckets; too large and each bucket holds everything,
    which is the flat list this exists to avoid.
    """

    def __init__(self, cell: int = 32) -> None:
        self.cell = cell
        self._buckets: dict[tuple[int, int], list[T]] = {}

    def clear(self) -> None:
        self._buckets.clear()

    def _key(self, pos: Vec2) -> tuple[int, int]:
        return (int(math.floor(pos.x / self.cell)), int(math.floor(pos.y / self.cell)))

    def insert(self, pos: Vec2, item: T) -> None:
        self._buckets.setdefault(self._key(pos), []).append(item)

    def rebuild(self, items: list[T], position_of) -> None:
        """Drop everything and re-insert. The intended once-per-tick entry point."""
        self.clear()
        for item in items:
            self.insert(position_of(item), item)

    def query(self, pos: Vec2, radius: float) -> Iterator[T]:
        """Everything in the buckets a circle touches.

        A *broadphase*: the results are candidates, not hits. Callers still run
        the exact test. Items are yielded in bucket order, which is stable for a
        given set of positions, so a seeded sim replays identically.
        """
        min_x = int(math.floor((pos.x - radius) / self.cell))
        max_x = int(math.floor((pos.x + radius) / self.cell))
        min_y = int(math.floor((pos.y - radius) / self.cell))
        max_y = int(math.floor((pos.y + radius) / self.cell))
        for cy in range(min_y, max_y + 1):
            for cx in range(min_x, max_x + 1):
                bucket = self._buckets.get((cx, cy))
                if bucket:
                    yield from bucket

    def __len__(self) -> int:
        return sum(len(bucket) for bucket in self._buckets.values())
