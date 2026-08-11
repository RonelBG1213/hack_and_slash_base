"""The arena: a tile grid, a hero spawn, and a list of what to fight in it.

Tiles are stored as one character per cell in a tuple of strings. That reads as a
picture in the JSON file, which matters when levels are hand-authored and there
is no editor to draw them in -- a level you can proofread by looking at it is a
level you can fix without tooling.

The grid decides only what is solid. Everything else in the game moves in float
pixels; tiles never leave this module except as `is_solid`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from .vec2 import Vec2

FLOOR = "."
WALL = "#"
#: Where the hero starts. Painted into the grid so the spawn cannot drift out of
#: sync with the map it belongs to; read out at load time and replaced by floor.
HERO_MARK = "@"

WALKABLE = frozenset({FLOOR, HERO_MARK})


class EnemySpawn(NamedTuple):
    type_id: str
    tile: tuple[int, int]


@dataclass(frozen=True)
class Level:
    """An immutable arena. The live state of a run lives in `game.world`."""

    name: str
    rows: tuple[str, ...]
    hero_spawn: tuple[int, int]
    enemy_spawns: tuple[EnemySpawn, ...]
    tile: int = 16

    # --- dimensions ----------------------------------------------------------
    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def pixel_size(self) -> tuple[int, int]:
        return (self.width * self.tile, self.height * self.tile)

    # --- geometry ------------------------------------------------------------
    def is_solid(self, tx: int, ty: int) -> bool:
        """Out of bounds counts as solid.

        This is what closes the arena. A level does not need a drawn border of
        wall tiles to keep bodies inside it, and more importantly a body that
        somehow ends up outside still gets pushed back in rather than sailing
        off into empty space forever.
        """
        if ty < 0 or ty >= self.height or tx < 0 or tx >= self.width:
            return True
        return self.rows[ty][tx] not in WALKABLE

    def is_walkable(self, tx: int, ty: int) -> bool:
        return not self.is_solid(tx, ty)

    def tile_at(self, pos: Vec2) -> tuple[int, int]:
        return (int(pos.x // self.tile), int(pos.y // self.tile))

    def tile_center(self, tx: int, ty: int) -> Vec2:
        """Centre of a tile in world pixels. Spawns land here, not on a corner --
        a body placed on a tile corner starts overlapping up to three others."""
        half = self.tile / 2.0
        return Vec2(tx * self.tile + half, ty * self.tile + half)

    # --- validation ----------------------------------------------------------
    def problems(self) -> list[str]:
        """Everything wrong with this level, in plain words.

        Returned rather than raised so a tool can report all of them at once.
        Loading a broken level is allowed; starting a run on one is not.
        """
        issues: list[str] = []
        if not self.rows:
            return ["the level has no rows at all"]
        if len({len(row) for row in self.rows}) != 1:
            issues.append("rows are not all the same length")

        hx, hy = self.hero_spawn
        if self.is_solid(hx, hy):
            issues.append(f"the hero spawns inside a wall at {self.hero_spawn}")

        for spawn in self.enemy_spawns:
            if self.is_solid(*spawn.tile):
                issues.append(f"{spawn.type_id} spawns inside a wall at {spawn.tile}")
        if not self.enemy_spawns:
            issues.append("there is nothing to fight")
        return issues

    @property
    def is_playable(self) -> bool:
        return not self.problems()
