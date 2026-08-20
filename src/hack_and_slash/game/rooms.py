"""The rooms between the arenas: what stands in one, and what the doors offer.

A run is still forty arenas in the order they were measured in. Between them it
now passes through a **reward room** -- a small walkable box with one fixture at
its centre and three doors, standing on the three walls the hero did *not* come
in through. The doors name the kind of the room that follows the *next* arena,
so a choice made here is paid off two rooms away; which door is taken also
decides which wall the next room is entered by, so the rooms lie end to end.

Four kinds, and the stall is not one of the three a door draws from: it stands on
every fifth floor and on no other. A schedule rather than a roll, because "gold
you can always spend somewhere soon" and "gold you know exactly when you can
spend" are different promises and the second is the one worth planning around.

What each kind does is a line of behaviour rather than a number, so it
is code; the numbers are in `data/rooms.json`, and the two are checked against
each other at load the way `shop.stock()` checks its goods -- a kind added to the
data without an effect fails loudly instead of building a room with an inert
thing in the middle of it.

**The map stream is a fourth seeded stream, and it is stateless.** Which three
doors a room offers comes from a `Random` constructed fresh from `(seed, index)`
and thrown away. Two reasons, and the second is the one that decided it:

1. It cannot disturb `world.rng`, `world.loot_rng` or `world.attr_rng`. One
   interleaved draw on the first of those would shift every damage roll for the
   rest of the run and move all 280 cells of the recorded grid, with no balance
   number changing and nothing to report it.
2. A `Random` that is *held* has internal state a save cannot record. Deriving
   per transition is the same trick `Run._stage_seed` already uses, and it is
   what makes a loaded run replay the doors it was offered before it was put
   down rather than being handed three new ones.

Pure Python -- no pygame. The run decides *when* a room happens; this decides
what is in it.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path

from .. import config
from ..core.level import (
    REWARD_KINDS,
    REWARD_PROP,
    Direction,
    Level,
    Prop,
    PropKind,
    RoomKind,
)

#: The fourth stream, xor'd into the run seed exactly as `LOOT_STREAM` and
#: `ATTR_STREAM` are xor'd into a world's. A different constant and nothing more
#: clever than that: the whole guarantee is that the sequences do not overlap,
#: and four unrelated constants give four unrelated sequences.
MAP_STREAM = 0x4D0075

#: Spreads consecutive transitions apart before the xor, so room 3 and room 4 do
#: not draw from adjacent sequences. The same job `Run._stage_seed`'s 1013 does,
#: and a different prime so the two do not march in step down a run.
ROOM_STRIDE = 7919

#: The fifth and sixth streams: what a stall has on its shelf, and what a shrine
#: puts on its plinth. Two more unrelated constants, because the whole guarantee
#: has always been that the sequences do not overlap and unrelated constants give
#: unrelated sequences.
#:
#: They are *not* derived from `Run._room_seed`, which is the room's own world
#: seed. That docstring says this layer was coming -- "it exists so that the day
#: something in a room does roll, it is not drawing the sequence the arena beside
#: it draws" -- and reusing it would have made the shelf correlated with the
#: room world's rng and with the plinth, which is the thing these constants are
#: for.
STALL_STREAM = 0x57A11
SHRINE_STREAM = 0x5E121


def _stream(seed: int, index: int, stream: int = MAP_STREAM) -> random.Random:
    """One stream for one transition. Constructed, used, discarded.

    Parenthesised deliberately: `^` binds looser than `+` in Python, so
    `seed ^ stream + index * ROOM_STRIDE` is a different -- and silently
    plausible -- expression from this one.

    `stream` defaults to the map so the doors read exactly as they always did;
    the stall and the shrine pass their own, through the two thin wrappers below
    rather than by naming a constant at every call site.
    """
    return random.Random((seed ^ stream) + index * ROOM_STRIDE)


def stall_stream(seed: int, index: int) -> random.Random:
    """What the stall at `index` has on its shelf. Never held -- see `offer`.

    That is what makes a run loaded from disk find the same three pieces at the
    same prices it was looking at when it was put down, with the save file
    saying nothing about a shelf at all.
    """
    return _stream(seed, index, STALL_STREAM)


def shrine_stream(seed: int, index: int) -> random.Random:
    """What the shrine at `index` offers. Never held, for the same reason."""
    return _stream(seed, index, SHRINE_STREAM)


#: Every reward kind but the stall. The three a door can always offer, and the
#: pool `offer` draws from on the floors a stall is not standing on.
#:
#: Up here rather than beside `offer`, because `Table.load` bounds `doors`
#: against it: the stall is on a schedule rather than in the draw, so this is
#: what a wall can actually be filled from.
ORDINARY_KINDS = tuple(kind for kind in REWARD_KINDS if kind is not RoomKind.SHOP)


# --- the content file --------------------------------------------------------
@dataclass(frozen=True)
class Table:
    """The contents of `data/rooms.json`, read once.

    Frozen, because it is content in the same sense the bestiary, the loot table
    and the progression curve are: tuning a room means editing the JSON.
    """

    enabled: bool
    doors: int

    #: How many floors apart the stalls stand. Five means floors 5, 10, 15 and so
    #: on carry one and no other floor can; `0` switches the stall off entirely
    #: and `1` puts one on every floor, which are the two ends of the rollback.
    stall_every: int

    first_room: RoomKind
    heal_percent: int
    shrine_points: int
    chest_gold: int
    chest_floor_step: float

    #: How many rolled pieces a stall puts above its consumables, and how many
    #: attributes a shrine offers. Zero is a meaningful value for both and is the
    #: documented rollback: a stall with no gear is the shop exactly as it was,
    #: and a shrine offering nothing falls back to every attribute at once.
    stall_offers: int
    shrine_offers: int

    @property
    def is_off(self) -> bool:
        """Whether the whole layer is inert -- the single switch and the rollback.

        Off, no reward room is ever built and a cleared arena leads straight to
        the next one, which is the campaign exactly as it was measured.
        """
        return not self.enabled

    def heal_for(self, max_hp: int) -> int:
        """What a fountain gives a hero with this maximum.

        A percentage of the maximum rather than a flat number, so it means the
        same thing to a 130-hp Knight and a 70-hp Rogue -- and of the *maximum*
        rather than of what is missing, because a fraction-of-missing heal pays
        the nearly-dead most, and the nearly-dead hero is exactly the one the
        ceiling test needs to keep killing.
        """
        return max(0, round(max_hp * self.heal_percent / 100.0))

    def chest_worth(self, floor: int) -> int:
        """What a chest holds on this floor.

        The same depth curve `data/loot.json` puts on a kill, reusing the shape
        rather than inventing a second idea of what deeper is worth.

        Draws no dice. A chest is worth exactly what the floor says, so this
        layer cannot disturb a damage roll however it is tuned -- the same
        property `progression.py` has and for the same reason.
        """
        return max(1, round(self.chest_gold * (1 + self.chest_floor_step * (floor - 1))))

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        source = path or config.ROOMS_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))

        first = RoomKind(payload["first_room"])
        if first not in REWARD_PROP:
            raise ValueError(
                f"{source}: first_room is '{first.value}', which is an arena rather "
                f"than a reward room; the {len(REWARD_KINDS)} are "
                f"{', '.join(kind.value for kind in REWARD_KINDS)}"
            )

        doors = int(payload["doors"])
        if not 1 <= doors <= len(ORDINARY_KINDS):
            # Sampled without replacement, so more doors than kinds is not a
            # tuning choice that produces a duller room -- it is a room that
            # cannot be built at all. Better said at startup than raised out of
            # the middle of somebody's twentieth stage.
            #
            # The bound is the *ordinary* kinds, not every kind: the stall is on
            # a schedule rather than in the draw, so off a stall floor there are
            # only these to fill a wall from, and a room that builds on floor 5
            # and fails on floor 6 is the worst shape this check could take.
            raise ValueError(
                f"{source}: doors is {doors}, and there are only "
                f"{len(ORDINARY_KINDS)} kinds outside the stall to draw "
                f"distinct ones from"
            )

        stall_every = int(payload["stall_every"])
        if stall_every < 0:
            raise ValueError(
                f"{source}: stall_every is {stall_every}, which is not a count "
                f"of floors; 0 is the stall switched off"
            )

        stall_offers = int(payload["stall"]["offers"])
        shrine_offers = int(payload["shrine"]["offers"])
        for name, count in (("stall.offers", stall_offers), ("shrine.offers", shrine_offers)):
            if count < 0:
                raise ValueError(f"{source}: {name} is {count}, which is not a count")
        # The *upper* bound on shrine.offers is checked in `progression.offers`,
        # and the one on stall.offers in `equipment.offers`. How many attributes
        # there are, and how many pieces are in the pool, is those modules'
        # knowledge -- reaching back for it from here would close an import cycle
        # to move one error message a little earlier.

        return cls(
            enabled=bool(payload["enabled"]),
            doors=doors,
            stall_every=stall_every,
            first_room=first,
            heal_percent=int(payload["fountain"]["heal_percent"]),
            shrine_points=int(payload["shrine"]["points"]),
            chest_gold=int(payload["treasure"]["gold"]),
            chest_floor_step=float(payload["treasure"]["floor_step"]),
            stall_offers=stall_offers,
            shrine_offers=shrine_offers,
        )


_TABLE: Table | None = None
_TEMPLATE: Level | None = None


def table() -> Table:
    """The shipped room table, read from disk once.

    Lazy rather than at import, for the reason `loot.table()` gives: a module
    that reads a file at import time turns a missing data file into a failure of
    `test_architecture.py`, reported as an import error naming the wrong problem.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


