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
from hack_and_slash.core import campaign_io
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import jobs
from hack_and_slash.game.autoplay import (
    REACTION_SLOPPY,
    Autoplay,
    autoplay,
    play_out,
    play_run_out,
    reckless,
)
from hack_and_slash.game.intent import NOTHING, Intent
from hack_and_slash.game.run import Run, RunOutcome
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Outcome, World

from hack_and_slash.game.entities import DEFAULT_HERO

from .helpers import BESTIARY, HERO, open_room

#: Generous. A competent hero clears a stage in well under this; the ceiling is
#: here so one that can no longer reach anything fails the test instead of
#: hanging the suite.
TICK_LIMIT = 9000

#: A whole run is forty stages, so it needs headroom the single-stage limit does
#: not. Still a guard, not a target -- a healthy run finishes in well under half
#: of it, and the value exists so a run that has stopped being winnable fails
#: the suite instead of hanging it. Doubled with the campaign; it was 120000 at
#: twenty stages and the same fraction of a real run either way.
RUN_TICK_LIMIT = 240000

#: Enough seeds that a bracket assertion is about the balance rather than about
#: one lucky fight. The sim is deterministic, so each is a fixed outcome.
SEEDS = range(6)

#: Fewer, for the four classes that are not the reference. The per-stage sweep
#: costs twenty stages times the seed count times a class, and the full matrix
#: is a minute of wall time that nobody wants on every save. Three seeds still
#: catches a class that is broken; `tools/balance.py --class all` is where the
#: full matrix lives when the question is tuning rather than regression.
CLASS_SEEDS = range(3)

#: The stage the game was originally tuned around, and the only one whose
#: numbers are on record. Index 2 -- "The Gauntlet". Deliberately unmoved by the
#: expansion to twenty stages and again by the expansion to forty: it is the
#: single fixed point the balance harness can be checked against, and it is only
#: worth anything if it stays put.
RECORDED_STAGE = 2

#: The shape of the campaign, derived from one number rather than written out
#: three times. Eight acts of five: four stages that build and a boss on the
#: fifth. Written this way because the four separate literals it replaced --
#: boss indices, act starts, a stage count and a boss count -- could disagree
#: with each other, and three of them were bare tuples that had to be found by
#: hand when the campaign doubled.
STAGES_PER_ACT = 5
ACT_COUNT = 8
STAGE_COUNT = STAGES_PER_ACT * ACT_COUNT

#: Where each act begins. Zero-based, so act I starts at 0 and act VIII at 35.
ACT_STARTS = tuple(act * STAGES_PER_ACT for act in range(ACT_COUNT))

#: Bosses close acts. Zero-based indices, so stages 5, 10, 15, 20, 25, 30, 35
#: and 40 -- and note stage 20 is the one the fork follows, so the four after it
#: are fought by an advanced class and the four before it are not.
BOSS_STAGES = tuple(start + STAGES_PER_ACT - 1 for start in ACT_STARTS)

#: The two halves of the campaign, split at the fork, as zero-based indices.
#:
#: This is the single most important line in the file for anyone extending it.
#: A stage is not "hard" or "easy" in the abstract -- it is hard *for the hero
#: that fights it*, and which hero that is changes exactly once, at
#: `jobs.PROMOTION_STAGE`. Sweeping a base class over stage 30 measures a
#: matchup the game cannot produce, and every failure it reports is a fiction.
BASE_STAGES = range(jobs.PROMOTION_STAGE - 1)
ADVANCED_STAGES = range(jobs.PROMOTION_STAGE - 1, STAGE_COUNT)

#: Two seeds for the advanced grid rather than the three the base grid uses.
#:
#: The shape of the cost is what decides this. The base grid is four classes
#: over twenty stages; the advanced grid is *ten* over twenty, because a
#: promotion doubles the roster, and at three seeds it would be six hundred
#: stage plays on every run of the suite.
#:
#: What two seeds buys and what it costs is on record for the base grid at
#: three: the Magician also fails stages 14 and 17 at six seeds and neither
#: shows up in the suite. Expect the same here -- this catches a class that
#: cannot clear a stage, not one that clears it half the time.
#: `tools/balance.py` is where the exhaustive version lives.
ADVANCED_SEEDS = range(2)


#: Read once. Forty stages off the disk, on every one of several hundred calls,
#: was the slowest thing in the suite by a wide margin -- and the campaign is
#: immutable, so there is nothing to be gained by rereading it.
_CAMPAIGN = campaign_io.load(config.LEVELS_DIR / "campaign.json")


