"""What a run did, counted from the events it emitted.

The third reader of the drained event list, beside `render/effects.py` and
`audio/cues.py`. Four numbers the game has never had -- damage dealt, damage
taken, kills and elapsed time -- and every one of them is derived rather than
measured, because the sim counts none of them and must not start.

**Nothing here may ever change the outcome of a fight**, which is the same
sentence `effects.py` opens with and it is true here for a stronger reason: this
module holds no `Random` at all. `Effects` keeps its own seeded one so that
drawing cannot consume a number the sim was about to draw; a tally has nothing
to draw and so has nothing to guard. `test_tally.py` runs the same seeded fight
with a tally attached and without, and demands the two worlds come out
identical.

**Why this is in `render/` and not `game/`.** It is pure Python and imports no
pygame, so purity is not the reason -- `effects.py` is pygame-free too. The
reason is `game/events.py`'s rule, which is a rule about that package: *"nothing
in the sim may ever read an event back. Events are an output, not state."* A
module inside `game/` whose entire job is reading events back would demote that
to a convention and make the wrong thing importable from `sim.py`. Both existing
consumers sit outside `game/` for the same reason, and this joins them.

**It is not an instrument.** `game/autoplay.py` and `tools/balance.py` never call
`drain_events` at all -- they step the sim directly -- so a swept run has no
tally and the recorded balance grid cannot see one. That is the correct
arrangement and not an oversight: the moment the reference bot grows a readout,
the readout is measuring the instrument.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..game.events import Event, EventKind


def format_time(ticks: int) -> str:
    """Ticks as `m:ss`.

    Minutes are unbounded and there is deliberately no hour rollover: a
    fifty-stage run is tens of minutes, and `1:04:22` on a screen that has never
    shown an hour is a format nobody needs to learn to read `64:22`.
    """
    seconds = ticks // config.TICKS_PER_SEC
    return f"{seconds // 60}:{seconds % 60:02d}"


@dataclass
class Tally:
    """Four counters and a clock. Fed, never read back by anything that decides."""

    #: Damage the hero dealt: `HIT.amount` on every blow that was not landed on
    #: the hero. Exact -- `combat` refuses same-faction targets on both damage
    #: paths, so there is no enemy-on-enemy hit to over-count.
    dealt: int = 0

    #: Damage the hero took *from something that meant it*. `TRAP` is kept out
    #: and counted separately, which is what `events.py` split the kind for:
    #: "anything counting what the *enemies* did to the hero would otherwise
    #: count the room's spikes among them".
    taken: int = 0

    #: What the floor did. Summed with `taken` when the screen wants one number,
    #: apart from it when it wants the honest one.
    burned: int = 0

    #: Bodies that stopped moving and were not the hero.
    #:
    #: Every non-hero death is one the player caused *today*, and that is a fact
    #: about `data/hazards.json` rather than about this code: it ships
    #: `harms: "hero"`, so a trap never kills an enemy. Set `harms: all` and trap
    #: kills would join this count, which is arguably right and is at least worth
    #: knowing before the number is read as "kills by my own hand".
    kills: int = 0

    #: Ticks the world was actually live. Not a wall-clock timer and not a
    #: speedrun split: hitstop `continue`s before this is fed and every panel
    #: guard returns before it, so time spent frozen, shopping, at the fork or
    #: paused is not in here. What it measures is how long the fighting took,
    #: and it is reproducible for a fixed seed and a fixed input trace.
    ticks: int = 0

    #: True when this run was picked up off disk rather than started. The tally
    #: is not in the save file -- see `docs/limits.md` -- so on a resumed run
    #: these four numbers describe this session and not the whole run, and the
    #: screen has to say so rather than quietly under-report a campaign.
    partial: bool = False

    @property
    def seconds(self) -> float:
        return self.ticks / config.TICKS_PER_SEC

    @property
    def hurt(self) -> int:
        """Everything that cost health, whoever dealt it."""
        return self.taken + self.burned

    def feed(self, events: list[Event]) -> None:
        """Take one tick's events.

        **There is deliberately no `CRIT` branch.** Its comment in `events.py`
        says a crit "accompanies the HIT it belongs to rather than replacing it,
        so anything counting damage stays right whether or not it knows crits
        exist" -- `HIT.amount` is already multiplied. A `case EventKind.CRIT`
        here would double every critical hit in the run, and it would look
        exactly like a tuning problem.
        """
        for event in events:
            match event.kind:
                case EventKind.HIT:
                    if event.is_hero:
                        self.taken += event.amount
                    else:
                        self.dealt += event.amount
                case EventKind.TRAP:
                    if event.is_hero:
                        self.burned += event.amount
                case EventKind.DEATH:
                    if not event.is_hero:
                        self.kills += 1

    def advance(self, ticks: int = 1) -> None:
        """Age the clock by ticks that were actually stepped.

        Separate from `feed` rather than folded into it, for two reasons: the
        clock is then testable with no events at all, and a tick that emitted
        nothing still counts. Folding them would also make the clock double the
        day somebody feeds twice.
        """
        self.ticks += ticks