def reset_cache() -> None:
    """Forget the loaded table and template. For tests that supply their own."""
    global _TABLE, _TEMPLATE
    _TABLE = None
    _TEMPLATE = None


# --- the offer ---------------------------------------------------------------
def floor_of(index: int) -> int:
    """The floor the room these doors lead to will stand on.

    Two, not one, and the off-by-one is the whole point of the mechanic: the
    doors in a room name the room after the **next** arena. `offer(seed, i)` is
    read when the run is standing at index `i`, and what it picks is entered at
    index `i + 1`, whose floor is `i + 2` -- because a room takes the floor
    number of the arena it follows (`Purse(floor=index + 1)` is that definition).

    Written down as a function rather than as `+ 2` at two call sites, because it
    is the kind of arithmetic that looks wrong when it is right.
    """
    return index + 2


def is_stall_floor(index: int) -> bool:
    """Whether the doors at `index` may offer a stall.

    Every fifth floor and no other. `stall_every: 0` switches the stall off
    entirely, which is the rollback beside `stall.offers: 0`.
    """
    every = table().stall_every
    return every > 0 and floor_of(index) % every == 0


def offer(seed: int, index: int) -> tuple[RoomKind, ...]:
    """What the room after the arena at `index` puts on its three walls.

    Distinct kinds, in the order the doors are drawn -- so which door carries
    which kind is part of the one roll rather than a second decision.

    **The stall is not in the roll; it is on a schedule.** Off a stall floor the
    doors are drawn from `ORDINARY_KINDS` and a shop is not reachable at all; on
    one the stall is certain and the other doors are drawn from `ORDINARY_KINDS`
    around it. That replaces the old draw-and-guarantee pair, which cannot mean
    anything beside a schedule: "never more than four transitions from a shop"
    and "a shop on every fifth floor" are two answers to the same question.

    The schedule *is* the guarantee, and it is a better one -- gold that can
    never be spent is not a reward, and now the player knows exactly how far the
    next chance to spend it is rather than trusting that one will turn up.

    Onto the **last** door, exactly as the old guarantee was, so the stall can
    never quietly become most of what the reference bot walks into: it always
    takes door 0.

    Stateless, like everything on the map stream: a run loaded from disk is
    offered the doors it was offered before it was put down, and the save file
    says nothing about a door at all.
    """
    doors = table().doors
    if not is_stall_floor(index):
        return tuple(_stream(seed, index).sample(ORDINARY_KINDS, doors))

    kinds = _stream(seed, index).sample(ORDINARY_KINDS, doors - 1)
    kinds.append(RoomKind.SHOP)
    return tuple(kinds)