def campaign():
    return _CAMPAIGN


def stage_world(
    index: int = RECORDED_STAGE, seed: int = 7, hero: str = DEFAULT_HERO
) -> World:
    """One stage in isolation, entered at full health."""
    return World(campaign()[index], BESTIARY, seed=seed, hero_type_id=hero)


def play(world: World, policy, limit: int = TICK_LIMIT) -> int:
    return play_out(world, policy, limit)


def wins_across_seeds(
    policy, index: int = RECORDED_STAGE, hero: str = DEFAULT_HERO, seeds=SEEDS
) -> int:
    """How many of the given seeds this policy clears one stage on."""
    won = 0
    for seed in seeds:
        world = stage_world(index, seed, hero)
        play(world, policy)
        won += world.outcome is Outcome.WON
    return won


def play_run(policy, seed: int, hero: str = DEFAULT_HERO, job: str = "") -> Run:
    """A whole run, stage one to the end, with health carrying between.

    `job` is the branch taken at the fork. Left empty the run never promotes,
    which is what every bracket recorded before acts V-VIII existed assumes --
    so those brackets keep measuring what they measured.
    """
    run = Run.start(campaign(), BESTIARY, seed=seed, hero_type_id=hero)
    play_run_out(run, policy, RUN_TICK_LIMIT, job)
    return run


def why_not(index: int, hero: str, seeds=SEEDS) -> str:
    """Why a stage did not clear, in the terms that tell the two causes apart.

    Only ever called from inside a failing assertion's message, which Python
    does not evaluate unless the assertion fails -- so this costs nothing on the
    hundreds of cells that pass.

    It exists because the two causes look identical in a win count and are
    nothing alike:

      * The hero died. That is a balance question, and the levers are in
        `docs/balance.md` in the order to reach for them.
      * The hero ran out of ticks while healthy, with something still at full
        health. That is not difficulty at all -- it is an enemy parked outside
        its own aggro radius or in a pocket with no line of sight, which nothing
        paths around because nothing in this game paths. The stage cannot be
        finished by anybody and no amount of tuning will fix it.

    Three late stages shipped with the second fault during the acts V-VIII pass
    and cost an afternoon before somebody counted what was still alive.
    """
    lines = []
    for seed in seeds:
        world = stage_world(index, seed, hero)
        ticks = play(world, autoplay)
        if world.outcome is Outcome.WON:
            continue
        alive = [e for e in world.enemies() if e.is_alive]
        untouched = [e for e in alive if e.hp == e.type.hp]
        hero_hp = world.hero.hp if world.hero else 0
        if world.hero is None or hero_hp <= 0:
            lines.append(f"seed {seed}: died on tick {ticks}, {len(alive)} still up")
        else:
            kinds = sorted({e.type.id for e in untouched})
            lines.append(
                f"seed {seed}: ran out of ticks on {hero_hp} hp with "
                f"{len(alive)} alive and {len(untouched)} NEVER TOUCHED "
                f"({', '.join(kinds) or 'none'}) -- likely a spawn nothing "
                "reaches rather than a difficulty problem"
            )
    return "\n    " + "\n    ".join(lines)


def first_branch(hero: str) -> str:
    """The promotion on key 1 for this class, or "" if it has none.

    Every whole-run bracket takes this one. It has to take *something* -- a run
    that declines cannot happen at a keyboard either, and half the campaign is
    tuned for a promoted hero -- and picking by index rather than by name keeps
    the choice out of this file: index 0 is what `data/entities.json` lists
    first, which is what the panel puts on key 1.

    The other branch is not left unmeasured; it is covered per stage by the
    advanced grid below, which runs all ten. What is not covered is a *run*
    through the second branch, and that is the affordable half of the trade --
    a whole forty-stage run is a hundred times the work of one stage.
    """
    offers = BESTIARY.promotions_for(hero)
    return offers[0].id if offers else ""


