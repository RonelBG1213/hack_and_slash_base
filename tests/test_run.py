"""The layer above a single stage: carry-over, advancing, and how a run ends.

The distinction this file exists to protect: `World.outcome` says whether the
current arena is cleared, `Run.outcome` says whether the run is over. Clearing a
stage is only a win if there is nothing after it.
"""

from __future__ import annotations

from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.game.run import Run, RunOutcome
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Outcome, World

from .helpers import BESTIARY, open_room

HERO = BESTIARY["hero"]


def stage(name: str, enemies=(("grunt", (12, 10)),)) -> Level:
    room = open_room(20, 20)
    return Level(
        name=name,
        rows=room.rows,
        hero_spawn=(4, 10),
        enemy_spawns=tuple(EnemySpawn(t, pos) for t, pos in enemies),
        tile=room.tile,
    )


def campaign(count: int = 3) -> Campaign:
    return Campaign(
        name="test run", stages=tuple(stage(f"stage {i + 1}") for i in range(count))
    )


def clear_current_stage(run: Run) -> None:
    """Kill everything on the stage the way the sim would, then settle."""
    for enemy in run.world.enemies():
        enemy.hp = 0
    step(run.world)
    run.settle()


# --- carry-over in World -----------------------------------------------------
def test_a_world_without_carry_over_starts_at_full_health() -> None:
    # Every test predating the run layer depends on this staying the default.
    world = World(stage("solo"), BESTIARY, seed=1)
    assert world.hero.hp == HERO.hp


def test_carry_over_sets_the_hero_s_starting_health() -> None:
    world = World(stage("solo"), BESTIARY, seed=1, carry_hp=40)
    assert world.hero.hp == 40


def test_carry_over_cannot_exceed_the_hero_s_maximum() -> None:
    # Otherwise a generous heal becomes permanent bonus health.
    world = World(stage("solo"), BESTIARY, seed=1, carry_hp=HERO.hp + 50)
    assert world.hero.hp == HERO.hp


def test_carry_over_cannot_start_a_stage_already_dead() -> None:
    # A stage that begins with the death animation playing is not a stage.
    world = World(stage("solo"), BESTIARY, seed=1, carry_hp=0)
    assert world.hero.hp >= 1
    assert world.hero.is_alive


# --- advancing ---------------------------------------------------------------
def test_a_run_starts_on_the_first_stage() -> None:
    run = Run.start(campaign(3), BESTIARY, seed=5)
    assert run.stage_number == 1
    assert run.stage_count == 3
    assert run.outcome is RunOutcome.RUNNING
    assert run.world.hero.hp == HERO.hp


def test_clearing_a_stage_advances_rather_than_winning() -> None:
    """The distinction the whole module exists for."""
    run = Run.start(campaign(3), BESTIARY, seed=5)
    clear_current_stage(run)

    assert run.world.outcome is Outcome.RUNNING, "should be a fresh stage"
    assert run.outcome is RunOutcome.RUNNING, "the run is not over"
    assert run.stage_number == 2


def test_damage_carries_into_the_next_stage() -> None:
    run = Run.start(campaign(3), BESTIARY, seed=5)
    run.world.hero.hp = 50
    clear_current_stage(run)

    # Wounded, but not as wounded as you finished.
    assert 50 < run.world.hero.hp < HERO.hp


def test_the_heal_between_stages_is_the_amount_the_data_says() -> None:
    run = Run.start(campaign(3), BESTIARY, seed=5)
    run.world.hero.hp = 40
    clear_current_stage(run)

    assert run.world.hero.hp == 40 + HERO.heal_between_stages
    assert run.healed == HERO.heal_between_stages


def test_the_heal_cannot_take_you_above_full_health() -> None:
    run = Run.start(campaign(3), BESTIARY, seed=5)
    run.world.hero.hp = HERO.hp - 5
    clear_current_stage(run)

    assert run.world.hero.hp == HERO.hp
    assert run.healed == 5, "should report what was actually restored"


def test_advancing_is_announced_once_and_then_forgotten() -> None:
    # Drained like an event -- the banner must not stay up for the whole stage.
    run = Run.start(campaign(3), BESTIARY, seed=5)
    clear_current_stage(run)
    assert run.just_advanced

    step(run.world)
    run.settle()
    assert not run.just_advanced


# --- ending ------------------------------------------------------------------
def test_clearing_the_final_stage_wins_the_run() -> None:
    run = Run.start(campaign(2), BESTIARY, seed=5)
    clear_current_stage(run)
    assert run.outcome is RunOutcome.RUNNING

    clear_current_stage(run)
    assert run.outcome is RunOutcome.WON
    assert run.is_over


def test_a_one_stage_campaign_is_won_by_clearing_it() -> None:
    run = Run.start(campaign(1), BESTIARY, seed=5)
    clear_current_stage(run)
    assert run.outcome is RunOutcome.WON


def test_dying_loses_the_run_from_any_stage() -> None:
    run = Run.start(campaign(3), BESTIARY, seed=5)
    clear_current_stage(run)
    assert run.stage_number == 2

    run.world.hero.hp = 0
    step(run.world)
    run.settle()

    assert run.outcome is RunOutcome.LOST
    assert run.is_over


def test_settling_a_finished_run_changes_nothing() -> None:
    # The play scene calls settle() every tick without checking.
    run = Run.start(campaign(1), BESTIARY, seed=5)
    clear_current_stage(run)
    assert run.outcome is RunOutcome.WON

    run.settle()
    run.settle()
    assert run.outcome is RunOutcome.WON
    assert run.stage_number == 1


def test_settling_mid_stage_does_nothing() -> None:
    run = Run.start(campaign(3), BESTIARY, seed=5)
    for _ in range(20):
        step(run.world)
        run.settle()
    assert run.stage_number == 1
    assert run.outcome is RunOutcome.RUNNING


# --- restarting --------------------------------------------------------------
def test_restarting_returns_to_stage_one_at_full_health() -> None:
    run = Run.start(campaign(3), BESTIARY, seed=5)
    run.world.hero.hp = 20
    clear_current_stage(run)
    assert run.stage_number == 2

    fresh = run.restart()
    assert fresh.stage_number == 1
    assert fresh.world.hero.hp == HERO.hp
    assert fresh.outcome is RunOutcome.RUNNING


def test_the_campaign_is_never_mutated_by_a_run() -> None:
    """What lets a restart work without re-reading anything from disk."""
    original = campaign(3)
    run = Run.start(original, BESTIARY, seed=5)
    clear_current_stage(run)
    run.restart()

    assert run.campaign is original
    assert original.stages == campaign(3).stages


# --- seeding -----------------------------------------------------------------
def test_stages_do_not_all_roll_the_same_numbers() -> None:
    """Without an offset per stage, every stage draws the same damage rolls in
    the same order -- duller, and a poor test, since a bug that needs a
    particular sequence would never appear twice in a run."""
    run = Run.start(campaign(3), BESTIARY, seed=5)
    first = run.world.seed
    clear_current_stage(run)
    assert run.world.seed != first


def test_the_same_seed_replays_the_same_run() -> None:
    def play(seed: int):
        run = Run.start(campaign(3), BESTIARY, seed=seed)
        seeds = [run.world.seed]
        for _ in range(2):
            clear_current_stage(run)
            seeds.append(run.world.seed)
        return seeds

    assert play(11) == play(11)
    assert play(11) != play(12)
