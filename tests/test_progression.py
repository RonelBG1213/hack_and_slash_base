"""Experience, levels, and spending the points they pay out.

The shipped table has `xp_base: 0`, so the layer is inert in the real game and
almost everything here runs against a deliberately generous table swapped in for
the duration of a test. The one exception is
`test_the_shipped_table_ships_switched_off`, which is the whole reason the
recorded balance grid is still a fixed reference -- and it reads the real file.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.game import progression
from hack_and_slash.game.attributes import NEUTRAL, Attributes
from hack_and_slash.game.autoplay import into, play_run_out, spread
from hack_and_slash.game.progression import Curve, Table
from hack_and_slash.game.run import Run
from hack_and_slash.game.sim import step

from .helpers import BESTIARY, HERO, open_room

#: Levels cost 100, 150, 200...; a grunt is level 2 and so pays 20.
GENEROUS = Table(
    xp_base=10,
    curve=Curve(first=100, step=50, max_level=5, points_per_level=3),
    points=dict.fromkeys(progression.SPENDABLE, 1) | {"max_hp": 4},
)


@contextmanager
def table(swap: Table):
    """Swap the progression table for the duration of a block.

    Monkeypatched rather than injected, for the reason `test_loot.py` gives
    about its own table: the game has one, and inventing a seam to have two
    would be a worse design than a test that puts it back afterwards.
    """
    original = progression._TABLE
    progression._TABLE = swap
    try:
        yield swap
    finally:
        progression._TABLE = original


def campaign(count: int = 3) -> Campaign:
    room = open_room(20, 20)
    return Campaign(
        name="test progression",
        stages=tuple(
            Level(
                name=f"stage {i + 1}",
                rows=room.rows,
                hero_spawn=(4, 10),
                enemy_spawns=(EnemySpawn("grunt", (12, 10)), EnemySpawn("grunt", (13, 10))),
                tile=room.tile,
            )
            for i in range(count)
        ),
    )


def clear_current_stage(run: Run) -> None:
    """Kill everything, then walk out of the reward room that follows.

    Both halves, so this still means "the run is standing at the start of the
    next arena" -- which is what every assertion below is about. Straight to a
    door and not past the fixture in the middle: a fountain healing on the way
    through would put a second source of health inside tests written to pin the
    between-stage heal exactly.
    """
    for enemy in run.world.enemies():
        enemy.hp = 0
    step(run.world)
    run.settle()

    if run.room is not None:
        door = [prop for prop in run.world.props if prop.is_door][0]
        run.world.hero.pos = door.pos
        step(run.world)
        run.settle()


# --- the switch --------------------------------------------------------------
def test_the_shipped_table_ships_switched_off() -> None:
    """The load-bearing test in this file.

    `xp_base: 0` is what makes "the attribute layer moved no recorded number" a
    fact about the shipped game rather than a claim about a code path. If this
    ever goes green-to-red because somebody turned progression on, the 280-cell
    grid needs re-baselining and `tools/balance.py --class all` is the gate --
    see the warning at the top of `data/progression.json`.
    """
    shipped = Table.load()
    assert shipped.is_off
    assert shipped.xp_for(monster_level=12) == 0


def test_nothing_is_earned_while_the_table_is_off() -> None:
    run = Run.start(campaign(), BESTIARY)
    clear_current_stage(run)

    assert (run.xp, run.hero_level, run.unspent_points) == (0, 1, 0)
    assert run.earned == NEUTRAL
    assert run.world.hero.bonus == NEUTRAL


def test_a_table_must_price_every_attribute_and_invent_none() -> None:
    """Bidirectional, the way `shop.stock()` validates its goods. An attribute
    left out is silently unspendable; one invented is a typo costing nothing."""
    with pytest.raises(KeyError):
        GENEROUS.gain("luck", 1)


# --- earning -----------------------------------------------------------------
def test_killing_things_banks_experience_on_the_run() -> None:
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        clear_current_stage(run)
        # Two grunts at level 2, ten per level -- forty, short of the hundred a
        # level costs, so it sits as progress rather than levelling.
        assert run.xp == 40
        assert run.hero_level == 1


def test_experience_is_progress_to_the_next_level_not_a_lifetime_total() -> None:
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.world.xp = 260  # two levels' worth: 100 then 150, with 10 over
        run._bank()

        assert run.hero_level == 3
        assert run.xp == 10, "the cost was not taken off"
        assert run.unspent_points == 6


def test_one_stage_can_carry_more_than_one_level() -> None:
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.world.xp = 10_000
        run._bank()
        assert run.hero_level == GENEROUS.curve.max_level


def test_the_level_cap_stops_the_points_as_well_as_the_level() -> None:
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.world.xp = 10_000
        run._bank()
        capped = run.unspent_points

        run.world.xp = 10_000
        run._bank()
        assert run.unspent_points == capped, "banked past the cap"


def test_experience_draws_no_random_numbers() -> None:
    """The one subsystem added to this game that needed no stream of its own.

    Asserted rather than assumed, because the cost of being wrong is every
    recorded number in the project quietly changing meaning.
    """
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        before = (
            run.world.rng.getstate(),
            run.world.loot_rng.getstate(),
            run.world.attr_rng.getstate(),
        )
        run.world.xp = 5000
        run._bank()

        assert before == (
            run.world.rng.getstate(),
            run.world.loot_rng.getstate(),
            run.world.attr_rng.getstate(),
        )


# --- spending ----------------------------------------------------------------
def test_a_point_buys_what_the_table_says_and_reaches_the_body() -> None:
    """Both halves, and the test exists because writing only one is the easy
    mistake: `run.earned` alone is inert until the next stage, and
    `hero.bonus` alone is lost at that boundary."""
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.unspent_points = 3

        assert progression.spend(run, "max_hp", 2)
        assert run.earned.max_hp == 8
        assert run.world.hero.bonus.max_hp == 8
        assert run.world.hero.max_hp == HERO.hp + 8
        assert run.unspent_points == 1


def test_spending_more_than_is_banked_is_refused_not_clamped() -> None:
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.unspent_points = 1

        assert not progression.spend(run, "damage", 2)
        assert run.earned == NEUTRAL, "a partial purchase happened anyway"
        assert run.unspent_points == 1


def test_what_is_spent_survives_the_next_stage() -> None:
    """`_advance` builds a whole new `World`, hero included. Without handing the
    earned block to its constructor, everything the run had earned would be left
    behind on the old body."""
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.unspent_points = 3
        progression.spend(run, "max_hp", 3)

        clear_current_stage(run)
        assert run.index == 1
        assert run.world.hero.bonus.max_hp == 12
        assert run.world.hero.max_hp == HERO.hp + 12


def test_earned_health_raises_the_ceiling_the_between_stage_heal_fills_to() -> None:
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.unspent_points = 5
        progression.spend(run, "max_hp", 5)  # +20
        run.world.hero.hp = 1

        clear_current_stage(run)
        assert run.max_hp == HERO.hp + 20
        assert run.world.hero.hp == 1 + HERO.heal_between_stages


def test_a_restart_gives_the_levels_back() -> None:
    """`restart()` rebuilds through `Run.start`, so this needs no code of its
    own -- which is exactly why it is worth pinning."""
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY)
        run.unspent_points = 3
        progression.spend(run, "damage", 3)
        run.hero_level = 4
        run.xp = 55

        fresh = run.restart()
        assert (fresh.xp, fresh.hero_level, fresh.unspent_points) == (0, 1, 0)
        assert fresh.earned == NEUTRAL
        assert fresh.world.hero.bonus == NEUTRAL


def test_what_is_spent_survives_a_promotion() -> None:
    """Promotion swaps `Entity.type` on a live body. `bonus` lives on the body,
    not on the type, so it has to come through the fork -- otherwise a run loses
    everything it earned at the exact midpoint of itself."""
    from hack_and_slash.game import jobs

    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY, hero_type_id="knight")
        run.unspent_points = 4
        progression.spend(run, "max_hp", 4)  # +16

        assert jobs.promote(run, BESTIARY["dark_knight"])
        assert run.world.hero.bonus.max_hp == 16
        assert run.world.hero.max_hp == BESTIARY["dark_knight"].hp + 16


def test_earned_health_is_on_the_body_before_the_carry_is_clamped() -> None:
    """The ordering bug this test was written for.

    `_advance` works out what carries using the run's effective maximum, then
    builds a `World`, which clamps the arriving hero against *its* maximum. If
    the earned attributes are handed over after construction, that clamp runs
    against the class's bare health and quietly clips off exactly the health the
    levelling bought -- so +20 maximum health would let a hero carry more and
    then take it away again on the same tick.

    Only visible above the class's own maximum, which is why the other carry
    tests here do not catch it.
    """
    with table(GENEROUS):
        run = Run.start(campaign(), BESTIARY, hero_type_id="knight")
        run.unspent_points = 6
        progression.spend(run, "max_hp", 6)  # +24, so 154 against the Knight's 130

        run.world.hero.hp = run.max_hp  # full, and above what the class alone allows
        clear_current_stage(run)

        assert run.max_hp == HERO.hp + 24
        assert run.world.hero.max_hp == HERO.hp + 24
        assert run.world.hero.hp == HERO.hp + 24, "the carry was clamped to the bare class"


# --- what a shrine puts on its plinth ----------------------------------------
def test_a_shrine_offers_distinct_attributes() -> None:
    """Sampled without replacement, for the reason `rooms.offer` samples doors
    that way: two identical rows read as a bug rather than as a repeated
    option."""
    for index in range(39):
        offered = progression.offers(7, index, 3)
        assert len(offered) == 3
        assert len(set(offered)) == 3


def test_the_same_shrine_offers_the_same_three() -> None:
    """The determinism claim, and the reason no save field was needed for it.

    Built from `(seed, index)` and thrown away, so a run loaded off disk finds
    the plinth it was standing at when it was put down.
    """
    for index in range(39):
        assert progression.offers(7, index, 3) == progression.offers(7, index, 3)


def test_a_different_seed_is_a_different_run_of_shrines() -> None:
    plinths = {progression.offers(seed, 0, 3) for seed in range(12)}
    assert len(plinths) > 1, "every seed rolled the same first shrine"


def test_a_different_shrine_is_a_different_three() -> None:
    plinths = {progression.offers(7, index, 3) for index in range(39)}
    assert len(plinths) > 1, "every shrine in a run offers the same three"


def test_every_attribute_a_shrine_can_offer_is_spendable() -> None:
    """So a ninth attribute is offerable on the day it is declared, rather than
    on the day somebody remembers to add it to a list here."""
    seen = {
        name
        for seed in range(12)
        for index in range(39)
        for name in progression.offers(seed, index, 3)
    }
    assert seen <= set(progression.SPENDABLE)
    assert seen == set(progression.SPENDABLE), (
        f"never offered: {sorted(set(progression.SPENDABLE) - seen)}"
    )


def test_offering_everything_is_the_shrine_exactly_as_it_was() -> None:
    """`shrine.offers: 8` in `data/rooms.json`, the narrow rollback."""
    assert set(progression.offers(7, 3, len(progression.SPENDABLE))) == set(
        progression.SPENDABLE
    )


def test_offering_nothing_is_an_empty_plinth() -> None:
    assert progression.offers(7, 3, 0) == ()


def test_more_offers_than_attributes_is_refused() -> None:
    """Raised here rather than as random's "Sample larger than population",
    which would point at nothing."""
    with pytest.raises(ValueError, match="shrine.offers"):
        progression.offers(7, 3, len(progression.SPENDABLE) + 1)


def test_the_shipped_shrine_count_is_offerable() -> None:
    """Ties the number in the data file to the bound this module enforces."""
    from hack_and_slash.game import rooms

    progression.offers(7, 0, rooms.table().shrine_offers)


# --- the instrument ----------------------------------------------------------
# `autoplay` can now spend what a run earns. It ships not doing so, because that
# is the hero every cell of the recorded balance grid was measured against --
# see the note on `play_run_out`. These pin both halves of that: that the
# default is still the old instrument exactly, and that the new one works.
def played_out(allocate=None, seed: int = 1) -> Run:
    """A whole run, driven the way `tools/balance.py` drives one.

    Eight stages rather than the three the rest of this file uses, because a
    point is spent on a *transition* and the last bank of a run has none after
    it. A campaign short enough that the only level lands on the final stage
    would report "the bot never spends" about a bot that spends.
    """
    run = Run.start(campaign(8), BESTIARY, seed=seed)
    play_run_out(run, limit=80_000, allocate=allocate)
    return run


def test_the_reference_bot_still_spends_nothing_by_default() -> None:
    """The load-bearing one.

    `allocate=None` is the default, and every recorded number in
    `docs/balance.md` was measured through it. A run that levels up under a
    generous table and *still* reaches the end holding a neutral block is what
    makes adding the argument a change to nothing.
    """
    with table(GENEROUS):
        run = played_out()

    assert run.unspent_points > 0, "the table was not generous enough to test this"
    assert run.earned == NEUTRAL
    assert run.world.hero is None or run.world.hero.bonus == NEUTRAL


def test_a_bot_that_allocates_arrives_holding_nothing() -> None:
    with table(GENEROUS):
        run = played_out(allocate=spread)

    assert run.unspent_points == 0, "points were banked and never spent"
    assert run.earned != NEUTRAL


def test_allocating_is_inert_while_the_table_is_off() -> None:
    """The argument cannot move the grid on its own.

    Shipped table, so nothing is earned, so the most spendthrift policy in the
    module has nothing to spend -- which is why teaching the bot to allocate and
    turning `xp_base` up are two commits rather than one.
    """
    run = played_out(allocate=spread)

    assert (run.xp, run.hero_level, run.unspent_points) == (0, 1, 0)
    assert run.earned == NEUTRAL


def test_spread_puts_one_point_into_each_attribute_in_turn() -> None:
    picks = [spread(None, nth) for nth in range(len(progression.SPENDABLE) * 2)]

    assert picks[: len(progression.SPENDABLE)] == list(progression.SPENDABLE)
    assert picks[len(progression.SPENDABLE) :] == list(progression.SPENDABLE)


def test_spread_holds_no_cursor_of_its_own() -> None:
    """The reason `nth` is an argument rather than state on the policy.

    Two runs measured in one process share the policy object -- `tools/balance.py`
    passes the same one to eight seeds in a row -- and a cursor kept on it would
    make the second run start wherever the first stopped. Identical seeds must
    spend identically however many ran before them.
    """
    with table(GENEROUS):
        first = played_out(allocate=spread)
        second = played_out(allocate=spread)

    assert first.earned == second.earned


def test_into_puts_the_whole_budget_in_one_place() -> None:
    with table(GENEROUS):
        run = played_out(allocate=into("max_hp"))

    assert run.earned.max_hp > 0
    assert run.earned == Attributes(max_hp=run.earned.max_hp)


def test_into_refuses_an_attribute_that_does_not_exist() -> None:
    """Loud at the flag rather than silent for the length of a sweep. Every
    point into a typo reports as 'levelling changes nothing', which is a
    plausible-looking answer to the question being asked."""
    with pytest.raises(KeyError):
        into("luck")


def test_a_policy_that_holds_its_points_is_not_an_infinite_loop() -> None:
    with table(GENEROUS):
        run = played_out(allocate=lambda run, nth: "")

    assert run.unspent_points > 0
    assert run.earned == NEUTRAL


def test_what_the_bot_spends_reaches_the_body_it_is_playing() -> None:
    """Both halves of `grant`, through the instrument rather than through a
    direct call: a policy that wrote only `run.earned` would look right here
    until the assertion is about the hero standing in the arena."""
    with table(GENEROUS):
        run = Run.start(campaign(8), BESTIARY, seed=1)
        play_run_out(run, limit=80_000, allocate=into("max_hp"))
        if run.world.hero is not None:
            assert run.world.hero.bonus == run.earned
            assert run.world.hero.max_hp == run.hero_type.full_hp + run.earned.max_hp
