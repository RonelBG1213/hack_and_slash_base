"""The whole game, start to finish, with no window open.

This is the regression net. Every other test checks one rule; this one checks
that the rules add up to a game that can be won -- that the arena on disk is
completable, that a run ends, and that standing still gets you killed.

The hero is driven by a small deterministic policy rather than a fixed list of
button presses. A recorded input sequence would be worthless here: change one
timing in `data/weapons.json` and it desynchronises immediately, failing without
telling you anything. A policy keeps playing, so when this test fails it is
because the *game* stopped being winnable, which is the thing worth knowing.
"""

from __future__ import annotations

import pytest

from hack_and_slash import config
from hack_and_slash.core import level_io
from hack_and_slash.core.vec2 import ZERO, Vec2
from hack_and_slash.game import actions
from hack_and_slash.game.entities import ActionState, Entity
from hack_and_slash.game.intent import NOTHING, Intent
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Outcome, World

from .helpers import BESTIARY, open_room

#: Generous. A competent human clears the arena in well under this; the ceiling
#: is here so a hero that can no longer reach anything fails the test instead of
#: hanging the suite.
TICK_LIMIT = 9000

#: Below this fraction of health the policy stops pressing and backs off.
CAUTIOUS_BELOW = 0.45

#: How close an incoming attack has to be before the policy rolls away from it.
DANGER_RADIUS = 46.0


def arena() -> World:
    level = level_io.load(config.LEVELS_DIR / "arena.json")
    return World(level, BESTIARY, seed=7)


# --- a hero that plays badly but plays ---------------------------------------
def autoplay(world: World) -> Intent:
    """Close in, swing when in range, roll away from anything about to land.

    Deliberately simple: if a policy this crude can clear the arena, a person
    can. If it stops being able to, the arena or the numbers have drifted.
    """
    hero = world.hero
    if hero is None or not hero.is_alive:
        return NOTHING

    enemies = world.enemies()
    if not enemies:
        return NOTHING

    threat = _incoming(hero, enemies)
    if threat is not None and hero.dodge_cooldown <= 0 and actions.can_act(hero):
        away = (hero.pos - threat.pos).normalized()
        return Intent(move=away, aim=(threat.pos - hero.pos).normalized(), dodge=True)

    target = min(enemies, key=lambda e: e.pos.distance_sq_to(hero.pos))
    toward = (target.pos - hero.pos).normalized()
    distance = hero.pos.distance_to(target.pos)
    strike_range = hero.type.weapon.reach + target.radius - 4.0

    if hero.health_fraction < CAUTIOUS_BELOW and distance < strike_range * 1.6:
        # Hurt: back off and let the dodge come off cooldown rather than trading.
        return Intent(move=-toward, aim=toward)

    if distance <= strike_range:
        return Intent(aim=toward, attack=True)

    return Intent(move=toward, aim=toward)


def _incoming(hero: Entity, enemies: list[Entity]) -> Entity | None:
    """The nearest enemy whose attack is about to land on us."""
    for enemy in enemies:
        if enemy.pos.distance_to(hero.pos) > DANGER_RADIUS:
            continue
        if enemy.state in (ActionState.WINDUP, ActionState.ACTIVE):
            return enemy
    return None


def play(world: World, policy, limit: int = TICK_LIMIT) -> int:
    for tick in range(limit):
        if world.outcome is not Outcome.RUNNING:
            return tick
        step(world, policy(world))
    return limit


# --- the run -----------------------------------------------------------------
def test_the_shipped_arena_can_be_cleared() -> None:
    """The one that proves there is a game here.

    If this fails after a tuning change, something became unwinnable -- most
    likely an enemy that now out-damages the hero's ability to disengage.
    """
    world = arena()
    ticks = play(world, autoplay)

    assert world.outcome is Outcome.WON, (
        f"gave up after {ticks} ticks with {len(world.enemies())} enemies left "
        f"and the hero on {world.hero.hp if world.hero else 0} hp"
    )
    assert world.hero is not None and world.hero.is_alive
    assert not world.enemies()


