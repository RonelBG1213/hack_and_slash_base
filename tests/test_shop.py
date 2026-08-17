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
from hack_and_slash.game.sim import step

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
    # Order is content, not a sort: it is the order the panel draws and
    # therefore which good sits on which digit.
    assert [g.id for g in shop.stock()] == [
        "poultice",
        "tonic",
        "charm",
        "boots",
        "elixir",
    ]


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
        # A name nothing in EFFECTS knows. It used to be "elixir", which became
        # a real good -- so this now names something no shelf will ever hold.
        shop={"philtre": {"name": "Philtre", "price": 10, "amount": 1, "limit": 0}},
    )
    monkeypatch.setattr(loot, "_TABLE", broken)

    with pytest.raises(KeyError, match="philtre"):
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


# --- the late shelf ----------------------------------------------------------
# A forty-stage run banks roughly three times what a twenty-stage one did, so
# the three original goods were bought out around the halfway mark and left
# twenty stages with nothing to decide. The Elixir is the answer, and it is
# stocked by stage number rather than by gold -- so it arrives at a point in the
# campaign rather than at a point in somebody's luck.
def run_on_stage(stage_number: int, gold: int = 100000) -> Run:
    run = Run.start(campaign(40), BESTIARY, at_stage=stage_number - 1)
    run.gold = gold
    return run


def test_the_late_good_is_not_on_the_shelves_early() -> None:
    early = shop.available(run_on_stage(1))
    assert [g.id for g in early] == ["poultice", "tonic", "charm", "boots"]


def test_the_late_good_appears_on_the_stage_its_data_names() -> None:
    unlocks = good("elixir").unlocks_at
    assert unlocks > 1, "an unlock of 0 or 1 means the good is simply always stocked"

    assert "elixir" not in [g.id for g in shop.available(run_on_stage(unlocks - 1))]
    assert "elixir" in [g.id for g in shop.available(run_on_stage(unlocks))]


def test_the_late_good_cannot_be_bought_before_it_is_stocked() -> None:
    """The panel would not draw a row for it, but nothing stops a caller.

    Worth pinning rather than assuming: `available` is what the panel and the
    key handler agree on, and a `buy` that ignored it would make the shelf
    cosmetic.
    """
    run = run_on_stage(1)
    assert not shop.can_buy(run, good("elixir"))
    assert not shop.buy(run, good("elixir"))
    assert run.bonus_heal == 0


def test_the_late_good_adds_to_the_heal_the_tonic_writes() -> None:
    """The same dial on purpose. What the late run is short of is not a
    mechanic, it is anything left worth buying."""
    run = run_on_stage(good("elixir").unlocks_at)

    assert shop.buy(run, good("tonic"))
    assert shop.buy(run, good("elixir"))
    assert run.bonus_heal == good("tonic").amount + good("elixir").amount


def test_available_is_stock_filtered_by_where_the_run_is() -> None:
    """What `available` exists to guarantee.

    The panel draws this list and the key handler indexes into it, so a row and
    its key are the same digit in both halves of the campaign. The other half of
    that contract -- that the panel has a key for every row it can draw -- is in
    `test_render.py`, where the keys live.
    """
    for stage_number in (1, good("elixir").unlocks_at, 40):
        rows = shop.available(run_on_stage(stage_number))
        assert rows == tuple(g for g in shop.stock() if g.unlocks_at <= stage_number)


# --- the boots, and the one good that writes an attribute --------------------
def test_the_boots_write_both_halves_of_the_stat_layer() -> None:
    """`run.earned` is what survives a stage boundary; `hero.bonus` is what the
    sim reads in the stage being played. Writing only one is a purchase that
    either does nothing now or goes quiet at the next transition, and neither
    failure says a word at the point of sale."""
    run = rich_run()
    boots = good("boots")

    assert shop.buy(run, boots)
    assert run.earned.move_speed == boots.amount * 10, "per-mille, not percent"
    assert run.world.hero.attrs.move_speed == boots.amount * 10


def test_the_boots_move_the_hero_and_leave_everything_else_alone() -> None:
    """The point of the good, and the guarantee underneath it: one attribute
    moves and the other seven do not."""
    import dataclasses

    run = rich_run()
    shop.buy(run, good("boots"))

    for field in dataclasses.fields(run.earned):
        if field.name == "move_speed":
            continue
        assert getattr(run.earned, field.name) == 0, f"the boots moved {field.name}"


def test_the_boots_survive_the_stage_boundary() -> None:
    """The half a one-sided implementation loses. `Run._advance` hands the next
    `World` the earned block, so speed bought in act I is still there in act II
    -- the same road `progression.spend` travels and for the same reason."""
    run = rich_run()
    shop.buy(run, good("boots"))
    bought = run.earned.move_speed

    for enemy in run.world.enemies():
        enemy.hp = 0
    # A tick, because `sim._settle` is what judges the stage -- killing the
    # roster is not the same as the world having noticed.
    step(run.world)
    run.settle()

    assert run.just_advanced, "the stage did not turn over"
    assert run.world.hero.attrs.move_speed == bought


def test_the_boots_are_capped() -> None:
    """Speed compounds against a game with no pathing, where outrunning a crowd
    is the hero's main tool -- so it is capped for the reason the Charm is."""
    run = rich_run(gold=1000000)
    boots = good("boots")
    assert boots.limit > 0, "an uncapped speed good is the only thing worth buying"

    for _ in range(boots.limit):
        assert shop.buy(run, boots)

    assert not shop.buy(run, boots), "the cap did not hold"
    assert run.earned.move_speed == boots.amount * 10 * boots.limit
