"""Screenshake, floating damage numbers, and the freeze on a solid hit.

**Nothing here may ever change the outcome of a fight.** Effects are fed by
events, which the sim emits and never reads back; this module owns its own state
and touches no entity. `tests/test_effects.py` runs the same seeded fight with
effects on and off and demands the two worlds come out identical -- so the feel
pass can be turned all the way up without anybody having to re-verify the
balance underneath it.

Free of pygame, so that guarantee can be checked headlessly.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .. import config
from ..core.vec2 import ZERO, Vec2
from ..game.events import Event, EventKind

#: How long a damage number hangs in the air, in ticks.
NUMBER_LIFETIME = 42

#: Pixels a damage number drifts upward over its life.
NUMBER_RISE = 18.0

#: Shake sizes, in pixels of offset. Small numbers: an internal resolution of
#: 384x216 upscaled by 3 means one pixel of shake reads as three on screen, and
#: a game that lurches on every hit becomes unreadable in a crowd.
SHAKE_ON_HIT = 1.6
SHAKE_ON_HERO_HURT = 3.2
SHAKE_ON_DEATH = 2.4

#: Per-tick decay of the shake magnitude.
SHAKE_DECAY = 0.82


@dataclass
class FloatingNumber:
    text: str
    origin: Vec2
    ticks_left: int
    color: tuple[int, int, int]
    drift: float  # sideways offset, so two hits at once do not overlap exactly

    @property
    def progress(self) -> float:
        return 1.0 - (self.ticks_left / NUMBER_LIFETIME)

    def offset(self) -> Vec2:
        """Where to draw it, relative to where the hit landed."""
        return Vec2(self.drift * self.progress, -NUMBER_RISE * _ease_out(self.progress))

    @property
    def alpha(self) -> int:
        # Solid for most of its life, then fades. Fading from the start makes
        # the number hard to read at exactly the moment it matters.
        fade = max(0.0, (self.progress - 0.6) / 0.4)
        return int(255 * (1.0 - fade))


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


@dataclass
class Effects:
    """All the cosmetic state, fed one tick of events at a time."""

    #: Seeded separately from the sim's RNG. Drawing must never consume a number
    #: the simulation was going to use -- that would make the sim depend on
    #: whether anything was on screen.
    rng: random.Random = field(default_factory=lambda: random.Random(7))

    numbers: list[FloatingNumber] = field(default_factory=list)
    shake: float = 0.0
    hitstop: int = 0

    #: The two the options screen exposes. Both default to True, so an `Effects`
    #: built without an opinion -- every test and tool that predates the screen
    #: -- is the one that was always here.
    #:
    #: Safe to expose *because* of the guarantee at the top of this file rather
    #: than in spite of it: this module is fed events the sim emits and never
    #: reads back, so there is no path by which either flag could reach a fight.
    #: `test_effects.py` runs the same seeded fight with them both ways and
    #: demands identical output, which is what turns that from an argument into
    #: a fact.
    screenshake: bool = True
    damage_numbers: bool = True

    def feed(self, events: list[Event], hitstop: int = 0) -> None:
        """Take one tick's events. Called every frame, before drawing."""
        self.hitstop = hitstop

        for event in events:
            match event.kind:
                case EventKind.HIT:
                    self._add_number(event)
                    self.shake = max(
                        self.shake,
                        SHAKE_ON_HERO_HURT if event.is_hero else SHAKE_ON_HIT,
                    )
                case EventKind.DEATH:
                    self.shake = max(self.shake, SHAKE_ON_DEATH)
                case EventKind.PICKUP:
                    # The only place a rarity is ever seen. There is one relic
                    # sprite for all five tiers, so what tells a player they
                    # just picked up something good is this number's colour and
                    # the size of it -- and no shake, because a coin is not an
                    # impact.
                    self.numbers.append(
                        FloatingNumber(
                            text=f"+{event.amount}",
                            origin=event.pos,
                            ticks_left=NUMBER_LIFETIME,
                            color=config.RARITY_COLORS.get(event.rarity, config.GOLD),
                            drift=0.0,
                        )
                    )
                case EventKind.BLOCKED:
                    # A dodge that looks identical to a miss teaches the player
                    # nothing about what just worked.
                    self.numbers.append(
                        FloatingNumber(
                            text="dodge",
                            origin=event.pos,
                            ticks_left=NUMBER_LIFETIME // 2,
                            color=(150, 214, 236),
                            drift=0.0,
                        )
                    )

    def _add_number(self, event: Event) -> None:
        # The toggle covers *damage* numbers and nothing else, which is what the
        # row it sits behind says. The pickup and dodge numbers stay: a coin the
        # player walked over and a hit they rolled out of are both outcomes with
        # no other tell in the game, and switching those off would not be a
        # quieter screen so much as a game that stopped answering questions.
        if not self.damage_numbers:
            return

        self.numbers.append(
            FloatingNumber(
                text=str(event.amount),
                origin=event.pos,
                ticks_left=NUMBER_LIFETIME,
                # Red when it is the player being hurt, pale when it is not:
                # the colour answers "was that me?" without reading the number.
                color=(232, 106, 96) if event.is_hero else (240, 236, 220),
                drift=self.rng.uniform(-6.0, 6.0),
            )
        )

    def tick(self) -> None:
        """Age everything by one frame."""
        self.shake *= SHAKE_DECAY
        if self.shake < 0.05:
            self.shake = 0.0

        for number in self.numbers:
            number.ticks_left -= 1
        self.numbers = [n for n in self.numbers if n.ticks_left > 0]

    def shake_offset(self) -> Vec2:
        """Where to nudge the whole viewport this frame."""
        # Gated here rather than at `feed`, so `shake` goes on meaning "how hard
        # was that" whichever way the toggle is set. Suppressing the offset is
        # the whole of "off"; suppressing the magnitude as well would leave the
        # two halves of this class disagreeing about what happened.
        if not self.screenshake or self.shake <= 0.0:
            return ZERO
        angle = self.rng.uniform(0.0, math.tau)
        return Vec2(math.cos(angle) * self.shake, math.sin(angle) * self.shake)

    def clear(self) -> None:
        self.numbers.clear()
        self.shake = 0.0
        self.hitstop = 0
