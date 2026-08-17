"""Promotion: swapping the class on a live body, once, halfway through a run.

What these pin is the *mechanism*, not the ten classes' numbers. The numbers are
a first pass -- the reference bot plays light-only, and an advanced class's
light is the one it inherited, so a sweep of acts V-VIII still cannot see a
heavy or an ultimate -- and asserting any of them would be pinning a guess.
What is
asserted is everything that would be a bug rather than a balance question: the
body keeps its identity, health carries as a proportion, and a run can only do
this once.
"""

from __future__ import annotations

import pytest

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import jobs, skills
from hack_and_slash.game.run import Run

from .helpers import BESTIARY
from .test_run import campaign


def a_run(hero: str = "knight") -> Run:
    return Run.start(campaign(3), BESTIARY, seed=5, hero_type_id=hero)


def first_offer(run: Run):
    return jobs.offers_for(run)[0]


# --- what is on the table ----------------------------------------------------
def test_every_class_is_offered_its_own_two_promotions() -> None:
    """The panel indexes straight into this, so the order is what keys 1 and 2
    do -- and every one of them has to descend from the class being played."""
    for cls in BESTIARY.hero_classes:
        run = a_run(cls.id)
        offers = jobs.offers_for(run)
        assert len(offers) == 2
        assert all(o.promotes_from == cls.id for o in offers)
        assert jobs.can_promote(run)


def test_nothing_is_offered_twice() -> None:
    """One promotion per run. The offer disappearing is what closes the panel,
    so this is also what stops it reopening on the next settle."""
    run = a_run()
    assert jobs.promote(run, first_offer(run))
    assert jobs.offers_for(run) == ()
    assert not jobs.can_promote(run)


def test_a_class_with_no_promotions_declared_offers_nothing() -> None:
    """The feature's off switch: delete the advanced entries from the JSON and
    this returns empty, the panel never opens, and no code is removed."""
    run = a_run()
    run.hero_type_id = "sovereign"  # nothing promotes from a boss
    assert jobs.offers_for(run) == ()


# --- what promotion does to the body -----------------------------------------
def test_promotion_swaps_the_type_on_the_hero_already_standing_there() -> None:
    """It cannot work any other way. `Run._advance` builds the next world -- hero
    included -- before the panel is ever shown, so by the time a player chooses,
    the body that choice applies to already exists."""
    run = a_run()
    hero = run.world.hero
    before_id = hero.id
    chosen = first_offer(run)

    assert jobs.promote(run, chosen)

    assert run.world.hero is hero, "promotion replaced the body instead of retyping it"
    assert hero.id == before_id
    assert hero.type is chosen
    assert run.job_id == chosen.id


def test_health_carries_as_a_proportion_never_as_a_number() -> None:
    """An advanced class has a different maximum, so copying the raw value would
    make promoting into a bigger class a stealth heal and a smaller one a stealth
    wound. The choice must cost and grant nothing on its own."""
    run = a_run("knight")
    hero = run.world.hero
    hero.hp = hero.max_hp // 2  # 65 of 130

    dark_knight = BESTIARY["dark_knight"]  # 115 max, fewer than the Knight's 130
    assert jobs.promote(run, dark_knight)

    assert hero.max_hp == 115
    assert hero.hp == round(0.5 * 115)
    assert hero.health_fraction == pytest.approx(0.5, abs=0.01)


def test_promoting_at_full_health_arrives_at_full_health() -> None:
    run = a_run("knight")
    hero = run.world.hero
    assert hero.hp == hero.max_hp

    assert jobs.promote(run, BESTIARY["holy_knight"])  # 150, up from 130
    assert hero.hp == hero.max_hp == 150


def test_a_sliver_of_health_never_rounds_away_to_death() -> None:
    """Rounding a small fraction of a smaller maximum can reach zero, and a
    promotion that killed you would be the worst bug this file could miss."""
    run = a_run("knight")
    hero = run.world.hero
    hero.hp = 1

    assert jobs.promote(run, BESTIARY["dark_knight"])
    assert hero.hp >= 1
    assert hero.is_alive