# --- building one ------------------------------------------------------------
#: What each reward room is called, for the banner and the save row. Four short
#: names rather than "Fountain Room": the arenas are all "The something" and a
#: room that broke the pattern would read as a different kind of screen.
NAMES = {
    RoomKind.FOUNTAIN: "The Spring",
    RoomKind.SHOP: "The Stall",
    RoomKind.SHRINE: "The Shrine",
    RoomKind.TREASURE: "The Cache",
}


def template() -> Level:
    """The chamber on disk, read once. Written by `tools/make_rooms.py`.

    One template for all four kinds *and* all four approaches, because they
    differ by the single prop at the centre and by which of the four openings is
    the way in -- sixteen near-identical files would be sixteen places to apply
    one layout fix to fifteen of.
    """
    global _TEMPLATE
    if _TEMPLATE is None:
        # Imported here rather than at module scope purely to keep the import
        # graph flat: `core.level_io` is only needed for this one call, and
        # `game/` reaching into `core/` for IO at import time is the shape that
        # makes a missing file look like an architecture failure.
        from ..core import level_io

        _TEMPLATE = level_io.load(config.ROOMS_DIR / "chamber.json")
        _check_template(_TEMPLATE)
    return _TEMPLATE


#: The wall you came in through, given the wall you walked out of the last room
#: by. Walking out through the east side of one room puts you at the west side of
#: the next: the rooms are laid end to end, so a run reads as a path rather than
#: as four unrelated boxes.
OPPOSITE = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}

