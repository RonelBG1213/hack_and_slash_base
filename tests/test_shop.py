"""What gold buys, and the three ways a purchase can be refused.

Headless throughout. The shop is a pure function of a `Run` -- the scene decides
when to show it, and none of that is under test here.
"""

from __future__ import annotations

import pytest

from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.game import shop
from hack_and_slash.game.run import Run

from .helpers import BESTIARY, HERO, open_room


def campaign(count: int = 3) -> Campaign:
    room = open_room(20, 20)
    return Campaign(
        name="test shop",
        stages=tuple(
            Level(
                name=f"stage {i + 1}",
                rows=room.rows,
                hero_spawn=(4, 10),
                enemy_spawns=(EnemySpawn("grunt", (12, 10)),),
                tile=room.tile,
            )
            for i in range(count)
        ),
    )


def rich_run(gold: int = 10000) -> Run:
    run = Run.start(campaign(), BESTIARY)
    run.gold = gold
    return run


def good(good_id: str) -> shop.Good:
    for entry in shop.stock():
        if entry.id == good_id:
            return entry
    raise AssertionError(f"no '{good_id}' on the shelves")


# --- the shelves -------------------------------------------------------------
def test_the_shop_stocks_what_the_data_says() -> None:
    assert [g.id for g in shop.stock()] == ["poultice", "tonic", "charm"]


def test_every_good_has_a_price_an_amount_and_something_to_say() -> None:
    for entry in shop.stock():
        assert entry.price > 0, f"{entry.id} is free"
        assert entry.amount > 0, f"{entry.id} does nothing"
        assert entry.blurb, f"{entry.id} tells the player nothing"


def test_the_permanent_goods_are_capped_and_the_consumable_is_not() -> None:
    """Uncapped, the correct play is to buy nothing but Charms early, and the
    shop stops being a decision."""
    assert good("poultice").limit == 0
    assert good("tonic").limit > 0
    assert good("charm").limit > 0


def test_stock_and_effects_are_checked_against_each_other(monkeypatch) -> None:
    """A good in the data with no effect would be silently unbuyable.

    Silent is the problem. It loads, it draws, it takes a keypress, and nothing
    happens -- which looks like a bug in the input layer rather than a typo in a
    content file.
    """
    from hack_and_slash.game import loot

    broken = loot.LootTable(
        gold_base=1.0, floor_step=0.0, variance=0.0, item_chance=0.0, scatter=0.0,
        tiers=loot.table().tiers,
        shop={"elixir": {"name": "Elixir", "price": 10, "amount": 1, "limit": 0}},
    )
    monkeypatch.setattr(loot, "_TABLE", broken)

    with pytest.raises(KeyError, match="elixir"):
        shop.stock()


# --- buying ------------------------------------------------------------------
def test_a_poultice_heals_and_costs_what_it_says() -> None:
    run = rich_run()
    run.world.hero.hp = 40
    before = run.gold

    assert shop.buy(run, good("poultice"))
    assert run.world.hero.hp == 40 + good("poultice").amount
    assert run.gold == before - good("poultice").price


def test_a_poultice_never_takes_you_above_full_health() -> None:
    run = rich_run()
    run.world.hero.hp = HERO.hp - 2

    assert shop.buy(run, good("poultice"))
    assert run.world.hero.hp == HERO.hp


def test_a_poultice_at_full_health_is_refused_rather_than_wasted() -> None:
    """The one good that can be useless rather than merely unaffordable.

    Taking the gold and doing nothing is the behaviour a player would call a
    bug, so it is refused -- and `can_buy` says the same thing, which is what
    the panel greys the row out with.
    """
    run = rich_run()
    before = run.gold

    assert not shop.can_buy(run, good("poultice"))
    assert not shop.buy(run, good("poultice"))
    assert run.gold == before


def test_a_tonic_raises_the_heal_for_every_stage_after_it() -> None:
    run = rich_run()
    assert shop.buy(run, good("tonic"))
    assert run.bonus_heal == good("tonic").amount


def test_a_charm_raises_gold_find_by_the_percentage_it_says() -> None:
    run = rich_run()
    assert shop.buy(run, good("charm"))
    assert run.gold_find == pytest.approx(good("charm").amount / 100.0)


def test_the_permanent_goods_stack_up_to_their_cap() -> None:
    run = rich_run()
    tonic = good("tonic")

    for bought in range(tonic.limit):
        assert shop.buy(run, tonic), f"tonic {bought + 1} was refused early"

    assert shop.bought(run, tonic) == tonic.limit
    assert shop.sold_out(run, tonic)
    assert not shop.buy(run, tonic), "the cap did not hold"
    assert run.bonus_heal == tonic.amount * tonic.limit


def test_nothing_can_be_bought_without_the_gold_for_it() -> None:
    run = rich_run(gold=0)
    for entry in shop.stock():
        assert not shop.can_buy(run, entry)
        assert not shop.buy(run, entry)
    assert run.gold == 0


def test_a_refused_purchase_leaves_the_run_exactly_as_it_was() -> None:
    run = rich_run(gold=1)
    before = (run.gold, run.bonus_heal, run.gold_find, dict(run.purchases))

    for entry in shop.stock():
        shop.buy(run, entry)

    assert (run.gold, run.bonus_heal, run.gold_find, run.purchases) == before


def test_gold_cannot_be_spent_into_debt() -> None:
    run = rich_run(gold=good("charm").price)
    assert shop.buy(run, good("charm"))
    assert run.gold == 0

    for entry in shop.stock():
        shop.buy(run, entry)
    assert run.gold == 0


def test_what_is_bought_carries_but_a_restart_does_not_keep_it() -> None:
    run = rich_run()
    shop.buy(run, good("tonic"))
    shop.buy(run, good("charm"))

    fresh = run.restart()
    assert fresh.purchases == {}
    assert fresh.bonus_heal == 0
    assert fresh.gold_find == 0.0
