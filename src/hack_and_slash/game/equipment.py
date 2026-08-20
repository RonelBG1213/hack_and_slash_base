"""What a stall rolls onto its shelf, and what buying it does.

The five consumables in `game/shop.py` are the same five rows in the same order
on every stall of every run. This is the half that is a decision: three pieces
drawn from a pool of twelve, each with a rolled rarity that scales its attribute
block and its price by the same factor, priced against the floor it is standing
on and gone the moment you walk out of the room.

**A piece is a name and an `Attributes` block.** It is not a weapon, it is not
worn, there are no slots and nothing is replaced. Buying one adds its block to
`run.earned` permanently, through `progression.grant`, which is exactly what
`shop._boots` has always done with `move_speed` -- the mechanism is deliberately
the one that already existed rather than a second one beside it.

**The roll is stateless, and that is the load-bearing property.** The shelf comes
from a `Random` built fresh from `(seed, index)` and thrown away, which is
`rooms.offer`'s trick and is here for the same two reasons:

1. It cannot disturb `world.rng`, `world.loot_rng` or `world.attr_rng`. One
   interleaved draw on the first of those would shift every damage roll for the
   rest of the run and move all 280 cells of the recorded grid, with no balance
   number changing and nothing to report it.
2. A `Random` that is *held* has internal state a save cannot record. Deriving
   per room is what makes a loaded run find the same three pieces at the same
   prices it was looking at when it was put down, with `save.py` untouched and
   the save file saying nothing about a shelf at all.

Prices and blocks come from `data/equipment.json`; what a purchase *does* is
code. The two are checked against each other at load -- a rarity the pool cannot
price fails loudly rather than building a shelf with an inert thing on it, which
is `shop.stock()`'s guarantee and `progression.Table.load`'s.

Pure Python -- no pygame. The scene decides when a stall is open; this decides
what is on it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .. import config
from . import loot, progression, rooms
from .attributes import Attributes


@dataclass(frozen=True)
class Piece:
    """One entry in the pool. Content, and never seen by a player as it is.

    What reaches the panel is an `Offer` -- this scaled by a rarity and priced
    against a floor. Two types rather than one because the pool is shared by
    every run of the game and an offer belongs to one room of one run, which is
    the same split `EntityType` and `Entity` have.
    """

    id: str
    name: str
    price: int
    attributes: Attributes

    #: What the panel prints, already formatted. Built at load rather than at
    #: draw time so the "at most two attributes" rule below has somewhere
    #: honest to be enforced.
    blurb: str


#: The most attributes one piece may carry, and it is a layout constraint rather
#: than a design one. `render/shop_panel.py` gives the blurb about 150 pixels
#: between `LEFT + BLURB_X` and the rarity word right-aligned at `TALLY_RIGHT`,
#: and a third field draws straight through it. Checked at load because a piece
#: is content, and content gets added by somebody who is not looking at a 384px
#: panel at the time.
MAX_ATTRIBUTES = 2

#: What each attribute is called on a shelf, and the units it is shown in. The
#: same names `render/level_panel.py` uses -- two vocabularies for the eight
#: attributes across two panels is a thing a player would have to learn twice.
LABELS = {
    "max_hp": "Health",
    "damage": "Damage",
    "defense": "Defense",
    "crit_chance": "Crit rate",
    "crit_damage": "Crit damage",
    "evasion": "Dodge",
    "regen": "Regen/tick",
    "move_speed": "Move speed",
}


def describe(block: Attributes) -> str:
    """An attribute block as the line a player reads.

    Per-mille and hundredths are what the arithmetic is in, for the reason
    `attributes.py` gives; nobody reads "350 per mille" as thirty-five percent.
    The conversion happens here, at the edge, and nowhere in the arithmetic --
    the same split `LevelPanel._format` makes, and the same reason.

    Fields in declaration order, which is `progression.SPENDABLE` order, which is
    the order the shrine's panel draws them in. One order for the eight
    attributes everywhere they are shown.
    """
    parts = []
    for name in progression.SPENDABLE:
        value = getattr(block, name)
        if value:
            parts.append(f"+{_format(name, value)} {LABELS[name]}")
    return ", ".join(parts)


def _format(name: str, value: int) -> str:
    """One stored integer as the thing a player thinks they are buying.

    Deliberately the same three branches `LevelPanel._format` has. They are
    duplicated rather than shared because that one is a rendering detail of a
    pygame module and this one has to run headless -- `game/` never imports
    `render/`, and a shared helper would have to live somewhere that is neither.
    """
    if name in ("crit_chance", "crit_damage", "evasion", "move_speed"):
        return f"{value / 10:g}%"
    if name == "regen":
        # The unit is in the label ("Regen/tick"), not here, so the blurb reads
        # "+0.04 Regen/tick" rather than "+0.04/tick Regen".
        return f"{value / 100:g}"
    return str(value)


@dataclass(frozen=True)
class Offer:
    """One row of a stall's gear section: a piece, as this room is selling it.

    Frozen and self-contained, so the panel draws it and the scene buys it
    without either re-deriving anything. `key` is what records the purchase, and
    it names the room rather than the piece: the same Cuirass rolled at two
    different stalls is two different things to buy.
    """

    key: str
    piece_id: str
    name: str
    rarity: loot.Rarity
    price: int
    attributes: Attributes
    blurb: str


@dataclass(frozen=True)
class Table:
    """The contents of `data/equipment.json`, read once.

    Frozen, because it is content in the same sense the bestiary, the loot table,
    the progression curve and the room table are: tuning gear means editing the
    JSON.
    """

    floor_step: float
    rarity_scale: dict[loot.Rarity, int]
    pieces: tuple[Piece, ...]

    def scale_of(self, rarity: loot.Rarity) -> int:
        return self.rarity_scale[rarity]

    def price_on(self, base: int, scale: int, floor: int) -> int:
        """What a piece costs on this floor, at this rarity.

        The same depth curve `loot.gold_for` puts on a kill and
        `rooms.Table.chest_worth` puts on a chest, reusing the shape rather than
        inventing a third idea of what deeper is worth.

        Draws no dice. A shelf's prices are exactly what the floor and the rarity
        say, so this cannot disturb a damage roll however it is tuned -- the same
        property `chest_worth` has and for the same reason.
        """
        return max(1, round(base * scale * (1 + self.floor_step * (floor - 1))))

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        source = path or config.EQUIPMENT_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))

        # Bidirectional, the way `shop.stock()` validates its goods and
        # `progression.Table.load` validates its prices. A tier the pool cannot
        # price is a rarity that crashes the first time it is rolled, which may
        # be somebody's thirtieth stage; a price for a tier that does not exist
        # is a typo sitting there doing nothing. Both fail here.
        tiers = {tier.rarity for tier in loot.table().tiers}
        raw_scale = {
            name: value
            for name, value in payload["rarity_scale"].items()
            if not name.startswith("_")
        }
        named = {loot.Rarity(name) for name in raw_scale}
        missing = sorted(tier.value for tier in tiers - named)
        unknown = sorted(name.value for name in named - tiers)
        if missing or unknown:
            raise KeyError(
                f"{source}: rarity_scale prices {unknown or 'nothing unknown'} "
                f"and is missing {missing or 'nothing'}; data/loot.json's tiers "
                f"are {sorted(tier.value for tier in tiers)}"
            )

        pieces = []
        for piece_id, entry in payload["pieces"].items():
            if piece_id.startswith("_"):
                continue
            block = Attributes.from_dict(entry.get("attributes"))
            carried = sum(1 for name in progression.SPENDABLE if getattr(block, name))
            if carried > MAX_ATTRIBUTES:
                raise ValueError(
                    f"{source}: '{piece_id}' carries {carried} attributes and the "
                    f"panel has room for {MAX_ATTRIBUTES}; see MAX_ATTRIBUTES in "
                    f"game/equipment.py for the pixels this is about"
                )
            pieces.append(
                Piece(
                    id=piece_id,
                    name=entry.get("name", piece_id),
                    price=int(entry["price"]),
                    attributes=block,
                    blurb=describe(block),
                )
            )

        if not pieces:
            raise ValueError(f"{source}: the pool is empty, so no stall can roll")

        return cls(
            floor_step=float(payload["floor_step"]),
            rarity_scale={loot.Rarity(k): int(v) for k, v in raw_scale.items()},
            # A tuple in file order, so `offers` samples a stable population and
            # a seeded run replays the same shelf across a reordering of the
            # JSON only if the *order* is kept -- which is why the order is
            # content here exactly as it is in `shop.stock()`.
            pieces=tuple(pieces),
        )


_TABLE: Table | None = None


def table() -> Table:
    """The shipped gear pool, read from disk once.

    Lazy rather than at import, for the reason `loot.table()` gives: a module
    that reads a file at import time turns a missing data file into a failure of
    `test_architecture.py`, reported as an import error naming the wrong problem.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


