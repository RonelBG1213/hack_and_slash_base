"""Swings, damage, death.

The timings asserted here come straight from `data/weapons.json`: the sword has
5 ticks of windup and 4 of active, so the first tick that can hit anything is
the sixth after the button went down. Reading those numbers from the data rather
than hard-coding them means a tuning change moves the assertions with it instead
of breaking them.
"""

from __future__ import annotations

import random

import pytest

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import intent as intents
from hack_and_slash.game.combat import roll_damage
from hack_and_slash.game.entities import ActionState
from hack_and_slash.game.events import EventKind
from hack_and_slash.game.sim import step

from .helpers import BESTIARY, HERO, add_enemy, enemies_idle, make_world, run

#: Whatever the reference class swings. Read off the class rather than
#: named directly, so these tests follow the Knight if its weapon changes
#: -- they are about the swing state machine, not about one weapon's stats.
SWORD = HERO.weapon
RIGHT = Vec2(1, 0)
SEED = 4242


def duel(distance: float = 20.0, seed: int = SEED):
    """A hero and one grunt, that far apart, on the hero's right."""
    world = make_world(seed=seed)
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(distance, 0))
    return world, world.hero, enemy


def expected_first_hit(seed: int = SEED) -> int:
    """What the first sword hit of a run seeded this way rolls.

    Nothing else in these tests draws from the world's Random, so the first roll
    of a fresh Random with the same seed is the same number.
    """
    return roll_damage(SWORD, random.Random(seed))


# --- the swing window --------------------------------------------------------
def test_a_swing_deals_nothing_during_its_windup() -> None:
    """Windup is the tell. If it could hit, there would be nothing to react to."""
    world, hero, enemy = duel()
    with enemies_idle():
        for _ in range(SWORD.windup):
            step(world, intents.swing_at(RIGHT))
    assert enemy.hp == enemy.type.hp
    assert hero.state is ActionState.ACTIVE, "should be about to connect"


def test_the_first_active_tick_deals_exactly_the_seeded_damage() -> None:
    world, hero, enemy = duel()
    with enemies_idle():
        run(world, SWORD.windup + 1, intents.swing_at(RIGHT))
    assert enemy.hp == enemy.type.hp - expected_first_hit()


def test_one_swing_hits_a_body_once_however_long_it_stays_open() -> None:
    """The active window is four ticks. Without per-swing bookkeeping that is
    four hits, and every weapon in the game deals four times its damage."""
    world, hero, enemy = duel()
    with enemies_idle():
        run(world, SWORD.windup + SWORD.active + 1, intents.swing_at(RIGHT))
    assert enemy.hp == enemy.type.hp - expected_first_hit()


def test_a_second_swing_can_hit_the_same_body_again() -> None:
    """The per-swing bookkeeping must reset, or a body is immune after one hit.

    The hero has to walk in to land the second one -- knockback opens real space,
    which is why closing the distance again is part of the loop rather than a
    detail of this test.
    """
    world, hero, enemy = duel()
    press_forward = intents.Intent(move=RIGHT, aim=RIGHT, attack=True)
    with enemies_idle():
        run(world, SWORD.total_ticks * 2 + 4, press_forward)
    assert enemy.hp < enemy.type.hp - expected_first_hit(), "only one swing ever landed"


# --- the cone ----------------------------------------------------------------
def test_a_swing_misses_what_is_behind_you() -> None:
    world, hero, enemy = duel(distance=20.0)
    with enemies_idle():
        run(world, SWORD.windup + SWORD.active + 2, intents.swing_at(Vec2(-1, 0)))
    assert enemy.hp == enemy.type.hp


def test_a_swing_misses_what_is_out_of_reach() -> None:
    world, hero, enemy = duel(distance=SWORD.reach + 40)
    with enemies_idle():
        run(world, SWORD.windup + SWORD.active + 2, intents.swing_at(RIGHT))
    assert enemy.hp == enemy.type.hp