def runs_won(policy, hero: str = DEFAULT_HERO, seeds=SEEDS, job: str | None = None) -> int:
    branch = first_branch(hero) if job is None else job
    return sum(
        play_run(policy, seed, hero, branch).outcome is RunOutcome.WON for seed in seeds
    )


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

    **This was a strict xfail and is not any more.** At twenty stages the
    artifact had faded out: both policies finished 6/6 runs, the strict `>`
    failed, and rather than delete the test it was recorded as a live question
    -- *reconsider which policy is the reference*.

    Forty stages answered it, emphatically. The twitchy policy now finishes
    **0/6** where the reference finishes 6/6, and five of its six runs end on
    stage 25 -- the Herald, the first boss on the far side of the fork. That is
    the artifact in its purest form: a hero that rolls at every telegraph
    against a boss that is telegraphing half the time never swings back, and
    the four extra bosses gave it four more places to prove it.

    The xfail was doing its job the whole time. It went red the moment the claim
    became true again, which is the entire argument for `strict=True`, and the
    decision it forced was "it was fixed" rather than "the test rotted".
    """
    from hack_and_slash.game.autoplay import twitchy

    assert autoplay.reaction_ticks > twitchy.reaction_ticks
    assert runs_won(autoplay) > runs_won(twitchy), (
        "the twitchy policy now does at least as well as the measured one -- "
        "the artifact this guards against may have gone away, in which case "
        "reconsider which policy is the reference rather than deleting this"
    )


# --- the same bracket, one level up ------------------------------------------
# A run is not twenty independent fights: health carries between stages, so it
# can be unwinnable while every stage is fine on its own, and every stage can be
# fine while stage 12 is a wall. Both levels are checked, because neither
# implies the other.
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

    The reference class only covers the stages it can actually reach. Nobody
    fights stage 21 as a Knight -- the fork is compulsory and it is behind them
    by then -- so checking those twenty with a base class would be measuring a
    hero the game never produces, and failing on it would be reporting a
    difficulty problem that does not exist. `BASE_STAGES` is that boundary, and
    `test_every_late_stage_is_clearable_by_every_advanced_class` is the other
    side of it.
    """
    stages = campaign().stages
    for index in BASE_STAGES:
        won = wins_across_seeds(autoplay, index)
        assert won == len(SEEDS), (
            f"stage {index + 1} ({stages[index].name}) is clearable on only "
            f"{won}/{len(SEEDS)} seeds from full health"
            + why_not(index, DEFAULT_HERO)
        )


# --- and again, for everyone who is not the reference class ------------------
# The reference class is checked exhaustively above. These run the same three
# questions over the other four at a reduced seed count: enough to catch a class
# that cannot finish the game, cheap enough to keep in the regression suite.
# `tools/balance.py --class all` is the exhaustive version.
OTHER_CLASSES = [c.id for c in BESTIARY.hero_classes if c.id != DEFAULT_HERO]


#: Cells the reference policy cannot clear, recorded rather than left red.
#:
#: These are open balance work and the xfails are strict, so fixing one turns
#: the suite red until its entry is deleted -- the list cannot rot into a
#: permanent excuse.
#:
#: **The Magician is a trap and the fix is not known.** It is the only class
#: with any entry here; the other four clear all twenty stages on every seed.
#: Four things have been measured and ruled out, recorded so nobody spends the
#: afternoon again:
#:
#:   * *The stages are not at fault.* Knight, Rogue, Archer and Priest each
#:     clear all twenty stages 6/6. Stage 12 is not a bad stage -- it is the
#:     sharpest instance of a class-wide weakness that also shows on 14 and 17.
#:   * *arcane_bolt recovery 16 -> 13 relocates the failure.* It cleans up
#:     stages 12 and 14, then breaks 9 (6/6 -> 4/6) and craters 17 (5/6 ->
#:     1/6), and takes the campaign from 1/3 to 0/3 on these seeds.
#:   * *It is not fragility.* Health 105 -> 120 moves the stage 12 win rate not
#:     at all -- 3/8 either way -- it only leaves more health unspent. The class
#:     dies because it cannot act, not because it cannot take a hit.
#:   * *It is not damage.* 15 -> 17 finishes with half the health left, because
#:     a longer trade is a worse trade.
#:
#: So the dial is commitment, and no single dial tried so far moves it without
#: breaking something else. `tools/balance.py --class magician --full` and a
#: joint sweep is where a real fix comes from.
#:
#: One thing that looked like a cause and is not: `autoplay._threat_range` had
#: a dead `min()` that never clamped the charge threat range, so the bot answers
#: a charge from 127px out. Capping it as the code claimed to is *worse* -- it
#: costs the Archer a run and the Magician two more stages -- so the cap was
#: deleted rather than honoured and the behaviour is unchanged. See that
#: function for the numbers; nothing here shifted as a result.
UNTUNED_STAGES = {
    ("magician", 11): (
        "the Magician clears stage 12 (The Terraces) on 2/3 seeds. Open balance "
        "work -- see UNTUNED_STAGES for what has been ruled out"
    ),
}