def reset_cache() -> None:
    """Forget the loaded table. For tests that supply their own."""
    global _TABLE
    _TABLE = None


# --- the shelf ---------------------------------------------------------------
def offers(run) -> tuple[Offer, ...]:
    """The gear a stall at this point in this run has on it.

    Distinct pieces, sampled without replacement, each with its own rarity roll
    off the same stream -- so which piece is on key 1 and how good it is are part
    of the one roll rather than two decisions.

    **Derived, never held.** Called twice with the same run at the same index it
    returns the same thing, which is what lets the scene roll on the tick the
    fixture is touched and a scene rebuilt from a save roll again and agree.

    The count is `data/rooms.json`'s, because how much a *room* offers is that
    file's business; what is in the pool is this one's. The upper bound is
    checked here rather than there for the reason `progression.offers` gives.
    """
    pool = table().pieces
    count = rooms.table().stall_offers
    if not 0 <= count <= len(pool):
        raise ValueError(
            f"a stall cannot offer {count} of the {len(pool)} pieces there are; "
            f"see 'stall.offers' in data/rooms.json"
        )
    if count == 0:
        return ()

    # `index` is the arena just cleared, so the floor standing in this room is
    # `index + 1` -- the same figure `Run._enter_room` hands `Purse(floor=...)`
    # and the same one `rooms.Table.chest_worth` is given.
    floor = run.index + 1
    stream = rooms.stall_stream(run.seed, run.index)
    gear = table()
    lot = loot.table()

    rolled = []
    for slot, piece in enumerate(stream.sample(pool, count)):
        rarity = lot.roll_rarity(stream)
        scale = gear.scale_of(rarity)
        block = piece.attributes.scaled(scale)
        rolled.append(
            Offer(
                key=f"eq:{run.index}:{slot}",
                piece_id=piece.id,
                name=piece.name,
                rarity=rarity,
                price=gear.price_on(piece.price, scale, floor),
                attributes=block,
                blurb=describe(block),
            )
        )
    return tuple(rolled)