#: Left, forward, right -- for a hero facing each way. Screen axes, so facing
#: east (`+x`) puts left at north (`-y`).
#:
#: **The order is content, exactly as the door column's top-middle-bottom was.**
#: `offer` fills these in order and the reference bot always takes door 0, so two
#: things are pinned by putting *forward* in the middle:
#:
#: 1. Forward is the door collinear with the fixture -- every opening shares an
#:    axis with the centre, so the door straight ahead runs over it. Door 0 is
#:    never that door, which is what keeps the bot from healing on its way out
#:    and reporting its own perturbation as difficulty.
#: 2. `offer` puts the stall on the *last* door for the same reason, so the bot
#:    never walks into a shop either.
#:
#: A written-out table rather than arithmetic on an angle: four rows that can be
#: read and checked beats a rotation that has to be trusted.
DOOR_ORDER = {
    Direction.NORTH: (Direction.WEST, Direction.NORTH, Direction.EAST),
    Direction.SOUTH: (Direction.EAST, Direction.SOUTH, Direction.WEST),
    Direction.EAST: (Direction.NORTH, Direction.EAST, Direction.SOUTH),
    Direction.WEST: (Direction.SOUTH, Direction.WEST, Direction.NORTH),
}

#: Where a run that has not been through a door yet comes in. The first room is
#: entered from the west because that is where the entrance has always been, so
#: the room after arena one looks exactly as it did before rooms could turn.
FIRST_ENTRANCE = Direction.WEST


def _wall_of(tile: tuple[int, int], centre: tuple[int, int]) -> Direction:
    """Which wall an opening sits against, read off its offset from the fixture.

    Derived rather than recorded, so `tools/make_rooms.py` moving an opening
    cannot leave a label behind pointing at the wall it used to be on. The
    dominant axis decides, which is unambiguous for openings at wall midpoints
    and is checked for all four at load by `_check_template`.
    """
    dx = tile[0] - centre[0]
    dy = tile[1] - centre[1]
    if abs(dx) >= abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    return Direction.SOUTH if dy > 0 else Direction.NORTH


def openings(base: Level) -> dict[Direction, tuple[int, int]]:
    """The template's four openings, by the wall each one stands against."""
    reward = base.reward
    if reward is None:
        raise ValueError("the chamber template has no reward prop to stand in for")
    return {_wall_of(prop.tile, reward.tile): prop.tile for prop in base.doors}


def _check_template(base: Level) -> None:
    """Refuse a template that cannot serve all four approaches.

    Said at load rather than left to fail in the middle of a run: a chamber
    missing its north opening builds perfectly well for three of the four walls
    and raises a `KeyError` the first time a hero walks out of a door heading
    south, which is somebody's twentieth stage.
    """
    walls = openings(base)
    if len(walls) != len(Direction) or len(base.doors) != len(Direction):
        raise ValueError(
            f"the chamber template has {len(base.doors)} openings on "
            f"{len(walls)} walls; it needs one on each of the "
            f"{len(Direction)} -- rerun tools/make_rooms.py"
        )


def chamber(
    kind: RoomKind,
    doors: tuple[RoomKind, ...],
    entered_from: Direction = FIRST_ENTRANCE,
) -> Level:
    """A reward room of `kind`, entered through `entered_from`, leading to `doors`.

    The template's props are replaced rather than added to, keeping their tiles:
    the layout -- the four openings and the centre -- is the file's business, and
    which of them is the way in, which kind stands where, is this function's.
    Splitting it any other way puts half the layout in `tools/make_rooms.py` and
    half in here.

    The opening on the wall the hero arrived through becomes the spawn and
    carries no door; the other three carry the offer, ordered left, forward,
    right by `DOOR_ORDER`. So the room turns with the run: the door you took last
    decides which wall you are standing at and therefore which three walls you
    are choosing between.
    """
    base = template()
    reward = base.reward
    if reward is None:
        raise ValueError("the chamber template has no reward prop to stand in for")

    walls = openings(base)
    props = [Prop(REWARD_PROP[kind], reward.tile)]
    props += [
        Prop(PropKind.DOOR, walls[wall], leads_to=leads_to, wall=wall)
        for wall, leads_to in zip(DOOR_ORDER[OPPOSITE[entered_from]], doors)
    ]

    return replace(
        base,
        name=NAMES[kind],
        kind=kind,
        hero_spawn=walls[entered_from],
        props=tuple(props),
    )
