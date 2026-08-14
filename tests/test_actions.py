"""The dodge, the i-frame window, and the state machine underneath both.

The dodge is the hero's only defensive verb, so its edges are where the game is
either fair or not: invulnerability that starts late punishes reacting late,
which is when people react; invulnerability that outlasts the roll makes rolling
constantly the correct way to play.
"""

from __future__ import annotations

import pytest

from hack_and_slash.core.vec2 import Vec2, from_angle
from hack_and_slash.game import actions, intent as intents
from hack_and_slash.game.combat import apply_hit
from hack_and_slash.game.entities import ActionState
from hack_and_slash.game.events import EventKind
from hack_and_slash.game.sim import step

from .helpers import BESTIARY, HERO, add_enemy, enemies_idle, make_world, run
#: Whatever the reference class swings. Read off the class rather than
#: named directly, so these tests follow the Knight if its weapon changes
#: -- they are about the swing state machine, not about one weapon's stats.
SWORD = HERO.weapon
CLAW = BESTIARY.weapons["claw"]
RIGHT = Vec2(1, 0)


# --- invulnerability ---------------------------------------------------------
def test_a_hit_during_the_iframe_window_is_ignored() -> None:
    world = make_world()
    hero = world.hero
    attacker = add_enemy(world, "grunt", hero.pos + Vec2(14, 0))

    step(world, intents.dodge_toward(RIGHT))
    assert hero.iframes > 0

    landed = apply_hit(world, attacker, hero, CLAW, world.rng)
    assert not landed
    assert hero.hp == HERO.hp


def test_an_ignored_hit_says_so_rather_than_passing_silently() -> None:
    # The renderer needs to show *something* -- a dodge that looks identical to
    # a miss teaches the player nothing about what just worked.
    world = make_world()
    hero = world.hero
    attacker = add_enemy(world, "grunt", hero.pos + Vec2(14, 0))
    step(world, intents.dodge_toward(RIGHT))

    apply_hit(world, attacker, hero, CLAW, world.rng)
    assert any(e.kind is EventKind.BLOCKED for e in world.events)


def test_a_hit_one_tick_after_the_window_closes_lands() -> None:
    """The window has to have an end, and it has to be where the data says."""
    world = make_world()
    hero = world.hero
    attacker = add_enemy(world, "grunt", hero.pos + Vec2(14, 0))

    with enemies_idle():
        run(world, HERO.iframe_ticks + 1, intents.dodge_toward(RIGHT))
    assert hero.iframes == 0

    assert apply_hit(world, attacker, hero, CLAW, world.rng)
    assert hero.hp < HERO.hp


def test_invulnerability_starts_on_the_very_first_tick_of_the_roll() -> None:
    """Front-loaded deliberately: i-frames that begin part-way through punish
    reacting at the last moment, which is exactly when players react.

    The full window survives the tick it started on, because timers are counted
    down at the top of a tick and the roll begins after them -- so the player
    gets every tick the data promises, not one fewer.
    """
    world = make_world()
    step(world, intents.dodge_toward(RIGHT))
    assert world.hero.iframes == HERO.iframe_ticks


def test_invulnerability_ends_before_the_roll_does() -> None:
    """Otherwise the tail of every dodge is free, and the optimal play is to
    roll constantly rather than to roll at the right moment."""
    world = make_world()
    hero = world.hero
    with enemies_idle():
        run(world, HERO.iframe_ticks + 1, intents.dodge_toward(RIGHT))
        assert hero.iframes == 0
        assert hero.state is ActionState.DODGING, "the roll ended with the i-frames"


# --- one swing, one dodge ----------------------------------------------------
def test_dodging_the_first_frame_of_a_swing_dodges_all_of_it() -> None:
    """The subtle one.

    A swing records who it has hit *before* checking invulnerability. Drop that
    and rolling through the first tick of a four-tick window means being hit by
    the second, which reads as the dodge simply not working.
    """
    world = make_world()
    hero = world.hero
    enemy = add_enemy(world, "grunt", hero.pos + Vec2(14, 0))

    with enemies_idle():
        # Line up the grunt's swing so its active window opens next tick.
        enemy.facing = 0.0
        actions.begin_attack(enemy)
        run(world, CLAW.windup)
        assert enemy.state is ActionState.ACTIVE

        # Roll on the frame it connects, then ride out the rest of the window.
        step(world, intents.dodge_toward(Vec2(0, -1)))
        run(world, CLAW.active + 1)

    assert hero.hp == HERO.hp, "the swing got a second bite after the i-frames"


# --- cooldown ----------------------------------------------------------------
def test_a_second_dodge_is_refused_while_the_cooldown_runs() -> None:
    world = make_world()
    hero = world.hero
    with enemies_idle():
        run(world, HERO.dodge_ticks + 1, intents.dodge_toward(RIGHT))
    assert hero.state is ActionState.IDLE
    assert hero.dodge_cooldown > 0
    assert not actions.begin_dodge(hero, RIGHT)


