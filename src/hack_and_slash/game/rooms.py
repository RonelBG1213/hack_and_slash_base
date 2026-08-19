"""The rooms between the arenas: what stands in one, and what the doors offer.

A run is still forty arenas in the order they were measured in. Between them it
now passes through a **reward room** -- a small walkable box with one fixture at
its centre and three doors on the far wall. The doors name the kind of the room
that follows the *next* arena, so a choice made here is paid off two rooms away.

Four kinds. What each one does is a line of behaviour rather than a number, so it
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
from ..core.level import REWARD_KINDS, REWARD_PROP, Level, Prop, PropKind, RoomKind

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


# --- the content file --------------------------------------------------------
@dataclass(frozen=True)
class Table:
    """The contents of `data/rooms.json`, read once.

    Frozen, because it is content in the same sense the bestiary, the loot table
    and the progression curve are: tuning a room means editing the JSON.
    """

    enabled: bool
    doors: int
    guarantee_shop_within: int
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
        if not 1 <= doors <= len(REWARD_KINDS):
            # Sampled without replacement, so more doors than kinds is not a
            # tuning choice that produces a duller room -- it is a room that
            # cannot be built at all. Better said at startup than raised out of
            # the middle of somebody's twentieth stage.
            raise ValueError(
                f"{source}: doors is {doors}, and there are only "
                f"{len(REWARD_KINDS)} reward kinds to draw distinct ones from"
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
            guarantee_shop_within=int(payload["guarantee_shop_within"]),
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
def _raw_offer(seed: int, index: int) -> tuple[RoomKind, ...]:
    """The kinds the roll alone would show, before the shop guarantee.

    Distinct, and in the order the doors are drawn -- so which door carries
    which kind is part of the one roll rather than a second decision. Four
    reward kinds and three doors means exactly one kind is missing from any
    offer, which is the tension: a room is not a menu of everything, it is a
    menu of everything but one.
    """
    return tuple(_stream(seed, index).sample(REWARD_KINDS, table().doors))


def offer(seed: int, index: int) -> tuple[RoomKind, ...]:
    """What the room after the arena at `index` puts on its far wall.

    The roll, plus one guarantee: gold that can never be spent is not a reward,
    and three doors drawn from four kinds can go a long way without a shop. If
    no offer in the last `guarantee_shop_within` transitions held one, this one
    does.

    The guarantee reads *raw* rolls and never a history of what was taken. That
    is what keeps it stateless -- a run loaded from disk remembers nothing about
    the doors it saw before it was put down, and has to reach the same answer.
    """
    kinds = list(_raw_offer(seed, index))
    if RoomKind.SHOP in kinds:
        return tuple(kinds)

    window = max(1, table().guarantee_shop_within)
    for earlier in range(max(0, index - window + 1), index):
        if RoomKind.SHOP in _raw_offer(seed, earlier):
            return tuple(kinds)

    # Onto the last door rather than the first, so the guarantee cannot quietly
    # become most of what the reference bot sees -- it always takes door 0.
    kinds[-1] = RoomKind.SHOP
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

    One template for all four kinds, because they differ by the single prop at
    the centre -- four near-identical files would be four places to apply one
    layout fix to three of.
    """
    global _TEMPLATE
    if _TEMPLATE is None:
        # Imported here rather than at module scope purely to keep the import
        # graph flat: `core.level_io` is only needed for this one call, and
        # `game/` reaching into `core/` for IO at import time is the shape that
        # makes a missing file look like an architecture failure.
        from ..core import level_io

        _TEMPLATE = level_io.load(config.ROOMS_DIR / "chamber.json")
    return _TEMPLATE


def chamber(kind: RoomKind, doors: tuple[RoomKind, ...]) -> Level:
    """A reward room of `kind`, whose doors lead to `doors`.

    The template's props are replaced rather than added to, keeping their tiles:
    the layout -- entrance, centre, the three door positions -- is the file's
    business, and which kind stands where is this function's. Splitting it any
    other way puts half the layout in `tools/make_rooms.py` and half in here.
    """
    base = template()
    reward = base.reward
    if reward is None:
        raise ValueError("the chamber template has no reward prop to stand in for")

    tiles = [prop.tile for prop in base.props if prop.is_door]
    props = [Prop(REWARD_PROP[kind], reward.tile)]
    props += [
        Prop(PropKind.DOOR, tile, leads_to=leads_to)
        for tile, leads_to in zip(tiles, doors)
    ]

    return replace(base, name=NAMES[kind], kind=kind, props=tuple(props))