# --- buying one --------------------------------------------------------------
def taken(run, offer: Offer) -> bool:
    """Whether this run has already bought this row.

    Recorded in `run.purchases`, which `save.py` already round-trips as a
    `dict[str, int]` -- so a greyed-out row survives being put down and picked
    up, with no save schema change and no migration. `offer.key` is namespaced
    with `eq:` and `shop.bought` only ever looks up its own five ids, so the two
    cannot collide.
    """
    return bool(run.purchases.get(offer.key, 0))


def available(run, offers: tuple[Offer, ...]) -> tuple[Offer, ...]:
    """The gear half of the shelf as this run sees it, in roll order.

    `shop.available`'s opposite number, and the pair of them are what the panel
    draws: a row is on the shelf while there is still a purchase in it. A gear
    row holds exactly one, so a bought piece leaves immediately -- there is no
    equivalent of the Poultice here.

    **Takes the rolled tuple rather than calling `offers` itself.** The roll
    belongs to the room and the scene is holding it, and re-deriving here would
    make the drawn shelf and the held one two calls that merely happen to agree
    -- the hazard `render/shop_panel.py` opens by explaining.

    Filtering here rather than in `offers` is the load-bearing half. `offers` is
    the room's roll and stays whole: `save.py` writes nothing about a shelf, so a
    reloaded run finds its rows by re-rolling and indexing, and a filtered roll
    would hand back a different piece at index 0 the moment anything was bought.
    What survives a save is `run.purchases`, and this reads it.
    """
    return tuple(offer for offer in offers if not taken(run, offer))


def can_buy(run, offer: Offer) -> bool:
    """Whether pressing the key would do anything.

    Deliberately the same two checks `buy` makes, and used by the panel to grey a
    row out -- so what a player is shown and what actually happens cannot
    disagree. The same contract `shop.can_buy` has with `shop.buy`.
    """
    return run.gold >= offer.price and not taken(run, offer)


def buy(run, offer: Offer) -> bool:
    """Spend, apply, and record. Returns False if nothing happened.

    No cap and no limit, unlike the Charm and the Tonic. Those are capped because
    they are on every shelf and compound; a rolled piece is on one shelf in one
    room and is gone when you walk out. What bounds gear is the roll and the
    price, not a tally.
    """
    if not can_buy(run, offer):
        return False

    # Both halves of the write, and the reason both are necessary is in
    # `progression.grant`. `shop._boots` and `progression.spend` go through the
    # same door.
    progression.grant(run, offer.attributes)

    run.gold -= offer.price
    run.purchases[offer.key] = 1
    return True
