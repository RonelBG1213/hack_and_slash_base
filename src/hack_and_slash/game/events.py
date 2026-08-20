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
    #: A hit arrived and did nothing -- eaten by i-frames, or by an evasion
    #: roll. One kind for both, because to a player they are the same event and
    #: the renderer already draws it.
    BLOCKED = "blocked"
    #: Accompanies the HIT it belongs to rather than replacing it, so anything
    #: counting damage stays right whether or not it knows crits exist.
    CRIT = "crit"
    DEATH = "death"
    DODGE = "dodge"
    SHOOT = "shoot"
    PROJECTILE_SPENT = "projectile_spent"
    PICKUP = "pickup"  # gold or a valuable was collected
    #: A trap caught somebody. Separate from HIT because the presentation layer
    #: wants something different from each -- a blow comes from a body and points
    #: somewhere, a trap comes from the floor -- and because anything counting
    #: what the *enemies* did to the hero would otherwise count the room's
    #: spikes among them. `amount` is the damage, exactly as on a HIT.
    TRAP = "trap"
    #: A reward room's fixture was used, or one of its doors was walked
    #: through. One kind for both, because the presentation layer wants the
    #: same thing from each -- a flash where it happened -- and `amount` is
    #: zero on a door, which is the only difference either of them draws.
    PROP = "prop"


@dataclass(frozen=True)
class Event:
    kind: EventKind
    pos: Vec2
    entity_id: int
    amount: int = 0
    facing: float = 0.0
    is_hero: bool = False

    #: Which rarity a PICKUP was, as the plain string from `data/loot.json`.
    #: Empty on a coin, and on every other kind of event. A string rather than
    #: the `Rarity` enum so the presentation layer can look up a colour in
    #: `config.RARITY_COLORS` without importing anything from `game/`.
    rarity: str = ""
