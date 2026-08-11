"""Measures how hard the fight actually is.

    python tools/balance.py
    python tools/balance.py --seeds 24 --level arena

Runs reference heroes over many seeds and prints what happened, so tuning is an
argument about numbers rather than about how the game felt on the afternoon
someone changed it.

**The bracket** is the part that decides anything:

    skilled    must win every seed  -- a player doing the right things always can
    face-tank  must lose every seed -- walking in swinging has to cost you the run

Both ends have to hold. Only the floor and the fight is unfair; only the ceiling
and there is no fight.

**The reaction ladder** below it is informational, and it records a finding
rather than a target: reaction time barely moves this fight. A hero that never
dodges finishes *healthier* than one with perfect reflexes, because rolling
costs uptime and lengthens the fight. That is why the bracket is built on
refusing to disengage instead of on reacting late -- the latter measured almost
nothing. Read the ladder as a description of the design, and be suspicious of it
becoming steep: that would mean dodging had started to carry the fight.

**On trusting any of this.** These bots have perfect information and no sense
that pillars exist. They bracket the fight; they do not tell you whether it is
any *fun*. That still takes hands on a keyboard.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hack_and_slash import config  # noqa: E402
from hack_and_slash.core import level_io  # noqa: E402
from hack_and_slash.game.autoplay import (  # noqa: E402
    REACTION_PERFECT,
    REACTION_SHARP,
    REACTION_SLOPPY,
    Autoplay,
    play_out,
    reckless,
)
from hack_and_slash.game.entities import load_bestiary  # noqa: E402
from hack_and_slash.game.world import Outcome, World  # noqa: E402

LATENCIES = [
    ("perfect", REACTION_PERFECT),
    ("sharp", REACTION_SHARP),
    ("sloppy", REACTION_SLOPPY),
    ("asleep", 40),
]


def measure(level, bestiary, policy, seeds: range) -> dict:
    wins, clear_times, hp_left = 0, [], []

    for seed in seeds:
        world = World(level, bestiary, seed=seed)
        ticks = play_out(world, policy)
        if world.outcome is Outcome.WON:
            wins += 1
            clear_times.append(ticks / config.TICKS_PER_SEC)
            hp_left.append(world.hero.hp if world.hero else 0)

    return {
        "wins": wins,
        "total": len(seeds),
        "median_seconds": statistics.median(clear_times) if clear_times else None,
        "median_hp": statistics.median(hp_left) if hp_left else None,
        "worst_hp": min(hp_left) if hp_left else None,
    }


def verdict(skilled: dict, face_tank: dict) -> list[str]:
    """The bracket, applied. Empty means the fight is where the design wants it."""
    notes = []

    if skilled["wins"] < skilled["total"]:
        notes.append(
            f"a skilled hero loses {skilled['total'] - skilled['wins']} seed(s) -- "
            "the floor is broken: doing the right things does not reliably win"
        )
    elif skilled["median_hp"] is not None and skilled["median_hp"] > 80:
        notes.append(
            f"a skilled hero finishes on {skilled['median_hp']:.0f} hp -- "
            "winning without ever being in danger"
        )

    if face_tank["wins"] > face_tank["total"] // 4:
        notes.append(
            f"walking in swinging still wins {face_tank['wins']}/{face_tank['total']} -- "
            "the ceiling is broken: the arena does not punish playing badly"
        )

    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--level", default="arena")
    args = parser.parse_args()

    level = level_io.load(config.LEVELS_DIR / f"{args.level}.json")
    bestiary = load_bestiary(config.ENTITIES_DATA, config.WEAPONS_DATA)
    seeds = range(args.seeds)

    print(f"{level.name}  --  {len(level.enemy_spawns)} enemies, {args.seeds} seeds")

    def row_line(label: str, row: dict) -> str:
        clear = f"{row['median_seconds']:.0f}s" if row["median_seconds"] else "--"
        median_hp = f"{row['median_hp']:.0f}" if row["median_hp"] is not None else "--"
        worst_hp = f"{row['worst_hp']}" if row["worst_hp"] is not None else "--"
        return (
            f"{label:>12}  {row['wins']:>3}/{row['total']:<3}  "
            f"{clear:>7}  {median_hp:>9}  {worst_hp:>8}"
        )

    header = f"{'':>12}  {'won':>7}  {'median':>7}  {'median hp':>9}  {'worst hp':>8}"

    print("\nthe bracket -- both ends must hold")
    print(header)
    print("  " + "-" * 52)
    skilled = measure(level, bestiary, Autoplay(REACTION_PERFECT), seeds)
    face_tank = measure(level, bestiary, reckless, seeds)
    print(row_line("skilled", skilled))
    print(row_line("face-tank", face_tank))

    print("\nreaction ladder -- informational; expected to be flat, see the docstring")
    print(header)
    print("  " + "-" * 52)
    for name, ticks in LATENCIES:
        print(row_line(f"{name} ({ticks})", measure(level, bestiary, Autoplay(ticks), seeds)))

    print()
    notes = verdict(skilled, face_tank)
    if not notes:
        print("balance is where the design wants it. Leave the numbers alone.")
        return 0

    print("out of balance:")
    for note in notes:
        print(f"  - {note}")
    print(
        "\nLevers, in order. Enemy *durability* first -- an enemy that dies before its\n"
        "attack cadence lets it swing again applies no pressure however hard it hits,\n"
        "and that is a matter of arithmetic rather than of taste. Then count and\n"
        "placement (tools/make_level.py), then cadence (PAUSE_AFTER_ATTACK in\n"
        "game/ai.py). Enemy damage and hero hp last: raising damage makes one mistake\n"
        "lethal, which is a harsher game rather than a tighter one."
    )
    # Not a failure exit: this is an instrument, not a gate. A tuning session
    # wants to see the numbers without a non-zero status muddying the output.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
