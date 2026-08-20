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
    into,
    play_out,
    play_run_out,
    reckless,
    spread,
)
from hack_and_slash.game import jobs  # noqa: E402
from hack_and_slash.game.entities import DEFAULT_HERO, load_bestiary  # noqa: E402
from hack_and_slash.game.run import Run, RunOutcome  # noqa: E402
from hack_and_slash.game.world import Outcome, World  # noqa: E402

LATENCIES = [
    ("perfect", REACTION_PERFECT),
    ("sharp", REACTION_SHARP),
    ("sloppy", REACTION_SLOPPY),
    ("asleep", 40),
]

#: Forty stages, eight of them bosses. Six times the old four-stage guard,
#: which a healthy run still finishes in well under half of.
RUN_TICK_LIMIT = 240000

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


def measure_stage(level, bestiary, policy, seeds: range, hero: str = DEFAULT_HERO) -> dict:
    """One stage in isolation, entered at full health."""
    wins, seconds, hp_left = 0, [], []
    for seed in seeds:
        world = World(level, bestiary, seed=seed, hero_type_id=hero)
        ticks = play_out(world, policy)
        if world.outcome is Outcome.WON:
            wins += 1
            seconds.append(ticks / config.TICKS_PER_SEC)
            hp_left.append(world.hero.hp if world.hero else 0)
    return summarise(wins, len(seeds), seconds, hp_left)


def measure_run(
    campaign,
    bestiary,
    policy,
    seeds: range,
    hero: str = DEFAULT_HERO,
    job: str = "",
    allocate=None,
) -> dict:
    """A whole run, with health carrying between stages.

    `job` is the branch taken at the fork. Empty means the run never promotes --
    which is what every number recorded before acts V-VIII was measured with,
    and is why the first half of the campaign still reads the same here.

    `allocate` is how the hero spends what levelling pays. None -- the default,
    and what every recorded number here was measured with -- spends nothing.
    """
    wins, seconds, hp_left = 0, [], []
    for seed in seeds:
        run = Run.start(campaign, bestiary, seed=seed, hero_type_id=hero)
        ticks = play_run_out(run, policy, RUN_TICK_LIMIT, job, allocate)
        if run.outcome is RunOutcome.WON:
            wins += 1
            seconds.append(ticks / config.TICKS_PER_SEC)
            hp_left.append(run.world.hero.hp if run.world.hero else 0)
    return summarise(wins, len(seeds), seconds, hp_left)


def furthest_stage(
    campaign, bestiary, policy, seeds: range, hero: str, job: str = "", allocate=None
) -> tuple[int, str]:
    """Where the worst run of the set died, for a class that cannot finish.

    A row reading 0/8 says a class is broken but not where, and with forty
    stages "somewhere" is even less of an answer than it was with twenty. This
    gives the tuning pass the stage to look at first.
    """
    worst, name = len(campaign), ""
    for seed in seeds:
        run = Run.start(campaign, bestiary, seed=seed, hero_type_id=hero)
        play_run_out(run, policy, RUN_TICK_LIMIT, job, allocate)
        if run.outcome is not RunOutcome.WON and run.index < worst:
            worst, name = run.index, run.level.name
    return worst + 1, name


def row(label: str, data: dict) -> str:
    clear = f"{data['median_seconds']:.0f}s" if data["median_seconds"] else "--"
    median_hp = f"{data['median_hp']:.0f}" if data["median_hp"] is not None else "--"
    worst_hp = f"{data['worst_hp']}" if data["worst_hp"] is not None else "--"
    return (
        f"{label:>16}  {data['wins']:>3}/{data['total']:<3}  "
        f"{clear:>7}  {median_hp:>9}  {worst_hp:>8}"
    )


def verdict(
    stages: list[tuple[str, dict]], run_skilled: dict | None, run_tank: dict | None
) -> list[str]:
    """What is out of balance. The run halves are None when no run was measured
    -- `--stage N` asks about one arena and does not pay for two campaigns."""
    notes = []

    for name, data in stages:
        if data["wins"] < data["total"]:
            notes.append(
                f"{name} is clearable on only {data['wins']}/{data['total']} seeds "
                "from full health -- that stage is a wall, not a difficulty step"
            )

    if run_skilled is None or run_tank is None:
        return notes

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


