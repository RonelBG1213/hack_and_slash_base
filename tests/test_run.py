"""The layer above a single stage: carry-over, advancing, and how a run ends.

The distinction this file exists to protect: `World.outcome` says whether the
current arena is cleared, `Run.outcome` says whether the run is over. Clearing a
stage is only a win if there is nothing after it.
"""

from __future__ import annotations

from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.game import jobs
from hack_and_slash.game.run import Run, RunOutcome
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Outcome, World

from .helpers import BESTIARY, HERO, open_room


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


# --- the purse ---------------------------------------------------------------
def test_gold_survives_a_stage_transition() -> None:
    """A stage's takings are banked before the world holding them is replaced.

    `_advance` builds an entirely new `World`; whatever was on the old one goes
    with it. So the bank happens first, and this is the test that says so.
    """
    run = Run.start(campaign(), BESTIARY)
    clear_current_stage(run)

    assert run.gold > 0, "clearing a stage full of grunts paid nothing"
    assert run.world.gold == 0, "the new stage started with the last one's takings"


def test_gold_accumulates_across_stages() -> None:
    run = Run.start(campaign(4), BESTIARY)

    running = []
    for _ in range(3):
        clear_current_stage(run)
        running.append(run.gold)

    assert running == sorted(running)
    assert running[-1] > running[0]


def test_the_purse_shown_to_a_player_includes_the_stage_in_progress() -> None:
    """`gold` lags a stage behind by design; `gold_total` is the honest number.

    A purse that visibly ignores the coin you just walked over is worse than no
    purse at all.
    """
    run = Run.start(campaign(), BESTIARY)
    run.world.gold = 40

    assert run.gold == 0
    assert run.gold_total == 40


def test_a_deeper_stage_knows_which_floor_it_is() -> None:
    """The world cannot work this out for itself, and the payout depends on it."""
    run = Run.start(campaign(4), BESTIARY)
    assert run.world.purse.floor == 1

    clear_current_stage(run)
    assert run.world.purse.floor == 2


def test_starting_partway_in_arrives_on_the_floor_it_says() -> None:
    run = Run.start(campaign(6), BESTIARY, at_stage=3)
    assert run.world.purse.floor == 4


def test_a_lost_run_keeps_what_it_had_already_collected() -> None:
    run = Run.start(campaign(), BESTIARY)
    run.world.gold = 75
    run.world.hero.hp = 0
    step(run.world)
    run.settle()

    assert run.outcome is RunOutcome.LOST
    assert run.gold == 75


def test_banking_twice_does_not_pay_twice() -> None:
    """`settle` is called every tick and is meant to be idempotent.

    A death screen is up for as long as the player leaves it up, and `settle`
    keeps being called behind it.
    """
    run = Run.start(campaign(), BESTIARY)
    run.world.gold = 30
    run.world.hero.hp = 0
    step(run.world)

    for _ in range(20):
        run.settle()
    assert run.gold == 30


def test_winning_the_last_stage_banks_its_takings() -> None:
    run = Run.start(campaign(1), BESTIARY)
    clear_current_stage(run)

    assert run.outcome is RunOutcome.WON
    assert run.gold > 0


def test_a_bought_heal_adds_to_the_class_s_own() -> None:
    run = Run.start(campaign(), BESTIARY)
    hero = run.world.hero
    hero.hp = 10
    run.bonus_heal = 15

    clear_current_stage(run)
    assert run.world.hero.hp == 10 + HERO.heal_between_stages + 15


def test_gold_find_reaches_the_next_stage() -> None:
    run = Run.start(campaign(), BESTIARY)
    run.gold_find = 0.5

    clear_current_stage(run)
    assert run.world.purse.gold_find == 0.5


# --- a promotion has to survive the stage after it ---------------------------
# These matter because a promotion used to be the last thing that ever happened
# in a run. With twenty stages behind the fork, everything `_advance` rebuilds
# has to be rebuilt as the class the run became rather than the one it started
# as -- and the two are only ever different after a promotion, which is why
# nothing noticed for as long as there was no stage after one.
def test_a_promotion_survives_the_next_stage() -> None:
    """The body the next stage builds is the advanced class, not the base one.

    `_advance` constructs a fresh `World` for every transition. Handing it
    `hero_type_id` -- the class the run was *started* as -- silently un-promotes
    the hero on the very next stage boundary and leaves `job_id` claiming
    otherwise.
    """
    run = Run.start(campaign(4), BESTIARY, hero_type_id="knight")
    jobs.promote(run, BESTIARY["dark_knight"])
    assert run.world.hero.type.id == "dark_knight"

    clear_current_stage(run)

    assert run.world.hero.type.id == "dark_knight"
    assert run.job_id == "dark_knight"


def test_the_between_stage_heal_is_the_promoted_class_s_own() -> None:
    """The heal is read off the class being played now, maximum included.

    Inert at the old trigger, live at this one: every stage after the fork pays
    out, and it pays out against the advanced class's ceiling.
    """
    advanced = BESTIARY["dark_knight"]
    run = Run.start(campaign(4), BESTIARY, hero_type_id="knight")
    jobs.promote(run, advanced)
    run.world.hero.hp = 20

    clear_current_stage(run)
    assert run.world.hero.hp == 20 + advanced.heal_between_stages


def test_a_promoted_hero_is_not_healed_above_the_advanced_maximum() -> None:
    """A smaller advanced class must not inherit the base class's ceiling.

    The Dark Knight is 115 to the Knight's 130, so a carry clamped against the
    wrong maximum would hand it fifteen health it does not have.
    """
    advanced = BESTIARY["dark_knight"]
    run = Run.start(campaign(4), BESTIARY, hero_type_id="knight")
    jobs.promote(run, advanced)
    run.world.hero.hp = advanced.full_hp - 2

    clear_current_stage(run)
    assert run.world.hero.hp == advanced.full_hp


def test_restarting_after_a_promotion_returns_to_the_base_class() -> None:
    """`R` is a second attempt at the run, so it starts where the run started.

    `job_id` sits beside `hero_type_id` rather than overwriting it precisely so
    that this needs no knowledge of promotion to be correct.
    """
    run = Run.start(campaign(4), BESTIARY, hero_type_id="knight")
    jobs.promote(run, BESTIARY["dark_knight"])

    fresh = run.restart()
    assert fresh.job_id == ""
    assert fresh.hero_type.id == "knight"


def test_restarting_empties_the_purse_and_everything_bought_with_it() -> None:
    """A restart is a second attempt, not a continuation. Only the class carries."""
    run = Run.start(campaign(), BESTIARY)
    clear_current_stage(run)
    run.bonus_heal = 12
    run.gold_find = 0.75

    fresh = run.restart()
    assert fresh.gold == 0
    assert fresh.bonus_heal == 0
    assert fresh.gold_find == 0.0
    assert fresh.hero_type_id == run.hero_type_id