#: Run-level failures that follow from the above. Same rules, same list.
UNTUNED_CAMPAIGNS = {
    "magician": (
        "the Magician completes 1/3 runs, dying on stage 12 both times. Open "
        "balance work -- see UNTUNED_STAGES for what has been ruled out"
    ),
}


def _marks(reason: str | None):
    return (pytest.mark.xfail(strict=True, reason=reason),) if reason else ()


def _stage_grid():
    """Every non-reference class against every stage it can reach, one test each.

    One case per cell rather than a loop over all of them, so a class that
    fails on one stage reports as that one cell rather than stopping the sweep
    at the first failure and hiding whatever came after it. That is the fault
    this grid exists to fix: the reference-class version above walks the stages
    in a loop, and until this was added a class could fail three separate
    stages and surface only as an intermittent run-level failure.

    `BASE_STAGES` rather than the whole campaign -- a base class never fights
    past the fork. See the note on that constant.
    """
    for hero in OTHER_CLASSES:
        for index in BASE_STAGES:
            yield pytest.param(
                hero,
                index,
                marks=_marks(UNTUNED_STAGES.get((hero, index))),
                id=f"{hero}-stage{index + 1}",
            )


def _advanced_stage_grid():
    """Every advanced class against every stage after the fork.

    The other half of the grid, and the half that did not exist while promotion
    bought one fight. Ten classes rather than five, because a fork doubles the
    roster, and twenty stages rather than forty, because none of these ten is
    ever the hero before stage 21.

    No promotion machinery is involved and none is needed: `World` takes a
    `hero_type_id`, the bestiary holds the advanced classes, so a cell is just
    that class dropped into that arena at full health. Promotion only has to
    actually happen for the run-level bracket, where the carry between stages
    is the thing under test.

    What this measures is narrower than it looks, and the narrowness is the
    point. The reference bot presses the light attack and nothing else, and an
    advanced class's light is the one it inherited -- so this is the *base*
    class's swing with the advanced class's health and body. The twenty new
    heavies and ultimates are still unmeasured, exactly as the first fifteen
    attacks are, which is deliberate: it means acts V-VIII are clearable
    without them, and the new kit is upside rather than a requirement.
    """
    for advanced in BESTIARY.advanced_classes:
        for index in ADVANCED_STAGES:
            yield pytest.param(
                advanced.id,
                index,
                marks=_marks(UNTUNED_STAGES.get((advanced.id, index))),
                id=f"{advanced.id}-stage{index + 1}",
            )


@pytest.mark.parametrize("hero,index", list(_stage_grid()))
def test_every_stage_is_clearable_by_every_class(hero: str, index: int) -> None:
    """The per-stage check above, for the four classes it does not cover.

    Run at `CLASS_SEEDS` rather than `SEEDS` to keep the matrix affordable --
    eighty cells at three seeds rather than six. That is a real reduction in
    what it catches: at six seeds the Magician also fails stage 14 and stage 17
    (5/6 each), and neither shows up here because the seed that beats it is in
    3..5. `tools/balance.py --class all` is the version that sees those.
    """
    won = wins_across_seeds(autoplay, index, hero, CLASS_SEEDS)
    assert won == len(CLASS_SEEDS), (
        f"the {hero} clears stage {index + 1} ({campaign()[index].name}) on only "
        f"{won}/{len(CLASS_SEEDS)} seeds from full health"
        + why_not(index, hero, CLASS_SEEDS)
    )


@pytest.mark.parametrize("hero,index", list(_advanced_stage_grid()))
def test_every_late_stage_is_clearable_by_every_advanced_class(
    hero: str, index: int
) -> None:
    """The same question for the half of the campaign nothing used to reach.

    A branch that cannot clear act VII is not a choice, it is a run ended by a
    keypress twenty stages earlier -- and the promotion panel gives no warning
    and takes no refusals. Ten of these ship; ten of them have to work.
    """
    won = wins_across_seeds(autoplay, index, hero, ADVANCED_SEEDS)
    assert won == len(ADVANCED_SEEDS), (
        f"the {hero} clears stage {index + 1} ({campaign()[index].name}) on only "
        f"{won}/{len(ADVANCED_SEEDS)} seeds from full health"
        + why_not(index, hero, ADVANCED_SEEDS)
    )


