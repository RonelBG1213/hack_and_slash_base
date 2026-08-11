"""Things that happened this tick, for anyone who wants to draw or hear them.

The sim appends; the presentation layer drains. The rule that makes this worth
having: **nothing in the sim may ever read an event back**. Events are an
output, not state. Break that and the feel pass -- screenshake, damage numbers,
hitstop -- stops being cosmetic and starts changing who wins a fight, which is
precisely what `test_effects.py` refuses to allow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.vec2 import Vec2


class EventKind(str, Enum):
    SWING = "swing"  # a swing's active window opened
    HIT = "hit"  # damage landed
    BLOCKED = "blocked"  # a hit was eaten by i-frames
    DEATH = "death"
    DODGE = "dodge"
    SHOOT = "shoot"
    PROJECTILE_SPENT = "projectile_spent"


@dataclass(frozen=True)
class Event:
    kind: EventKind
    pos: Vec2
    entity_id: int
    amount: int = 0
    facing: float = 0.0
    is_hero: bool = False
