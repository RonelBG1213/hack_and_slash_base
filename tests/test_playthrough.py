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
from hack_and_slash.core import campaign_io
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game.autoplay import (
    REACTION_SLOPPY,
    Autoplay,
    autoplay,
    play_out,
    reckless,
)
from hack_and_slash.game.intent import NOTHING, Intent
from hack_and_slash.game.run import Run, RunOutcome
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Outcome, World

from .helpers import BESTIARY, open_room

#: Generous. A competent hero clears a stage in well under this; the ceiling is
#: here so one that can no longer reach anything fails the test instead of
#: hanging the suite.
TICK_LIMIT = 9000

#: A whole run is four stages, so it needs headroom the single-stage limit does
#: not. Still a guard, not a target.
RUN_TICK_LIMIT = 40000

#: Enough seeds that a bracket assertion is about the balance rather than about
#: one lucky fight. The sim is deterministic, so each is a fixed outcome.
SEEDS = range(6)

#: The stage the game was originally tuned around, and the only one whose
#: numbers are on record. Index 2 -- "The Gauntlet".
RECORDED_STAGE = 2


def campaign():
    return campaign_io.load(config.LEVELS_DIR / "campaign.json")


def stage_world(index: int = RECORDED_STAGE, seed: int = 7) -> World:
    """One stage in isolation, entered at full health."""
    return World(campaign()[index], BESTIARY, seed=seed)


def play(world: World, policy, limit: int = TICK_LIMIT) -> int:
    return play_out(world, policy, limit)


def wins_across_seeds(policy, index: int = RECORDED_STAGE) -> int:
    """How many of the standard seeds this policy clears one stage on."""
    won = 0
    for seed in SEEDS:
        world = stage_world(index, seed)
        play(world, policy)
        won += world.outcome is Outcome.WON
    return won


def play_run(policy, seed: int) -> Run:
    """A whole run, stage one to the end, with health carrying between."""
    run = Run.start(campaign(), BESTIARY, seed=seed)
    for _ in range(RUN_TICK_LIMIT):
        if run.is_over:
            break
        step(run.world, policy(run.world))
        run.settle()
    return run


def runs_won(policy) -> int:
    return sum(play_run(policy, seed).outcome is RunOutcome.WON for seed in SEEDS)