@pytest.mark.parametrize(
    "hero",
    [
        pytest.param(hero, marks=_marks(UNTUNED_CAMPAIGNS.get(hero)), id=hero)
        for hero in OTHER_CLASSES
    ],
)
def test_every_class_can_finish_the_campaign(hero: str) -> None:
    """A class that cannot complete a run is not a choice, it is a trap.

    This is the test the whole roster hangs on: five classes are five separate
    balance problems, and the four that are not the Knight get no coverage at
    all from anything above.
    """
    won = runs_won(autoplay, hero, CLASS_SEEDS)
    assert won == len(CLASS_SEEDS), (
        f"the {hero} completes only {won}/{len(CLASS_SEEDS)} runs -- the cause is "
        "commitment rather than heal_between_stages; run tools/balance.py "
        f"--class {hero} for the per-stage rows"
    )


@pytest.mark.parametrize("hero", OTHER_CLASSES)
def test_no_class_walks_the_campaign(hero: str) -> None:
    """The ceiling, per class. A class that wins while refusing to disengage is
    not a strong class, it is one the arena stopped applying to."""
    assert runs_won(reckless, hero, CLASS_SEEDS) == 0, (
        f"the {hero} finishes runs while walking in swinging"
    )


@pytest.mark.parametrize("hero", ["archer", "magician"])
def test_a_ranged_class_fights_from_range(hero: str) -> None:
    """The measuring instrument, not the game.

    `autoplay` engages at `weapon.reach`, which is zero for a projectile -- so
    before it learned about ranged weapons it walked a bow hero to a pixel from
    a grunt before firing, and every number it reported about these two classes
    was a number about how badly they melee.

    Asserting on the *distance* rather than on the win, because winning is what
    the balance tests already cover and it would pass either way.
    """
    from hack_and_slash.game.autoplay import RANGED_TOO_CLOSE

    world = World(open_room(50, 20), BESTIARY, seed=1, hero_type_id=hero)
    enemy = _add(world, "grunt", world.hero.pos + Vec2(200, 0))

    closest = float("inf")
    for _ in range(600):
        if world.outcome is not Outcome.RUNNING or not enemy.is_alive:
            break
        step(world, autoplay(world))
        closest = min(closest, world.hero.pos.distance_to(enemy.pos))

    assert not enemy.is_alive, f"the {hero} never killed a lone grunt"
    assert closest > RANGED_TOO_CLOSE * 0.5, (
        f"the {hero} closed to {closest:.0f}px -- it is being played as a melee "
        "class, so any balance number measured for it is meaningless"
    )


def _add(world: World, type_id: str, pos: Vec2):
    from .helpers import add_enemy

    return add_enemy(world, type_id, pos)


def test_a_run_carries_damage_forward() -> None:
    """The mechanism the run-level bracket is actually testing.

    Without this, a run is four separate fights and the whole layer is
    decoration.
    """
    run = play_run(autoplay, seed=3, job=first_branch(DEFAULT_HERO))
    assert run.outcome is RunOutcome.WON
    # Finishing a forty-stage run on full health would mean nothing ever stuck.
    # Measured against the promoted maximum, which is the hero that finishes.
    assert run.world.hero.hp < run.hero_type.hp


def test_the_heal_between_stages_is_the_class_s_own() -> None:
    """The Priest is a run-level class, so this is the Priest working.

    It looks like a detail and it is the whole reason that class exists: with a
    shared heal there would be no mechanical difference between picking the
    Priest and picking anyone else with 95 health.
    """
    priest, knight = BESTIARY["priest"], BESTIARY["knight"]
    assert priest.heal_between_stages > knight.heal_between_stages

    healed = {}
    for hero in ("priest", "knight"):
        run = Run.start(campaign(), BESTIARY, seed=5, hero_type_id=hero)
        # Take the hero down so the heal has room to show, then clear the stage.
        run.world.hero.hp = 20
        for _ in range(TICK_LIMIT):
            step(run.world, autoplay(run.world))
            run.settle()
            if run.just_advanced:
                break
        healed[hero] = run.healed

    assert healed["priest"] > healed["knight"], (
        f"the Priest recovered {healed['priest']} and the Knight "
        f"{healed['knight']} -- the heal is not being read off the class"
    )