def test_facing_is_committed_when_the_swing_starts() -> None:
    """Turning mid-swing would make every attack a homing one."""
    world, hero, enemy = duel(distance=20.0)
    with enemies_idle():
        step(world, intents.swing_at(Vec2(-1, 0)))  # commit to facing away
        run(world, SWORD.windup + SWORD.active + 2, intents.swing_at(RIGHT))
    assert enemy.hp == enemy.type.hp, "the swing turned to follow the aim"


# --- consequences ------------------------------------------------------------
def test_a_hit_shoves_the_target_away_from_the_attacker() -> None:
    world, hero, enemy = duel(distance=20.0)
    with enemies_idle():
        start_x = enemy.pos.x
        run(world, SWORD.windup + 6, intents.swing_at(RIGHT))
    assert enemy.pos.x > start_x + 2, "no knockback"


def test_knockback_bleeds_off_instead_of_running_forever() -> None:
    world, hero, enemy = duel(distance=20.0)
    with enemies_idle():
        run(world, SWORD.windup + 2, intents.swing_at(RIGHT))
        run(world, 40)
        settled = enemy.pos.x
        run(world, 40)
    assert enemy.pos.x == pytest.approx(settled), "still drifting"


def test_killing_a_body_removes_it_and_announces_the_death() -> None:
    world, hero, enemy = duel(distance=20.0)
    enemy.hp = 1
    with enemies_idle():
        deaths = []
        for _ in range(SWORD.windup + 2):
            step(world, intents.swing_at(RIGHT))
            deaths += [e for e in world.events if e.kind is EventKind.DEATH]
    assert deaths, "nothing announced the kill"
    assert all(e.id != enemy.id for e in world.entities)


def test_a_hit_announces_how_much_it_was_for() -> None:
    # The damage numbers on screen must be the damage actually dealt.
    world, hero, enemy = duel(distance=20.0)
    with enemies_idle():
        hits = []
        for _ in range(SWORD.windup + 2):
            step(world, intents.swing_at(RIGHT))
            hits += [e for e in world.events if e.kind is EventKind.HIT]
    assert len(hits) == 1
    assert hits[0].amount == expected_first_hit()
    assert enemy.hp == enemy.type.hp - hits[0].amount


def test_nothing_can_hit_its_own_faction() -> None:
    world, hero, enemy = duel(distance=200.0)
    friend = add_enemy(world, "grunt", enemy.pos + Vec2(14, 0))
    with enemies_idle():
        enemy.facing = 0.0
        from hack_and_slash.game import actions

        actions.begin_attack(enemy)
        run(world, enemy.type.weapon.total_ticks + 2)
    assert friend.hp == friend.type.hp


# --- interruption ------------------------------------------------------------
def test_being_hit_during_a_windup_loses_the_attack() -> None:
    from hack_and_slash.game import actions
    from hack_and_slash.game.combat import apply_hit

    world, hero, enemy = duel(distance=20.0)
    actions.begin_attack(enemy, facing=0.0)
    assert enemy.state is ActionState.WINDUP

    apply_hit(world, hero, enemy, SWORD, world.rng)
    assert enemy.state is ActionState.IDLE, "the windup survived a hit"


def test_being_hit_once_the_blade_is_out_does_not_cancel_it() -> None:
    """Otherwise whoever swings first always wins, and trading is never a choice."""
    from hack_and_slash.game import actions
    from hack_and_slash.game.combat import apply_hit

    world, hero, enemy = duel(distance=20.0)
    enemy.state = ActionState.ACTIVE
    apply_hit(world, hero, enemy, SWORD, world.rng)
    assert enemy.state is ActionState.ACTIVE


# --- damage rolls ------------------------------------------------------------
def test_damage_never_rounds_away_to_nothing() -> None:
    weak = BESTIARY.weapons["claw"]
    for seed in range(50):
        assert roll_damage(weak, random.Random(seed)) >= 1


def test_damage_varies_but_stays_inside_its_band() -> None:
    rolls = {roll_damage(SWORD, random.Random(seed)) for seed in range(200)}
    assert len(rolls) > 1, "variance of 2 produced one number"
    assert min(rolls) >= SWORD.damage - SWORD.variance
    assert max(rolls) <= SWORD.damage + SWORD.variance
