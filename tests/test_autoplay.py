"""The reference bot's defensive repertoire, and the second instrument beside it.

`test_playthrough.py` measures what the policies *achieve* -- brackets, grids,
whole campaigns -- and takes minutes to do it. This file measures what they
*decide*, in milliseconds, and it exists for one claim in particular:

    the reference policy is unchanged by `Evasive` existing

That claim is what lets a lateral disengage be added to a tuned game without
re-opening the 280 recorded cells. It is the same shape as
`test_a_variant_is_stat_identical_to_what_it_varies` and as the neutral-attribute
test: turn "the grid is unmoved" from a sweep into an assertion.
"""

from __future__ import annotations

import pytest

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import skills
from hack_and_slash.game.autoplay import Autoplay, Evasive, Skilful, autoplay, evasive
from hack_and_slash.game.entities import ActionState

from .helpers import BESTIARY, add_enemy, level_with, make_world, open_room, run
from .helpers import HERO  # noqa: F401

SEED = 909


def a_world(width: int = 30, height: int = 30):
    return make_world(open_room(width, height), seed=SEED)


def hurt(hero, fraction: float = 0.2) -> None:
    """Drop the hero low enough that the policy wants to give ground.

    `_should_give_ground` needs three things at once -- low health, a dodge on
    cooldown and something close -- and a test that set only the first would
    quietly measure the healthy branch instead.
    """
    hero.hp = max(1, int(hero.max_hp * fraction))
    hero.dodge_cooldown = 60


# --- the identity ------------------------------------------------------------
def test_the_reference_policy_retreats_in_a_straight_line() -> None:
    """The blind spot, pinned deliberately rather than left implicit.

    This is not a wish -- it is the property the `flanker` brain was built to
    punish, and the reason `data/entities.json` ships a demon that is spawned
    nowhere. Writing it down as a test means the day somebody changes it, the
    suite says so rather than the balance grid saying so three sweeps later.
    """
    world = a_world()
    hero = world.hero
    toward = Vec2(1.0, 0.0)

    away = autoplay._retreat_direction(world, hero, toward)
    assert away.x == pytest.approx(-1.0)
    assert away.y == pytest.approx(0.0)


def test_the_evasive_policy_leaves_the_reference_untouched() -> None:
    """`Evasive` overrides one method. If it ever overrides a second, this is
    the test that notices -- and every recorded number in the project is
    downstream of it."""
    overridden = {
        name
        for name in vars(Evasive)
        if not name.startswith("__") and hasattr(Autoplay, name)
    }
    assert overridden == {"_retreat_direction"}, (
        f"Evasive now overrides {sorted(overridden)}; the reference policy is "
        f"no longer provably unchanged by its existence"
    )


def test_a_healthy_fight_is_decided_identically_by_both_policies() -> None:
    """The identity claim on real decisions rather than on the class body.

    A hero that is not giving ground never reaches `_retreat_direction` at all,
    so the two policies must agree tick for tick. If they diverge here, the
    override is leaking into branches it has no business in and an `Evasive`
    sweep would be measuring two changes at once.
    """
    level = level_with((6, 6), [("grunt", (10, 6)), ("bowman", (14, 10))])
    reference = make_world(level, seed=SEED)
    lateral = make_world(level, seed=SEED)

    for tick in range(400):
        a = autoplay(reference)
        b = evasive(lateral)
        assert a == b, f"tick {tick}: the two policies asked for different things"
        run(reference, 1, a)
        run(lateral, 1, b)
        if reference.hero is None or not reference.enemies():
            break


# --- the sidestep ------------------------------------------------------------
def test_an_evasive_hero_gives_ground_off_the_straight_line() -> None:
    """The whole of what this instrument adds."""
    world = a_world()
    hero = world.hero
    toward = Vec2(1.0, 0.0)

    away = evasive._retreat_direction(world, hero, toward)
    straight = Vec2(-1.0, 0.0)

    assert away.y != pytest.approx(0.0), (
        f"the evasive retreat came back as {away}, which is the straight line "
        f"the reference already walks"
    )
    # Still a retreat, not an orbit: the lean is off the line, not across it.
    assert away.x < 0.0, f"the evasive retreat is not going backwards at all: {away}"
    assert away.dot(straight) > 0.0


def test_the_evasive_lean_is_the_angle_it_says_it_is() -> None:
    world = a_world()
    away = Evasive(degrees=90.0)._retreat_direction(world, world.hero, Vec2(1.0, 0.0))
    assert away.x == pytest.approx(0.0, abs=1e-9)


def test_an_evasive_retreat_still_refuses_to_walk_into_a_wall() -> None:
    """The wall-probe in `_away_from` sits in front of the override and has to
    stay there.

    The corner death-spiral it exists to stop -- every boss pushes the hero
    backwards, and the measured runs ended with the hero flattened against the
    far wall taking free hits -- is not made any less likely by leaning the
    retreat forty degrees. It is the same failure with a diagonal on it.
    """
    world = a_world()
    hero = world.hero

    # Jam the hero into the west wall, with the threat due east: straight back
    # and both leans are all into stone.
    hero.pos = Vec2(world.level.tile * 1.2, world.level.tile * 1.2)
    enemy = add_enemy(world, "grunt", hero.pos + Vec2(20, 0))
    hurt(hero)

    intent = evasive(world)
    step = hero.pos + intent.move * world.level.tile
    tx = int(step.x // world.level.tile)
    ty = int(step.y // world.level.tile)
    assert not world.is_solid(tx, ty), (
        f"the evasive retreat walked the hero into the wall at ({tx}, {ty})"
    )


def test_both_policies_agree_the_hero_is_giving_ground_at_all() -> None:
    """Guards the test above from passing for the wrong reason.

    If `hurt` stopped triggering `_should_give_ground` -- a changed threshold, a
    changed condition -- the retreat tests would exercise the *approach* branch
    and go on passing while measuring nothing.
    """
    world = a_world()
    hero = world.hero
    add_enemy(world, "grunt", hero.pos + Vec2(20, 0))
    hurt(hero)

    assert autoplay._should_give_ground(hero, True)


# --- the skill-ceiling policy and the buff slot ------------------------------
def test_the_skilful_policy_never_reaches_for_the_buff_slot() -> None:
    """The Q slot is invisible to both instruments, and that is a decision.

    `Autoplay` cannot see it because it plays light-only. `Skilful` skips it
    explicitly, because a policy whose whole rule is "the most expensive thing
    that can connect, on the tick I want to attack" has no model of *buff, then
    fight* -- pressing a buff inside that rule would measure the ordering this
    loop happens to have rather than what the buff is worth.

    That is the recorded trap in this repo, hit for the fourth time: an
    instrument that touches the feature reports its own perturbation in the
    same units it reports difficulty. The flanker demon was the first.

    Asserted over every class, and at ranges either side of every skill's
    reach, so it cannot pass merely because the bot was too far away to want
    anything.
    """
    policy = Skilful()
    for cls in BESTIARY.hero_classes:
        for distance in (12, 30, 60, 140, 300):
            world = a_world()
            world.hero.type = cls
            add_enemy(world, "grunt", world.hero.pos + Vec2(distance, 0))

            for _ in range(90):
                intent = policy(world)
                assert not (intent.attack and intent.weapon == skills.NEUTRAL), (
                    f"{cls.id} pressed the buff slot at {distance}px"
                )
                run(world, 1, intent)
