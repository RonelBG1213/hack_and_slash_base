"""What a body wants to do this tick.

The seam between "someone pressed a key" and "the world changed". The sim takes
`Intent` objects and nothing else -- it never sees a keyboard, a mouse, or an
enemy's reasoning. Two things fall out of that:

* a test scripts a fight by handing over a list of Intents, no input layer needed;
* the player and the AI go through exactly one code path, so an enemy can never
  do something the hero physically could not.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.vec2 import ZERO, Vec2


@dataclass(frozen=True)
class Intent:
    """A request, not a command -- the sim decides what is actually possible."""

    #: Direction to walk. Clamped to length 1 by the sim, so holding two keys
    #: cannot outrun holding one.
    move: Vec2 = ZERO

    #: Where to point. ZERO means "keep facing where I was", which is what a
    #: motionless mouse should do -- not snap to the right.
    aim: Vec2 = ZERO

    attack: bool = False
    dodge: bool = False

    #: Which of the attacker's attacks to use. Only a boss has more than one, so
    #: everything else leaves this at zero and never thinks about it.
    weapon: int = 0

    @property
    def wants_to_move(self) -> bool:
        return not self.move.is_zero()


NOTHING = Intent()


def walk(direction: Vec2) -> Intent:
    return Intent(move=direction, aim=direction)


def swing_at(direction: Vec2) -> Intent:
    return Intent(aim=direction, attack=True)


def dodge_toward(direction: Vec2) -> Intent:
    return Intent(move=direction, aim=direction, dodge=True)