def test_the_cooldown_starts_when_the_roll_ends_not_when_it_begins() -> None:
    # So back-to-back dodging is gated by the gap between rolls, not their length.
    world = make_world()
    hero = world.hero
    with enemies_idle():
        run(world, 2, intents.dodge_toward(RIGHT))
        assert hero.dodge_cooldown == 0, "cooldown started during the roll"
        run(world, HERO.dodge_ticks, intents.dodge_toward(RIGHT))
    assert hero.dodge_cooldown > 0


def test_dodging_again_is_allowed_once_the_cooldown_expires() -> None:
    world = make_world()
    hero = world.hero
    with enemies_idle():
        # Tapped once, not held -- holding the button re-rolls the instant the
        # cooldown clears, which would leave the hero mid-roll here.
        step(world, intents.dodge_toward(RIGHT))
        run(world, HERO.dodge_ticks + HERO.dodge_cooldown)
    assert hero.state is ActionState.IDLE
    assert hero.dodge_cooldown == 0
    assert actions.begin_dodge(hero, RIGHT)


# --- exclusivity -------------------------------------------------------------
def test_you_cannot_dodge_out_of_your_own_swing() -> None:
    """One action at a time, on one field. Overlapping states are how "I dodged
    and got hit anyway, mid-swing" bugs come about."""
    world = make_world()
    hero = world.hero
    step(world, intents.swing_at(RIGHT))
    assert hero.state is ActionState.WINDUP
    assert not actions.begin_dodge(hero, RIGHT)


def test_a_dodge_and_an_attack_requested_together_only_rolls() -> None:
    world = make_world()
    hero = world.hero
    step(world, intents.Intent(move=RIGHT, aim=RIGHT, attack=True, dodge=True))
    assert hero.state is ActionState.DODGING


def test_nothing_can_act_while_staggered() -> None:
    world = make_world()
    hero = world.hero
    hero.stagger = 3
    assert not actions.can_act(hero)
    assert not actions.begin_attack(hero)
    assert not actions.begin_dodge(hero, RIGHT)


def test_enemies_cannot_dodge() -> None:
    # Expressed as data -- enemies have no dodge_ticks -- not as a branch.
    world = make_world()
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(40, 0))
    assert not actions.begin_dodge(enemy, RIGHT)


# --- movement ----------------------------------------------------------------
def test_a_roll_covers_more_ground_than_walking_the_same_ticks() -> None:
    walking = make_world()
    rolling = make_world()
    with enemies_idle():
        run(walking, HERO.dodge_ticks, intents.walk(RIGHT))
        run(rolling, HERO.dodge_ticks, intents.dodge_toward(RIGHT))
    assert rolling.hero.pos.x > walking.hero.pos.x + 10


def test_a_roll_cannot_be_steered_once_it_has_started() -> None:
    """A dodge is a commitment. Steering mid-roll would make the direction you
    chose a suggestion, and there would be nothing to read or punish."""
    world = make_world()
    hero = world.hero
    start_y = hero.pos.y
    with enemies_idle():
        step(world, intents.dodge_toward(RIGHT))
        run(world, HERO.dodge_ticks - 1, intents.walk(Vec2(0, 1)))  # try to turn down
    assert hero.pos.y == pytest.approx(start_y)


def test_rolling_with_no_direction_held_rolls_where_you_are_looking() -> None:
    # Rather than doing nothing and eating the cooldown for it.
    world = make_world()
    hero = world.hero
    hero.facing = from_angle(0.0).angle()
    start = hero.pos
    with enemies_idle():
        run(world, 4, intents.Intent(dodge=True))
    assert hero.pos.x > start.x


def test_walking_is_slowed_but_not_stopped_during_a_swing() -> None:
    """Rooting the hero for every attack reads as unresponsive; full speed makes
    committing to a swing cost nothing."""
    free = make_world()
    swinging = make_world()
    with enemies_idle():
        run(free, 10, intents.walk(RIGHT))
        run(swinging, 10, intents.Intent(move=RIGHT, aim=RIGHT, attack=True))

    free_distance = free.hero.pos.x - make_world().hero.pos.x
    swing_distance = swinging.hero.pos.x - make_world().hero.pos.x
    assert 0 < swing_distance < free_distance
    assert swing_distance == pytest.approx(free_distance * actions.ATTACK_MOVE_SCALE)


# --- the state machine -------------------------------------------------------
def test_a_swing_spends_exactly_the_ticks_its_data_says() -> None:
    world = make_world()
    hero = world.hero
    with enemies_idle():
        step(world, intents.swing_at(RIGHT))
        assert hero.state is ActionState.WINDUP

        run(world, SWORD.windup - 1)
        assert hero.state is ActionState.ACTIVE

        run(world, SWORD.active)
        assert hero.state is ActionState.RECOVERY

        run(world, SWORD.recovery)
        assert hero.state is ActionState.IDLE


def test_attacks_cannot_be_mashed_out_of_recovery() -> None:
    # Recovery is the price of missing. If it can be cancelled, there is no price.
    world = make_world()
    hero = world.hero
    with enemies_idle():
        run(world, SWORD.windup + SWORD.active + 1, intents.swing_at(RIGHT))
        assert hero.state is ActionState.RECOVERY
        assert not actions.begin_attack(hero)