def run_identity(bestiary, hero: str) -> tuple[str, str]:
    """How to drive a whole run for this class: (class to start as, branch).

    **Every run promotes**, and getting this wrong measures a hero the game
    cannot produce -- in either direction:

      * An advanced class cannot *start* a run. A run measured "as the Dark
        Knight" is a run started as the Knight that takes that branch at the
        fork. Started as a Dark Knight on stage 1 it is a different run
        entirely, and the ladder's sharp(12) row disagreed with the skilled row
        above it that uses the identical policy.
      * A base class cannot *finish* one. The fork is compulsory, so a Knight
        that plays all forty stages is nobody -- and it reports 1/6, because
        acts V-VIII are tuned for the class it refused to become.

    A base class takes the branch on key 1, which is what `data/entities.json`
    lists first. The other branch is covered per stage rather than per run; a
    forty-stage run is a hundred times the work of one stage.
    """
    advanced = bestiary[hero].promotes_from
    if advanced:
        return advanced, hero
    offers = bestiary.promotions_for(hero)
    return hero, offers[0].id if offers else ""


def stages_for(campaign, bestiary, hero: str, only: int | None) -> list[int]:
    """Which stage indices are worth sweeping for this class.

    A base class is never the hero after the fork and an advanced class is never
    the hero before it, so sweeping the whole campaign for either measures a
    matchup the game cannot produce -- and prints a wall of zeroes that looks
    exactly like a balance failure. `--stage N` overrides it, because the point
    of naming a stage is to look at that stage.
    """
    if only is not None:
        return [only - 1]

    fork = jobs.PROMOTION_STAGE - 1
    if bestiary[hero].promotes_from:
        return list(range(fork, len(campaign)))
    return list(range(min(fork, len(campaign))))


def measure_class(
    campaign,
    bestiary,
    hero: str,
    seeds: range,
    full: bool,
    only: int | None = None,
    allocate=None,
) -> list[str]:
    """One class, top to bottom. Returns whatever is out of balance about it."""
    name = bestiary[hero].name
    print(f"\n{'=' * 60}\n{name}  ({hero})\n{'=' * 60}")

    indices = stages_for(campaign, bestiary, hero, only)

    stage_rows = []
    if full:
        print("\nper stage, skilled, entered at full health")
        print(HEADER)
        print(RULE)
        for index in indices:
            level = campaign[index]
            data = measure_stage(level, bestiary, autoplay, seeds, hero)
            stage_rows.append((f"stage {index + 1} ({level.name})", data))
            print(row(f"{index + 1}. {level.name}", data))

    if only is not None:
        # A single stage is a tuning question about that arena. Running two
        # forty-stage campaigns to answer it is a minute of waiting for numbers
        # nobody asked for.
        return [f"[{hero}] {note}" for note in verdict(stage_rows, None, None)]

    base, branch = run_identity(bestiary, hero)

    print("\nwhole run, health carrying between stages")
    print(HEADER)
    print(RULE)
    run_skilled = measure_run(campaign, bestiary, autoplay, seeds, base, branch, allocate)
    run_tank = measure_run(campaign, bestiary, reckless, seeds, base, branch, allocate)
    print(row("skilled", run_skilled))
    print(row("face-tank", run_tank))

    if run_skilled["wins"] < run_skilled["total"]:
        stage, stage_name = furthest_stage(
            campaign, bestiary, autoplay, seeds, base, branch, allocate
        )
        print(f"\n  worst run ended on stage {stage} ({stage_name})")

    return [f"[{hero}] {note}" for note in verdict(stage_rows, run_skilled, run_tank)]


