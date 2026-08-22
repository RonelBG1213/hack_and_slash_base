"""Which noise each event asks for, and how many times per frame it may ask.

The counterpart to `render/effects.py`, and written to the same rule: **nothing
here may ever change the outcome of a fight.** Cues are fed by events, which the
sim emits and never reads back; this module owns its own state and touches no
entity. `tests/test_audio.py` runs the same seeded fight with cues on and off and
demands the two worlds come out identical -- so the audio pass can be turned all
the way up without anybody having to re-verify the balance underneath it.

Free of pygame, so that guarantee can be checked headlessly. Making the noise is
`bank.py`, which is not.

**The one mechanic here is that feeding and draining happen at different rates,
and they have to.** `World.drain_events` is called once per *simulated tick*,
from inside the fixed-timestep loop in `scenes/play.py` -- and one rendered frame
pays out up to fifteen of them after a stall (`config.MAX_FRAME_TIME`). A mixer
fed straight off that stacks fifteen identical swings into a single frame, which
is not a swing, it is a buzz. A single swing catching six enemies does the same
thing six times over in one tick.

So `feed` accumulates and `drain` collapses: at most one play per cue per frame,
called from where `effects.tick()` already is. Everything a player can actually
distinguish survives that; everything they cannot was going to be mush.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..game.events import Event, EventKind

#: The loudest the options screen can set. Volume is an integer 0-10 rather than
#: a float, and that is not cosmetic: `settings.load` coerces bools and ints and
#: nothing else, so a float field would be dropped on every load and silently
#: fall back to its default forever, with no error anywhere.
MAX_VOLUME = 10

#: Loud enough to hear over nothing, quiet enough not to be the first thing
#: somebody turns down.
DEFAULT_VOLUME = 7


def cue_for(event: Event) -> Optional[str]:
    """The cue an event asks for, or None if it asks for nothing.

    A function rather than a dict because four of the twelve kinds branch on the
    payload -- and each branch is a distinction the player can hear.
    """
    match event.kind:
        case EventKind.HIT:
            # The single most important line in this file. A blow you land and a
            # blow you take are opposite events, and "was that me?" has to be
            # answerable without looking at the health bar -- which is the same
            # argument `effects._add_number` makes when it colours one red and
            # the other pale.
            return "hurt" if event.is_hero else "hit"
        case EventKind.DEATH:
            return "hero_death" if event.is_hero else "death"
        case EventKind.PICKUP:
            # Empty on a coin, set on anything off the loot table. The same test
            # the PICKUP case in `effects.feed` uses to pick a colour, and for
            # the same reason: one relic sprite serves all five tiers, so the
            # sound is carrying information the picture is not.
            return "relic" if event.rarity else "coin"
        case EventKind.CRIT:
            # Layered over its HIT rather than replacing it, exactly as the event
            # itself accompanies the HIT it belongs to.
            return "crit"
        case EventKind.SWING:
            return "swing"
        case EventKind.SHOOT:
            return "shoot"
        case EventKind.DODGE:
            return "dodge"
        case EventKind.BUFF:
            return "buff"
        case EventKind.BLOCKED:
            return "blocked"
        case EventKind.TRAP:
            return "trap"
        case EventKind.PROP:
            return "prop"

    # PROJECTILE_SPENT, and only it. Three places emit it -- an arrow hit a body,
    # an arrow hit a wall, an arrow aged out over empty floor -- and nothing in
    # the payload tells them apart. A cue here would click every time a shot
    # expired into nothing, which is most of them for a bowman firing across a
    # room. Left out deliberately, in the same position `effects.feed` leaves
    # SWING, DODGE and PROP in.
    return None


@dataclass
class Cues:
    """What wants playing, fed one tick of events at a time."""

    #: 0 is off, and it is a real setting rather than a sentinel -- the row on
    #: the options screen reads "off" there. Held here as well as on `Settings`
    #: so a `Cues` built without an opinion is the one the game ships with.
    volume: int = DEFAULT_VOLUME

    #: Names asked for since the last drain. Deliberately a list rather than a
    #: set: the order cues were first asked for in is the order the sim resolved
    #: them in, and playing a death before the hit that caused it is audible.
    pending: list[str] = field(default_factory=list)

    @property
    def level(self) -> float:
        """Volume as the 0.0-1.0 the mixer wants."""
        return max(0, min(MAX_VOLUME, self.volume)) / MAX_VOLUME

    def feed(self, events: list[Event]) -> None:
        """Take one tick's events. Called from inside the tick loop."""
        # Gated here as well as in `drain`, so a silent game does no work at all
        # rather than building a list nobody will read. Unlike `Effects.shake`
        # there is no second half of this class that would then disagree about
        # what happened -- a cue not played is a cue with no other state.
        if self.volume <= 0:
            return

        for event in events:
            cue = cue_for(event)
            if cue is not None:
                self.pending.append(cue)

    def drain(self) -> list[str]:
        """Everything to play this frame, each name once. Called once per frame.

        Deduplicated rather than counted. Two grunts dying on the same tick is
        one `death` -- playing it twice is 3dB louder and not two deaths, and
        past about four the mixer runs out of channels and starts dropping the
        ones it did not choose.
        """
        if self.volume <= 0:
            self.pending.clear()
            return []

        seen: set[str] = set()
        out: list[str] = []
        for name in self.pending:
            if name not in seen:
                seen.add(name)
                out.append(name)

        self.pending.clear()
        return out

    def clear(self) -> None:
        """Forget what was queued, without playing any of it.

        Used where `Effects.clear` is -- a stage boundary. The cues queued by the
        last tick of a stage that has already been left belong to an arena the
        player is no longer standing in.
        """
        self.pending.clear()