# --- the run -----------------------------------------------------------------
def test_the_recorded_stage_can_be_cleared() -> None:
    """The one that proves there is a game here.

    If this fails after a tuning change, something became unwinnable -- most
    likely an enemy that now out-damages the hero's ability to disengage.
    """
    world = stage_world()
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
    world = stage_world()
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

    Rolling costs uptime and lengthens the fight, so a hero that reacts slowly
    does about as well as one that reacts sharply. That is why the ceiling is
    built on refusing to disengage instead of on reacting late.

    Note what is *not* claimed: this holds across the slower reactions, not down
    to zero. A hero answering every telegraph on the tick it opens rolls
    perpetually against the boss and loses most runs -- an artifact of the
    instrument, which is why `autoplay` is the twelve-tick policy rather than the
    zero-tick one. `test_twitchiness_is_not_skill` pins that separately.

    If this ever fails, the finding has stopped holding: dodging has started to
    carry the fight, and the ceiling test should be reconsidered rather than
    this one simply relaxed.
    """
    sloppy_wins = wins_across_seeds(Autoplay(reaction_ticks=REACTION_SLOPPY))
    assert sloppy_wins >= len(SEEDS) - 1, (
        f"a slow-reacting hero now wins only {sloppy_wins}/{len(SEEDS)} -- dodging "
        "has become decisive, so the ceiling test is measuring the wrong thing"
    )


def test_twitchiness_is_not_skill() -> None:
    """Why the reference hero is not the one with the fastest reflexes.

    Against something that is winding up or swinging half the time -- a boss --
    a hero that answers every telegraph instantly never gets a swing in. It is a
    property of the policy, not of the player it stands in for, and it is pinned
    here so nobody "improves" the reference hero by making it twitchier.
    """
    from hack_and_slash.game.autoplay import twitchy

    assert autoplay.reaction_ticks > twitchy.reaction_ticks
    assert runs_won(autoplay) > runs_won(twitchy), (
        "the twitchy policy now does at least as well as the measured one -- "
        "the artifact this guards against may have gone away, in which case "
        "reconsider which policy is the reference rather than deleting this"
    )


# --- the same bracket, one level up ------------------------------------------
# A run is not four independent fights: health carries between stages, so it can
# be unwinnable while every stage is fine on its own, and every stage can be fine
# while stage 2 is a wall. Both levels are checked, because neither implies the
# other.
def test_the_floor_a_skilled_hero_finishes_the_whole_run() -> None:
    won = runs_won(autoplay)
    assert won == len(SEEDS), (
        f"a skilled hero completes only {won}/{len(SEEDS)} runs -- either a stage "
        "is too hard or the heal between stages is too small to sustain a run"
    )


def test_the_ceiling_a_reckless_hero_finishes_no_runs() -> None:
    assert runs_won(reckless) == 0


def test_every_stage_is_clearable_on_its_own() -> None:
    """Catches the fault a run-level test hides.

    A run can be winnable overall while one stage in the middle is a wall the
    player only gets past because the two before it were generous. Each stage is
    checked from full health, which is the fairest reading each can get.
    """
    stages = campaign().stages
    for index, stage in enumerate(stages):
        won = wins_across_seeds(autoplay, index)
        assert won == len(SEEDS), (
            f"stage {index + 1} ({stage.name}) is clearable on only "
            f"{won}/{len(SEEDS)} seeds from full health"
        )


def test_a_run_carries_damage_forward() -> None:
    """The mechanism the run-level bracket is actually testing.

    Without this, a run is four separate fights and the whole layer is
    decoration.
    """
    run = play_run(autoplay, seed=3)
    assert run.outcome is RunOutcome.WON
    # Finishing a four-stage run on full health would mean nothing ever stuck.
    assert run.world.hero.hp < BESTIARY["hero"].hp


def test_the_difficulty_curve_rises() -> None:
    """A crude proxy, and labelled as one.

    Enemy count is a poor measure of difficulty -- a boss is one enemy. It is
    checked only across the first three stages, where the mix is comparable, and
    the real measure is the per-stage rows in `tools/balance.py`.
    """
    counts = [len(stage.enemy_spawns) for stage in campaign().stages[:3]]
    assert counts == sorted(counts), f"enemy counts do not rise: {counts}"
    assert counts[0] < counts[-1]


def test_the_final_stage_has_the_boss() -> None:
    final = campaign().stages[-1]
    assert any(spawn.type_id == "boss" for spawn in final.enemy_spawns)
    # And nothing before it does -- the capstone should not turn up early.
    for stage in campaign().stages[:-1]:
        assert not any(spawn.type_id == "boss" for spawn in stage.enemy_spawns)


def test_standing_still_gets_you_killed() -> None:
    """The other half of the contract. If doing nothing survives, the enemies
    are not a threat and none of the combat matters."""
    world = stage_world()
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
    first = stage_world()
    second = stage_world()
    play(first, autoplay)
    play(second, autoplay)

    assert first.tick == second.tick
    assert first.outcome is second.outcome
    assert first.hero.hp == second.hero.hp


def test_a_different_seed_plays_out_differently() -> None:
    """Otherwise the seed is decorative and the variance in the data does nothing."""
    level = campaign()[RECORDED_STAGE]
    results = set()
    for seed in range(6):
        world = World(level, BESTIARY, seed=seed)
        play(world, autoplay)
        results.add((world.tick, world.hero.hp if world.hero else 0))
    assert len(results) > 1


# --- the world stays sane for a whole run ------------------------------------
def test_nothing_ends_up_inside_a_wall() -> None:
    world = stage_world()
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
    world = stage_world()
    peak = 0
    for _ in range(2000):
        if world.outcome is not Outcome.RUNNING:
            break
        step(world, autoplay(world))
        peak = max(peak, len(world.projectiles))
    assert peak < 40, f"{peak} arrows in flight at once"


def test_health_never_goes_negative_or_above_full() -> None:
    world = stage_world()
    for _ in range(1500):
        if world.outcome is not Outcome.RUNNING:
            break
        step(world, autoplay(world))
        for entity in world.entities:
            assert 0 <= entity.hp <= entity.type.hp, entity.type.id