def test_the_new_kit_starts_ready() -> None:
    """The heavy and ultimate at those indices are different attacks now, so a
    cooldown left from the old kit would gate a weapon that never fired."""
    run = a_run()
    hero = run.world.hero
    hero.skill_cooldowns[skills.HEAVY] = 200
    hero.skill_cooldowns[skills.ULTIMATE] = 1700

    assert jobs.promote(run, first_offer(run))

    assert hero.skill_cooldowns == {}
    assert hero.cooldown_on(skills.HEAVY) == 0
    assert hero.cooldown_on(skills.ULTIMATE) == 0


def test_promotion_leaves_the_body_pointing_at_its_light_attack() -> None:
    """Defensive, and cheap. `weapon_index` survives the type swap, so a stale
    index would be a hero winding up one attack and landing another -- the exact
    failure the boss weapon-order test exists to prevent elsewhere."""
    run = a_run()
    hero = run.world.hero
    hero.weapon_index = skills.ULTIMATE
    hero.hit_ids.add(99)

    assert jobs.promote(run, first_offer(run))

    assert hero.weapon_index == skills.LIGHT
    assert hero.hit_ids == set()


# --- refusals ----------------------------------------------------------------
def test_a_second_promotion_is_refused_rather_than_raising() -> None:
    """A double keypress on the panel is a state, not a programming error."""
    run = a_run()
    first = first_offer(run)
    assert jobs.promote(run, first)

    other = BESTIARY["holy_knight"] if first.id == "dark_knight" else BESTIARY["dark_knight"]
    assert jobs.promote(run, other) is False
    assert run.job_id == first.id
    assert run.world.hero.type is first


def test_promoting_into_another_class_s_branch_raises() -> None:
    """This one *is* a programming error. The panel can only offer what
    `offers_for` returned, so reaching it means something else called in with a
    class that does not descend from the one being played."""
    run = a_run("knight")
    with pytest.raises(ValueError, match="assassin"):
        jobs.promote(run, BESTIARY["assassin"])
    assert run.job_id == ""


def test_a_dead_hero_is_not_promoted() -> None:
    """Not reachable today -- a cleared stage always leaves one alive -- but
    `world.hero` is Optional, and silently declining beats raising at the moment
    somebody pressed a key."""
    run = a_run()
    run.world.entities = [e for e in run.world.entities if not e.is_hero]
    assert run.world.hero is None

    assert jobs.promote(run, BESTIARY["dark_knight"]) is False
    assert run.job_id == ""


# --- what it must not disturb ------------------------------------------------
def test_promotion_draws_no_random_numbers() -> None:
    """Neither stream may move. The loot layer's whole guarantee is that a roll
    in one place cannot shift a damage roll elsewhere, and a promotion that
    consumed from either would break a seeded run's replay."""
    run = a_run()
    combat_before = run.world.rng.getstate()
    loot_before = run.world.loot_rng.getstate()

    assert jobs.promote(run, first_offer(run))

    assert run.world.rng.getstate() == combat_before
    assert run.world.loot_rng.getstate() == loot_before


def test_a_restart_comes_back_as_the_class_the_run_began_as() -> None:
    """`job_id` sits beside `hero_type_id` rather than overwriting it precisely
    so this works without `restart` knowing promotion exists. Overwriting would
    make R begin a fresh run at stage one as a class the character select cannot
    offer and the balance grid has never seen."""
    run = a_run("rogue")
    assert jobs.promote(run, BESTIARY["assassin"])
    assert run.hero_type_id == "rogue"

    fresh = run.restart()
    assert fresh.hero_type_id == "rogue"
    assert fresh.job_id == ""
    assert fresh.world.hero.type is BESTIARY["rogue"]