def test_clearing_the_arena_takes_a_believable_amount_of_time() -> None:
    """A fight that resolves in two seconds is not a fight, and one that takes
    five minutes is a chore. Wide bounds -- this is a smell test, not balance."""
    world = arena()
    ticks = play(world, autoplay)
    seconds = ticks / config.TICKS_PER_SEC

    assert world.outcome is Outcome.WON
    assert 10 < seconds < 180, f"cleared in {seconds:.0f}s"


def test_standing_still_gets_you_killed() -> None:
    """The other half of the contract. If doing nothing survives, the enemies
    are not a threat and none of the combat matters."""
    world = arena()
    ticks = play(world, lambda w: NOTHING, limit=4000)

    assert world.outcome is Outcome.LOST, f"survived {ticks} ticks doing nothing"


def test_the_hero_can_break_away_from_a_chase_in_open_ground() -> None:
    """The deal the fight rests on: taking a hit is a decision you made.

    Stated precisely, because the obvious stronger claim is false and should be.
    In *open ground* the hero pulls away from anything chasing it. Surrounded in
    a pillared arena it cannot, and that is the design working -- being boxed in
    by five things is supposed to kill you. Asserting "fleeing always survives"
    would be asserting that the arena has no teeth.
    """
    from .helpers import add_enemy, make_world

    world = make_world(open_room(50, 20), seed=1)
    hero = world.hero
    chaser = add_enemy(world, "grunt", hero.pos + Vec2(-60, 0))
    opening_gap = hero.pos.distance_to(chaser.pos)

    for _ in range(200):
        step(world, Intent(move=Vec2(1, 0), aim=Vec2(1, 0)))

    assert hero.pos.distance_to(chaser.pos) > opening_gap * 2, (
        "a chaser kept pace with the hero across open floor"
    )
    assert hero.hp == hero.type.hp, "was caught while running in a straight line"


# --- the run is reproducible -------------------------------------------------
def test_the_same_seed_replays_the_same_run() -> None:
    first = arena()
    second = arena()
    play(first, autoplay)
    play(second, autoplay)

    assert first.tick == second.tick
    assert first.outcome is second.outcome
    assert first.hero.hp == second.hero.hp


def test_a_different_seed_plays_out_differently() -> None:
    """Otherwise the seed is decorative and the variance in the data does nothing."""
    level = level_io.load(config.LEVELS_DIR / "arena.json")
    results = set()
    for seed in range(6):
        world = World(level, BESTIARY, seed=seed)
        play(world, autoplay)
        results.add((world.tick, world.hero.hp if world.hero else 0))
    assert len(results) > 1


# --- the world stays sane for a whole run ------------------------------------
def test_nothing_ends_up_inside_a_wall() -> None:
    world = arena()
    level = world.level

    for _ in range(1500):
        if world.outcome is not Outcome.RUNNING:
            break
        step(world, autoplay(world))
        for entity in world.entities:
            tx, ty = level.tile_at(entity.pos)
            assert level.is_walkable(tx, ty), (
                f"{entity.type.id} is inside a wall at {entity.pos} on tick {world.tick}"
            )


def test_projectiles_do_not_accumulate_forever() -> None:
    """Every arrow has to be reaped by a wall, a body or its own lifetime.
    A leak here is invisible until a long run slows to a crawl."""
    world = arena()
    peak = 0
    for _ in range(2000):
        if world.outcome is not Outcome.RUNNING:
            break
        step(world, autoplay(world))
        peak = max(peak, len(world.projectiles))
    assert peak < 40, f"{peak} arrows in flight at once"


def test_health_never_goes_negative_or_above_full() -> None:
    world = arena()
    for _ in range(1500):
        if world.outcome is not Outcome.RUNNING:
            break
        step(world, autoplay(world))
        for entity in world.entities:
            assert 0 <= entity.hp <= entity.type.hp, entity.type.id
