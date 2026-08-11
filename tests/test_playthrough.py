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

from hack_and_slash import config
from hack_and_slash.core import level_io
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game.autoplay import (
    REACTION_SLOPPY,
    Autoplay,
    autoplay,
    play_out,
    reckless,
)
from hack_and_slash.game.intent import NOTHING, Intent
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Outcome, World

from .helpers import BESTIARY, open_room

#: Generous. A competent human clears the arena in well under this; the ceiling
#: is here so a hero that can no longer reach anything fails the test instead of
#: hanging the suite.
TICK_LIMIT = 9000

#: Enough seeds that a bracket assertion is about the balance rather than about
#: one lucky fight. The sim is deterministic, so each is a fixed outcome.
SEEDS = range(8)


def arena(seed: int = 7) -> World:
    level = level_io.load(config.LEVELS_DIR / "arena.json")
    return World(level, BESTIARY, seed=seed)


def play(world: World, policy, limit: int = TICK_LIMIT) -> int:
    return play_out(world, policy, limit)


def wins_across_seeds(policy) -> int:
    """How many of the standard seeds this policy can clear."""
    won = 0
    for seed in SEEDS:
        world = arena(seed)
        play(world, policy)
        won += world.outcome is Outcome.WON
    return won


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


# --- the difficulty bracket --------------------------------------------------
# Two tests, and they only mean anything together. The floor alone permits a
# walkover; the ceiling alone permits an unwinnable fight.
def test_the_floor_a_skilled_hero_wins_every_seed() -> None:
    """Doing the right things has to reliably work.

    Not "usually" -- every seed. A run lost to the arena rolling badly rather
    than to the player is the thing this forbids.
    """
    assert wins_across_seeds(autoplay) == len(SEEDS)


def test_the_ceiling_walking_in_swinging_loses_every_seed() -> None:
    """The arena has to punish playing badly, or none of the combat matters.

    The instrument here is a hero that never disengages -- *not* one with slow
    reactions, which was the obvious choice and turned out to measure almost
    nothing. Reaction time barely moves this fight: see
    `test_reaction_time_is_not_what_decides_this_fight` below, which pins that
    finding so a future tuning pass notices if it stops being true.
    """
    assert wins_across_seeds(reckless) == 0


def test_reaction_time_is_not_what_decides_this_fight() -> None:
    """A recorded finding, not a goal -- and a tripwire under the test above.

    Rolling costs uptime and lengthens the fight, so a hero that never dodges
    finishes about as healthy as one with perfect reflexes. That is why the
    ceiling is built on refusing to disengage instead of on reacting late.

    If this ever fails, the finding has stopped holding: dodging has started to
    carry the fight, and the ceiling test should be reconsidered rather than
    this one simply relaxed.
    """
    sloppy_wins = wins_across_seeds(Autoplay(reaction_ticks=REACTION_SLOPPY))
    assert sloppy_wins >= len(SEEDS) - 1, (
        f"a slow-reacting hero now wins only {sloppy_wins}/{len(SEEDS)} -- dodging "
        "has become decisive, so the ceiling test is measuring the wrong thing"
    )


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