def test_hero_type_follows_the_promotion() -> None:
    """Read by `_advance` for the between-stage heal and the health cap. Inert at
    the shipped trigger -- there is no stage after the one you promote for -- and
    written this way so moving the trigger earlier stays a one-line change."""
    run = a_run("priest")
    assert run.hero_type is BESTIARY["priest"]

    assert jobs.promote(run, BESTIARY["battle_priest"])
    assert run.hero_type is BESTIARY["battle_priest"]


# --- and then it has to fight ------------------------------------------------
def test_every_promoted_class_can_actually_swing_all_four_slots() -> None:
    """The gap between "the type swapped" and "the game still works".

    Twenty new weapons went in at once, several of them fans and several of them
    full circles. A malformed one -- a projectile with no speed, an arc the swing
    resolver cannot handle -- loads perfectly and fails on the tick it is first
    used, which is the last stage of a twenty-stage run.

    So every slot of every promoted class is actually fired at a real enemy in a
    real world, and the whole cycle is stepped out.
    """
    from hack_and_slash.game.intent import Intent
    from hack_and_slash.game.sim import step

    from .helpers import add_enemy, make_world

    for advanced in BESTIARY.advanced_classes:
        base = BESTIARY[advanced.promotes_from]
        run = a_run(base.id)
        hero = run.world.hero
        assert jobs.promote(run, advanced)

        add_enemy(run.world, "grunt", hero.pos + Vec2(18, 0))

        for slot in skills.SLOTS:
            hero.state_ticks = 0
            hero.skill_cooldowns.clear()
            weapon = advanced.weapons[slot]

            step(run.world, Intent(attack=True, weapon=slot, aim=Vec2(1, 0)))
            # Out the far side of the whole cycle, projectiles and all.
            for _ in range(weapon.total_ticks + 2):
                step(run.world)

        assert hero.is_alive, f"the {advanced.id} died to its own kit"


# --- the bot takes the same decision, at the same moment ---------------------
# Promotion used to be something only a keyboard could do, which was fine while
# it bought one fight. Half the campaign is fought promoted now, so a driver
# that cannot promote cannot measure any of it -- and one that promotes at a
# different moment than the scene does is measuring a game nobody plays.
def a_long_run(hero: str = "knight") -> Run:
    """Parked one stage short of the fork, on a campaign just long enough.

    `at_stage` rather than a real campaign so this costs two stages of ticks
    instead of twenty-one: what is under test is where the driver promotes, not
    whether a trivial arena can be cleared.
    """
    return Run.start(
        campaign(jobs.PROMOTION_STAGE),
        BESTIARY,
        seed=5,
        hero_type_id=hero,
        at_stage=jobs.PROMOTION_STAGE - 2,
    )


def test_the_driver_promotes_into_the_branch_it_was_given() -> None:
    from hack_and_slash.game.autoplay import play_run_out

    run = a_long_run()
    play_run_out(run, job="holy_knight")

    assert run.job_id == "holy_knight"
    assert run.world.hero.type.id == "holy_knight"


def test_the_driver_leaves_the_class_alone_when_given_no_branch() -> None:
    """The default, and the reason the first half of the grid still measures
    what it always measured: a sweep has to ask for a branch by name."""
    from hack_and_slash.game.autoplay import play_run_out

    run = a_long_run()
    play_run_out(run)

    assert run.job_id == ""
    assert run.world.hero.type.id == "knight"


def test_the_driver_promotes_at_the_stage_the_scene_would() -> None:
    """Not on the first transition it sees, and not on the last one."""
    from hack_and_slash.game.autoplay import play_run_out

    run = a_long_run()
    assert run.stage_number == jobs.PROMOTION_STAGE - 1
    assert not run.at_promotion_point

    play_run_out(run, job="dark_knight")
    assert run.stage_number == jobs.PROMOTION_STAGE


def test_a_branch_from_another_class_is_refused_rather_than_ignored() -> None:
    """A sweep quietly measuring the wrong class is the failure worth being
    loud about -- it produces numbers, and they look fine."""
    from hack_and_slash.game.autoplay import play_run_out

    run = a_long_run("rogue")
    with pytest.raises(ValueError):
        play_run_out(run, job="dark_knight")
