"""Measures how hard the game actually is, per stage and across a whole run.

    python tools/balance.py
    python tools/balance.py --seeds 24

Runs reference heroes over many seeds and prints what happened, so tuning is an
argument about numbers rather than about how the game felt on the afternoon
someone changed it.

**Two brackets, because they can fail independently.**

    per stage  skilled clears each stage from full health
    whole run  skilled finishes all four with health carrying between them

A run can be unwinnable while every stage is fine on its own -- that is the heal
between stages being too small. Every stage can be fine while the run is easy --
that is the heal being too large. And one stage can be a wall the player only
gets past because the two before it were generous, which only the per-stage rows
show.

Both ends of each bracket matter:

    skilled    must win     -- a player doing the right things always can
    face-tank  must lose    -- walking in swinging has to cost you the run

**The reaction ladder** is informational, and it is not flat -- the zero-tick row
is an outlier that loses most runs while every slower row wins comfortably.

That is a fact about the *instrument*, not the game, and it is worth knowing.
A hero that answers every telegraph on the tick it opens rolls perpetually
against something that is winding up or swinging half the time, and never swings
back. The boss is where that became visible; it stayed harmless while every
fight was ordinary enemies with gaps between their attacks. So `skilled` is the
twelve-tick row, not the zero-tick one: a reflex that fast is not skill.

Across the slower rows the ladder is genuinely flat, which is the older finding
still holding -- reaction time is not what decides these fights. Disengaging
when hurt is, which is why the ceiling is a hero that refuses to.

**On trusting any of this.** These bots have perfect information, and only the
crudest sense that pillars exist. They bracket the game; they do not tell you
whether it is any *fun*. That still takes hands on a keyboard.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hack_and_slash import config  # noqa: E402
from hack_and_slash.core import campaign_io  # noqa: E402
from hack_and_slash.game.autoplay import (  # noqa: E402
    REACTION_PERFECT,
    REACTION_SHARP,
    REACTION_SLOPPY,
    Autoplay,
    autoplay,
    play_out,
    reckless,
)
from hack_and_slash.game.entities import load_bestiary  # noqa: E402
from hack_and_slash.game.run import Run, RunOutcome  # noqa: E402
from hack_and_slash.game.sim import step  # noqa: E402
from hack_and_slash.game.world import Outcome, World  # noqa: E402

LATENCIES = [
    ("perfect", REACTION_PERFECT),
    ("sharp", REACTION_SHARP),
    ("sloppy", REACTION_SLOPPY),
    ("asleep", 40),
]

RUN_TICK_LIMIT = 40000

HEADER = f"{'':>16}  {'won':>7}  {'median':>7}  {'median hp':>9}  {'worst hp':>8}"
RULE = "  " + "-" * 56


def summarise(wins: int, total: int, seconds: list[float], hp: list[int]) -> dict:
    return {
        "wins": wins,
        "total": total,
        "median_seconds": statistics.median(seconds) if seconds else None,
        "median_hp": statistics.median(hp) if hp else None,
        "worst_hp": min(hp) if hp else None,
    }


def measure_stage(level, bestiary, policy, seeds: range) -> dict:
    """One stage in isolation, entered at full health."""
    wins, seconds, hp_left = 0, [], []
    for seed in seeds:
        world = World(level, bestiary, seed=seed)
        ticks = play_out(world, policy)
        if world.outcome is Outcome.WON:
            wins += 1
            seconds.append(ticks / config.TICKS_PER_SEC)
            hp_left.append(world.hero.hp if world.hero else 0)
    return summarise(wins, len(seeds), seconds, hp_left)


def measure_run(campaign, bestiary, policy, seeds: range) -> dict:
    """A whole run, with health carrying between stages."""
    wins, seconds, hp_left = 0, [], []
    for seed in seeds:
        run = Run.start(campaign, bestiary, seed=seed)
        ticks = 0
        for ticks in range(RUN_TICK_LIMIT):
            if run.is_over:
                break
            step(run.world, policy(run.world))
            run.settle()
        if run.outcome is RunOutcome.WON:
            wins += 1
            seconds.append(ticks / config.TICKS_PER_SEC)
            hp_left.append(run.world.hero.hp if run.world.hero else 0)
    return summarise(wins, len(seeds), seconds, hp_left)


def row(label: str, data: dict) -> str:
    clear = f"{data['median_seconds']:.0f}s" if data["median_seconds"] else "--"
    median_hp = f"{data['median_hp']:.0f}" if data["median_hp"] is not None else "--"
    worst_hp = f"{data['worst_hp']}" if data["worst_hp"] is not None else "--"
    return (
        f"{label:>16}  {data['wins']:>3}/{data['total']:<3}  "
        f"{clear:>7}  {median_hp:>9}  {worst_hp:>8}"
    )


def verdict(stages: list[tuple[str, dict]], run_skilled: dict, run_tank: dict) -> list[str]:
    notes = []

    for name, data in stages:
        if data["wins"] < data["total"]:
            notes.append(
                f"{name} is clearable on only {data['wins']}/{data['total']} seeds "
                "from full health -- that stage is a wall, not a difficulty step"
            )

    if run_skilled["wins"] < run_skilled["total"]:
        notes.append(
            f"a skilled hero finishes only {run_skilled['wins']}/{run_skilled['total']} "
            "runs -- if every stage passes on its own, the heal between stages is "
            "too small to sustain a run"
        )
    elif run_skilled["worst_hp"] is not None and run_skilled["worst_hp"] > 70:
        # Judged on the *worst* run rather than the median. A high median with a
        # low worst case is variance, which is what a run should have; a high
        # worst case means no seed ever put the hero in danger, which is slack.
        notes.append(
            f"even the worst run finishes on {run_skilled['worst_hp']} hp -- no seed "
            "ever put the hero in danger, so the stages are not adding up to a run"
        )

    if run_tank["wins"] > 0:
        notes.append(
            f"walking in swinging finishes {run_tank['wins']}/{run_tank['total']} runs "
            "-- the ceiling is broken and the game does not punish playing badly"
        )

    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=8)
    args = parser.parse_args()

    campaign = campaign_io.load(config.LEVELS_DIR / "campaign.json")
    bestiary = load_bestiary(config.ENTITIES_DATA, config.WEAPONS_DATA)
    seeds = range(args.seeds)
    skilled = autoplay

    print(f"{campaign.name}  --  {len(campaign)} stages, {args.seeds} seeds")

    print("\nper stage, skilled, entered at full health")
    print(HEADER)
    print(RULE)
    stage_rows = []
    for index, level in enumerate(campaign.stages, start=1):
        data = measure_stage(level, bestiary, skilled, seeds)
        stage_rows.append((f"stage {index} ({level.name})", data))
        print(row(f"{index}. {level.name}", data))

    print("\nwhole run, health carrying between stages")
    print(HEADER)
    print(RULE)
    run_skilled = measure_run(campaign, bestiary, skilled, seeds)
    run_tank = measure_run(campaign, bestiary, reckless, seeds)
    print(row("skilled", run_skilled))
    print(row("face-tank", run_tank))

    print("\nreaction ladder on the run -- informational; see the docstring")
    print(HEADER)
    print(RULE)
    for name, ticks in LATENCIES:
        print(row(f"{name} ({ticks})", measure_run(campaign, bestiary, Autoplay(ticks), seeds)))

    print()
    notes = verdict(stage_rows, run_skilled, run_tank)
    if not notes:
        print("balance is where the design wants it. Leave the numbers alone.")
        return 0

    print("out of balance:")
    for note in notes:
        print(f"  - {note}")
    print(
        "\nLevers, in order. Enemy *durability* first -- an enemy that dies before its\n"
        "attack cadence lets it swing again applies no pressure however hard it hits.\n"
        "Then count and placement (tools/make_level.py), then cadence\n"
        "(PAUSE_AFTER_ATTACK in game/ai.py). For a run that is failing while its\n"
        "stages pass, the lever is heal_between_stages on the hero. Enemy damage and\n"
        "hero hp last: raising damage makes one mistake lethal, which is a harsher\n"
        "game rather than a tighter one."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
