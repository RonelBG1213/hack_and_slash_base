"""What gold buys, between one stage and the next.

Three goods, and every one of them is an integer on the `Run`. That is not a
limitation to be worked around later -- it is the whole design. `EntityType` is
frozen content shared by every run of that class, so anything touching a hero's
damage, speed or maximum health would need a per-`Entity` stat layer that every
lookup in the game went through. The shop deliberately sells nothing that needs
one.

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


EFFECTS = {
    "poultice": (_poultice, "+{amount} health, now"),
    "tonic": (_tonic, "+{amount} health back per stage"),
    "charm": (_charm, "+{amount}% gold from every drop"),
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
            )
        )

    missing = set(EFFECTS) - {good.id for good in goods}
    if missing:
        raise KeyError(
            f"game/shop.py can apply {', '.join(sorted(missing))}, but "
            "data/loot.json does not sell them -- they would be dead code"
        )
    return tuple(goods)


def bought(run, good: Good) -> int:
    return run.purchases.get(good.id, 0)


def sold_out(run, good: Good) -> bool:
    return good.limit > 0 and bought(run, good) >= good.limit


def can_buy(run, good: Good) -> bool:
    """Whether pressing the key would do anything.

    Deliberately the same three checks `buy` makes, and used by the panel to
    grey a row out -- so what a player is shown and what actually happens cannot
    disagree.
    """
    if run.gold < good.price or sold_out(run, good):
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
    if run.gold < good.price or sold_out(run, good):
        return False

    effect, _ = EFFECTS[good.id]
    if not effect(run, good.amount):
        return False

    run.gold -= good.price
    run.purchases[good.id] = bought(run, good) + 1
    return True
