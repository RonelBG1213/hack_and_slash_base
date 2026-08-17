"""What survives a run. Four counters, and deliberately only four.

A `Run` dies with the arena it ended in -- that is the design, and the shop and
the attribute layer are both built on it. This is the one thing that outlives
one, and it is kept as small as it can be while still being worth having.

**Nothing here is read by the sim, by `Run`, or by anything that decides a
fight.** It is a record of what happened, not an input to what happens next. The
day an unlock rule reads one of these numbers and hands a run a head start, that
is the day the recorded class-by-stage grid moves -- so the reading is a design
decision to be taken deliberately and swept, not a convenience to be added here.
Until then this is a scoreboard, and the two screens that draw it say so.

Why these four: each is a fact the run layer already knows at the moment a run
starts or ends, so recording one costs a line at a seam that already exists. A
counter that needed the sim to report something would be a change to the sim.

Pure Python -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .. import config


@dataclass
class Profile:
    """Lifetime totals across every run on this machine.

    All four default to zero, which is a truthful description of somebody who
    has never played -- so a missing file and a fresh player are the same state
    and nothing has to tell them apart.
    """

    runs_started: int = 0
    runs_won: int = 0

    #: The furthest stage ever reached, 1-based, as a player would say it.
    deepest_stage: int = 0

    #: The largest purse a single run ever ended with. `Run.gold_total`, taken
    #: when the run finishes -- so it counts what was collected, not what was
    #: left unspent, and a player who bought well is not punished for it.
    best_gold: int = 0


def load(path: Path | None = None) -> Profile:
    """Read the profile, falling back to an empty one on anything unreadable.

    Forgiving in exactly the way `settings.load` is forgiving, and for the same
    reason: a scoreboard that cannot be parsed is a scoreboard to start again,
    not a reason the game will not open. Content files refuse loudly; these do
    not, because these are not content.
    """
    source = path or config.PROFILE_FILE
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Profile()

    if not isinstance(payload, dict):
        return Profile()

    known = {f.name for f in fields(Profile)}
    accepted = {
        name: value
        for name, value in payload.items()
        if name in known and isinstance(value, int) and not isinstance(value, bool)
    }
    return Profile(**accepted)


def save(profile: Profile, path: Path | None = None) -> None:
    """Write the profile. Silent on failure, like the settings."""
    target = path or config.PROFILE_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
    except OSError:
        pass


def reset(path: Path | None = None) -> None:
    """Forget everything. The destructive half of the options screen."""
    target = path or config.PROFILE_FILE
    target.unlink(missing_ok=True)


# --- what a run puts into it -------------------------------------------------
def record_start(path: Path | None = None) -> Profile:
    """Count a run beginning, and hand back the profile it was counted into.

    Returned rather than only written, so the caller that is about to record the
    end of the same run is not re-reading a file it just wrote.
    """
    profile = load(path)
    profile.runs_started += 1
    save(profile, path)
    return profile


def record_stage(run, path: Path | None = None) -> Profile:
    """Note how far a run has got. Called on every stage transition.

    `max` rather than assignment: a later run that died early must not erase how
    far an earlier one got, which is the whole meaning of the word "deepest".
    """
    profile = load(path)
    profile.deepest_stage = max(profile.deepest_stage, run.stage_number)
    save(profile, path)
    return profile


def record_end(run, path: Path | None = None) -> Profile:
    """Note a run finishing, won or lost.

    Takes the `Run` rather than a handful of numbers so that the meaning of
    "how far" and "how rich" stays defined in one place -- `stage_number` and
    `gold_total` are already the two the HUD and the result screen show, and a
    scoreboard counting something subtly different from what the player was just
    looking at is worse than no scoreboard.
    """
    from .run import RunOutcome

    profile = load(path)
    if run.outcome is RunOutcome.WON:
        profile.runs_won += 1
    profile.deepest_stage = max(profile.deepest_stage, run.stage_number)
    profile.best_gold = max(profile.best_gold, run.gold_total)
    save(profile, path)
    return profile
