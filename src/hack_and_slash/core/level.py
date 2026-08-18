"""A room: a tile grid, a hero spawn, and either something to fight or something
to take.

Most rooms are arenas. A few are not, and `RoomKind` is the one field that says
which -- see the note on it below for why that lives on the level rather than
being inferred from an empty enemy list.

Tiles are stored as one character per cell in a tuple of strings. That reads as a
picture in the JSON file, which matters when levels are hand-authored and there
is no editor to draw them in -- a level you can proofread by looking at it is a
level you can fix without tooling.

The grid decides only what is solid. Everything else in the game moves in float
pixels; tiles never leave this module except as `is_solid`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from .collision import path_is_clear
from .vec2 import Vec2

FLOOR = "."
WALL = "#"
#: Where the hero starts. Painted into the grid so the spawn cannot drift out of
#: sync with the map it belongs to; read out at load time and replaced by floor.
HERO_MARK = "@"

WALKABLE = frozenset({FLOOR, HERO_MARK})


class RoomKind(str, Enum):
    """What a room is for.

    A field rather than something inferred from an empty enemy list, and the
    difference matters: "this room has nothing to fight" and "this room is a
    fountain" are the same fact today and different faults tomorrow. `problems()`
    reports the first as a broken arena and the second as nothing at all, which
    it can only do if the level says which it meant to be.

    `combat` and `boss` are both arenas and both clear by killing. The split is
    there so a boss stage can be *asked for* rather than derived -- eight act
    enders are already known to `tools/make_level.py`, and stamping the fact
    means the campaign can be checked against it instead of computed twice.

    The other four are reward rooms. Each names the prop standing in it, so
    there is no second table mapping one to the other.
    """

    COMBAT = "combat"
    BOSS = "boss"
    FOUNTAIN = "fountain"
    SHOP = "shop"
    SHRINE = "shrine"
    TREASURE = "treasure"


#: The kinds that are cleared by killing everything in them. `sim._settle` reads
#: this and nothing else -- a room outside the set never wins by being empty,
#: which is what stops a fountain being cleared on the tick it opens.
FIGHTING_KINDS = frozenset({RoomKind.COMBAT, RoomKind.BOSS})

#: The kinds a door may lead to. Reward rooms only: an arena is arrived at by
#: leaving a reward room, never by choosing it, because the forty arenas are
#: walked in their measured order and the doors pick what is between them.
REWARD_KINDS = tuple(kind for kind in RoomKind if kind not in FIGHTING_KINDS)


class PropKind(str, Enum):
    """Something in a room that is not a body and not loose loot.

    Four of them are the rewards, one to each reward room, and the names differ
    from `RoomKind`'s on purpose: a shop room contains a *stall*, and calling the
    sprite "shop" would be naming a piece of furniture after the building.

    `DOOR` is the fifth and the only one that carries a payload.
    """

    FOUNTAIN = "fountain"
    STALL = "stall"
    SHRINE = "shrine"
    CHEST = "chest"
    DOOR = "door"


#: Which prop stands in which reward room. One direction only -- the room is the
#: authority and the prop is derived, so the two cannot be edited into disagreeing.
REWARD_PROP = {
    RoomKind.FOUNTAIN: PropKind.FOUNTAIN,
    RoomKind.SHOP: PropKind.STALL,
    RoomKind.SHRINE: PropKind.SHRINE,
    RoomKind.TREASURE: PropKind.CHEST,
}


class Prop(NamedTuple):
    """A fixture on the floor: where it is, what it is, and where it goes.

    `leads_to` is meaningful for a door and empty for everything else. One field
    doing two jobs is refused elsewhere in this project for good reason, but this
    is not that: a door with no destination and a fountain with one are both
    nonsense, and `Level.problems()` says so rather than letting either stand.
    """

    kind: PropKind
    tile: tuple[int, int]
    leads_to: RoomKind | None = None

    @property
    def is_door(self) -> bool:
        return self.kind is PropKind.DOOR


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

    #: What this room is for. Defaults to an arena, so every level written
    #: before rooms existed still means exactly what it meant.
    kind: RoomKind = RoomKind.COMBAT

    #: Fixtures on the floor. Empty in all forty arenas, which is the whole of
    #: why the sim phase that reads them costs a measured tick one falsy test.
    props: tuple[Prop, ...] = ()

    @property
    def is_fight(self) -> bool:
        """Whether clearing this room means killing what is in it."""
        return self.kind in FIGHTING_KINDS

    @property
    def doors(self) -> tuple[Prop, ...]:
        return tuple(prop for prop in self.props if prop.is_door)

    @property
    def reward(self) -> Prop | None:
        """The one prop that is not a door, or None in an arena."""
        for prop in self.props:
            if not prop.is_door:
                return prop
        return None

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

        issues.extend(self._fixture_problems())
        return issues

    def _fixture_problems(self) -> list[str]:
        """What is wrong with this room *as the kind of room it says it is*.

        Split out because the two kinds fail in ways that have nothing in common:
        an arena is broken by having nothing to fight, and a reward room is
        broken by having something. Reporting both from one flat list of rules
        was how an early draft told a fountain it needed enemies.
        """
        issues: list[str] = []

        if self.is_fight:
            if not self.enemy_spawns:
                issues.append("there is nothing to fight")
            if self.props:
                issues.append(
                    f"an arena carries {len(self.props)} props; fixtures belong in "
                    "reward rooms, and a prop here would put the interaction phase "
                    "on a measured tick"
                )
            return issues

        # --- a reward room -----------------------------------------------------
        if self.enemy_spawns:
            issues.append(f"a {self.kind.value} room has {len(self.enemy_spawns)} enemies in it")

        for prop in self.props:
            if self.is_solid(*prop.tile):
                issues.append(f"the {prop.kind.value} is inside a wall at {prop.tile}")
            if prop.is_door and prop.leads_to is None:
                issues.append(f"the door at {prop.tile} leads nowhere")
            if not prop.is_door and prop.leads_to is not None:
                issues.append(f"the {prop.kind.value} at {prop.tile} is not a door but leads somewhere")

        wanted = REWARD_PROP.get(self.kind)
        rewards = [prop for prop in self.props if not prop.is_door]
        if len(rewards) != 1:
            issues.append(
                f"a {self.kind.value} room holds {len(rewards)} rewards, not 1"
            )
        elif wanted is not None and rewards[0].kind is not wanted:
            issues.append(
                f"a {self.kind.value} room holds a {rewards[0].kind.value}, "
                f"not a {wanted.value}"
            )

        if not self.doors:
            issues.append("a reward room with no door is a room nobody leaves")

        # The no-pathing rule, enforced rather than trusted to the generator.
        # Nothing in this game walks around a wall: the hero is steered by hand
        # and the reference bot walks in straight lines. In an arena a blocked
        # lane costs a slow fight; here it is a run that cannot continue, so it
        # is checked at load and refuses to start rather than being discovered.
        origin = self.tile_center(*self.hero_spawn)
        for prop in self.props:
            if not path_is_clear(origin, self.tile_center(*prop.tile), self.is_solid, self.tile):
                issues.append(
                    f"nothing can walk from the entrance to the {prop.kind.value} "
                    f"at {prop.tile} without going round a wall"
                )
        return issues

    @property
    def is_playable(self) -> bool:
        return not self.problems()