def test_the_difficulty_curve_rises_within_each_act() -> None:
    """A crude proxy, and labelled as one.

    Enemy count is a poor measure of difficulty -- a boss is one enemy, and the
    real measure is the per-stage rows in `tools/balance.py`. What it does catch
    is a stage accidentally emptier than the one before it.

    Checked *per act* rather than across the campaign. An act opens on a new
    enemy and deserves room to introduce it, so stage 6 having fewer bodies than
    stage 4 is the design working rather than the curve sagging. Boss stages are
    excluded entirely: they are deliberately the sparsest in the game.
    """
    stages = campaign().stages
    for act, start in enumerate(ACT_STARTS, start=1):
        build = stages[start : start + STAGES_PER_ACT - 1]
        counts = [len(stage.enemy_spawns) for stage in build]
        assert counts == sorted(counts), f"act {act} enemy counts do not rise: {counts}"
        assert counts[0] < counts[-1], f"act {act} does not build: {counts}"


def test_every_act_ends_on_a_boss_and_nothing_else_does() -> None:
    """Eight acts of five, and the shape has to be real rather than intended.

    A boss turning up mid-act is the loud failure; the quiet one is an act
    ending on an ordinary stage because a `Stage` entry was inserted rather than
    replaced, which shifts every boss one place and is invisible in a diff.
    """
    bosses = {t.id for t in BESTIARY.types.values() if t.brain == "boss"}
    stages = campaign().stages

    assert len(stages) == STAGE_COUNT, (
        f"the campaign is {len(stages)} stages, not {STAGE_COUNT}"
    )

    for index, stage in enumerate(stages):
        has_boss = any(spawn.type_id in bosses for spawn in stage.enemy_spawns)
        if index in BOSS_STAGES:
            assert has_boss, f"stage {index + 1} ({stage.name}) ends an act with no boss"
        else:
            assert not has_boss, f"stage {index + 1} ({stage.name}) has a boss mid-act"


def test_no_boss_is_used_twice() -> None:
    """Eight acts, eight bosses. Reusing one would make an act's ending a repeat
    of an earlier one, which is the single thing a boss stage cannot be."""
    bosses = {t.id for t in BESTIARY.types.values() if t.brain == "boss"}
    used = [
        spawn.type_id
        for stage in campaign().stages
        for spawn in stage.enemy_spawns
        if spawn.type_id in bosses
    ]
    assert len(used) == len(set(used)) == len(BOSS_STAGES), f"bosses used: {used}"


def test_no_boss_stage_is_escorted_by_anything_ranged() -> None:
    """A standing constraint on level design, enforced for the first time here.

    A ranged escort never becomes the nearest thing in the room, so it is never
    what the player is fighting, so it never dies -- it is a damage tax for the
    length of the fight with no answer available. The act III boss stage was
    drafted with two bowmen and was unwinnable on every seed.

    It has been a comment in three files and a rule in nobody's way since. Eight
    boss stages is four more chances to get it wrong than the rule survived the
    first time, and the failure is a stage that is simply impossible rather than
    one that is merely hard.
    """
    ranged = {t.id for t in BESTIARY.types.values() if t.brain == "archer"}
    stages = campaign().stages

    assert ranged, "no ranged enemies found -- this test has stopped checking anything"

    for index in BOSS_STAGES:
        stage = stages[index]
        offenders = sorted({s.type_id for s in stage.enemy_spawns if s.type_id in ranged})
        assert not offenders, (
            f"stage {index + 1} ({stage.name}) escorts its boss with {offenders}; "
            "boss stages take melee escorts only"
        )


def test_a_boss_outranks_its_own_escort() -> None:
    """The per-stage half of the level ladder, and the one loot actually sees.

    A boss and the grunts around it share a floor number, so depth cannot tell
    them apart -- `level` is the only thing that can, and a boss kill paying an
    escort's wage is the exact failure the field exists to prevent.

    Checked per stage rather than across the bestiary because that is the only
    place the comparison means anything: the Warden is a level 5 fought on stage
    5 and the stalker a level 6 first met on stage 26, and no kill ever weighs
    those two against each other.
    """
    stages = campaign().stages

    for index in BOSS_STAGES:
        stage = stages[index]
        levels = [BESTIARY[s.type_id].level for s in stage.enemy_spawns]
        boss = max(
            BESTIARY[s.type_id].level
            for s in stage.enemy_spawns
            if BESTIARY[s.type_id].brain == "boss"
        )
        escort = [lvl for lvl in levels if lvl != boss]
        assert escort, f"stage {index + 1} ({stage.name}) has no escort at all"
        assert boss > max(escort), (
            f"stage {index + 1} ({stage.name}): the boss ranks {boss} and its "
            f"escort ranks up to {max(escort)}"
        )


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