def allocation(name: str):
    """Turn the `--allocate` argument into a policy, or into a loud refusal.

    Empty is `None` rather than a do-nothing policy, so the sweep runs the exact
    code path every recorded number was measured through rather than one that
    behaves the same.
    """
    if not name:
        return None
    if name == "spread":
        return spread
    return into(name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument(
        "--class",
        dest="hero",
        default=DEFAULT_HERO,
        help="which class to measure, or 'all' for every one of them. Defaults "
        "to the reference class, which is the only one whose numbers the "
        "campaign was tuned against",
    )
    parser.add_argument(
        "--stages",
        action="store_true",
        help="print the per-stage rows for every class, not just the reference. "
        "Slow, and only worth it when a class is failing and you need to know "
        "which stage did it",
    )
    parser.add_argument(
        "--stage",
        type=int,
        default=None,
        help="measure this one stage (1-based) and nothing else. The tuning "
        "loop: a single arena answers in seconds where a full sweep takes "
        "minutes, and at forty stages that is the difference between trying "
        "six numbers and trying one",
    )
    parser.add_argument(
        "--allocate",
        default="",
        metavar="POLICY",
        help="how the hero spends what levelling pays: 'spread' for one point "
        "into each attribute in turn, or an attribute name for all of them into "
        "that one. Default is to spend nothing, which is what every recorded "
        "number was measured with -- and which stops being the right default "
        "the day data/progression.json sets xp_base above zero",
    )
    args = parser.parse_args()

    try:
        allocate = allocation(args.allocate)
    except KeyError as bad:
        print(bad.args[0], file=sys.stderr)
        return 1

    campaign = campaign_io.load(config.LEVELS_DIR / "campaign.json")
    bestiary = load_bestiary(config.ENTITIES_DATA, config.WEAPONS_DATA)
    seeds = range(args.seeds)

    if args.stage is not None and not 1 <= args.stage <= len(campaign):
        print(f"--stage must be between 1 and {len(campaign)}", file=sys.stderr)
        return 1

    # Advanced classes are measurable here and nowhere else in the tools. They
    # are deliberately absent from `hero_classes` -- that property feeds the
    # character select and the base half of the balance grid, and widening it
    # would put fifteen columns on a screen laid out for five. So they are
    # named explicitly, and 'all' still means the five you can start a run as.
    roster = [c.id for c in bestiary.hero_classes]
    advanced = [c.id for c in bestiary.advanced_classes]
    if args.hero == "all":
        heroes = roster
    elif args.hero == "advanced":
        heroes = advanced
    elif args.hero in roster or args.hero in advanced:
        heroes = [args.hero]
    else:
        print(
            f"unknown class '{args.hero}'; pick one of: {', '.join(roster + advanced)}, "
            "or 'all' for the starting five, or 'advanced' for the ten they promote into",
            file=sys.stderr,
        )
        return 1

    print(
        f"{campaign.name}  --  {len(campaign)} stages, {args.seeds} seeds, "
        f"{len(heroes)} class{'es' if len(heroes) > 1 else ''}, "
        f"spending {args.allocate or 'nothing'}"
    )

    notes = []
    for hero in heroes:
        # The per-stage sweep is the expensive half. It always runs for the
        # reference class, because that is the campaign's own measurement; for
        # the others it is opt-in, since what usually matters about them is
        # whether they can finish at all.
        full = args.stages or hero == DEFAULT_HERO or len(heroes) == 1
        notes += measure_class(
            campaign, bestiary, hero, seeds, full, args.stage, allocate
        )

    if len(heroes) == 1 and args.stage is None:
        # Driven exactly as `measure_class` drives its own run, base class and
        # branch, or the ladder is not comparable with the table above it. Asked
        # for an advanced class it used to start the run *as* that class on
        # stage 1 -- a hero the game cannot produce, and a whole different run --
        # which showed up as the ladder's sharp(12) row disagreeing with the
        # skilled row that uses the identical policy.
        base, branch = run_identity(bestiary, heroes[0])
        print("\nreaction ladder on the run -- informational; see the docstring")
        print(HEADER)
        print(RULE)
        for name, ticks in LATENCIES:
            print(
                row(
                    f"{name} ({ticks})",
                    measure_run(
                        campaign, bestiary, Autoplay(ticks), seeds, base, branch, allocate
                    ),
                )
            )

    print()
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
        "stages pass, the lever is heal_between_stages -- and it belongs to the class,\n"
        "so it is the right lever for one class failing and the wrong one for all\n"
        "five. Enemy damage and class hp last: raising damage makes one mistake\n"
        "lethal, which is a harsher game rather than a tighter one."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
