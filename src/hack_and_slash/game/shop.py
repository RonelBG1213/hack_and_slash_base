"""What gold buys, between one stage and the next.

Four goods, and every one of them is an integer on the `Run`. That is not a
limitation to be worked around later -- it is the whole design. `EntityType` is
frozen content shared by every run of that class, so anything touching a hero's
damage, speed or maximum health would need a per-`Entity` stat layer that every
lookup in the game went through. The shop deliberately sells nothing that needs
one.

The fourth good does not appear until the second half of the campaign. A forty-
stage run banks roughly three times what a twenty-stage run did, and against
three capped goods that meant every permanent bought out around the halfway
mark with twenty stages left to spend nothing on. A late shelf is the cheapest
answer that keeps the shop a decision to the end -- and it is stocked by stage
number rather than by gold, so it arrives at a point in the story rather than
at a point in somebody's luck.

Prices and amounts come from `data/loot.json`; what a good actually *does* is
code, because it is a line of behaviour rather than a number. The two are
checked against each other at load, so a good added to the data without an
effect fails loudly instead of being silently unbuyable.

Pure Python -- no pygame. The scene decides when to offer the shop; this decides
what happens when something is bought.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import loot


@dataclass(frozen=True)
class Good:
    """One line of stock.

    `limit` of 0 means no limit, which is only true of the Poultice -- the two
    permanent goods are capped because they compound. Four Tonics is more health
    back after every remaining stage than most classes start with; three Charms
    is +75% on everything that drops for the rest of the run. Uncapped, the
    correct play is to buy nothing but Charms early and the shop stops being a
    decision.
    """

    id: str
    name: str
    price: int
    amount: int
    limit: int

    #: Already formatted with the amount, so the panel renders it as-is.
    blurb: str

    #: The first stage this is on the shelf for, 1-based. 0 means always.
    #:
    #: A shelf rather than a fifth field on three goods that ignore it: what it
    #: buys is a shop that still has something to decide in act VIII, without
    #: making the early shop longer or the early decision harder.
    unlocks_at: int = 0


#: What each good does, and the line a player reads. Keyed by the id in
#: `data/loot.json`.
#:
#: The description is a template rather than a sentence because the amount is
#: data and the wording is not -- the Charm's amount is percentage points and
#: the Tonic's is health, and only the template knows which. Kept short on
#: purpose: the panel gives it about 150 pixels before it runs into the
#: sold-out tally, and a blurb that overflows is worse than no blurb.
#:
#: Each effect takes the run and the amount and returns whether it did anything.
#: Returning False is how "you are already at full health" is expressed -- the
#: purchase is refused rather than taking the gold for nothing, and the panel
#: greys the row out for the same reason.
def _poultice(run, amount: int) -> bool:
    hero = run.world.hero
    if hero is None or hero.hp >= hero.type.hp:
        return False
    hero.hp = min(hero.type.hp, hero.hp + amount)
    return True


def _tonic(run, amount: int) -> bool:
    run.bonus_heal += amount
    return True


def _charm(run, amount: int) -> bool:
    # Stored as a fraction because that is how the loot table uses it; the data
    # says 25 because percentage points are what a player is being shown.
    run.gold_find += amount / 100.0
    return True


def _elixir(run, amount: int) -> bool:
    # The same dial the Tonic writes, deliberately. A second effect that did
    # something new would need somewhere new to live; what the late run is short
    # of is not a mechanic, it is anything left worth buying.
    run.bonus_heal += amount
    return True


EFFECTS = {
    "poultice": (_poultice, "+{amount} health, now"),
    "tonic": (_tonic, "+{amount} health back per stage"),
    "charm": (_charm, "+{amount}% gold from every drop"),
    "elixir": (_elixir, "+{amount} health back per stage"),
}


def stock() -> tuple[Good, ...]:
    """The shop's shelves, in the order `data/loot.json` lists them.

    Order is content: it is the order the panel draws and therefore which good
    is on key 1. Taken from the file rather than sorted, so rearranging the shop
    means rearranging the JSON.
    """
    goods = []
    for good_id, entry in loot.table().shop.items():
        if good_id not in EFFECTS:
            raise KeyError(
                f"data/loot.json sells '{good_id}', which nothing in "
                f"game/shop.py knows how to apply; known goods: "
                f"{', '.join(sorted(EFFECTS))}"
            )
        _, template = EFFECTS[good_id]
        amount = int(entry["amount"])
        goods.append(
            Good(
                id=good_id,
                name=entry.get("name", good_id),
                price=int(entry["price"]),
                amount=amount,
                limit=int(entry.get("limit", 0)),
                blurb=template.format(amount=amount),
                unlocks_at=int(entry.get("unlocks_at", 0)),
            )
        )

    missing = set(EFFECTS) - {good.id for good in goods}
    if missing:
        raise KeyError(
            f"game/shop.py can apply {', '.join(sorted(missing))}, but "
            "data/loot.json does not sell them -- they would be dead code"
        )
    return tuple(goods)


def available(run) -> tuple[Good, ...]:
    """The shelves as this run sees them, in stock order.

    **This, not `stock()`, is what the panel draws and what the keys index
    into.** The two agree for the first twenty stages and differ after, and a
    caller that used `stock()` for one and this for the other would put a
    player's key 4 on a row that is not there.
    """
    return tuple(
        good for good in stock() if good.unlocks_at <= run.stage_number
    )


def bought(run, good: Good) -> int:
    return run.purchases.get(good.id, 0)


def sold_out(run, good: Good) -> bool:
    return good.limit > 0 and bought(run, good) >= good.limit


def stocked(run, good: Good) -> bool:
    """Whether this run has reached the stage the good goes on sale."""
    return good.unlocks_at <= run.stage_number


def can_buy(run, good: Good) -> bool:
    """Whether pressing the key would do anything.

    Deliberately the same three checks `buy` makes, and used by the panel to
    grey a row out -- so what a player is shown and what actually happens cannot
    disagree.
    """
    if run.gold < good.price or sold_out(run, good) or not stocked(run, good):
        return False
    if good.id == "poultice":
        # The one good that can be useless rather than merely unaffordable.
        hero = run.world.hero
        return hero is not None and hero.hp < hero.type.hp
    return True


def buy(run, good: Good) -> bool:
    """Spend, apply, and record. Returns False if nothing happened.

    The effect runs *before* the gold moves, so a good that turns out to do
    nothing -- a Poultice at full health -- costs nothing. Taking payment first
    and refunding it would work too, and would be one more place for the two
    numbers to disagree.
    """
    if run.gold < good.price or sold_out(run, good) or not stocked(run, good):
        return False

    effect, _ = EFFECTS[good.id]
    if not effect(run, good.amount):
        return False

    run.gold -= good.price
    run.purchases[good.id] = bought(run, good) + 1
    return True
