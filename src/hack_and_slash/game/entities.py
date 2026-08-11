"""What a body is, and what it is currently doing.

Two kinds of thing live here, and keeping them apart matters:

* **`Weapon` and `EntityType`** are immutable content, loaded from JSON. Tuning
  the game means editing `data/*.json`, never this file.
* **`Entity`** is live state -- where a body is, what it has left, which frame of
  a swing it is on. One per thing in the arena, mutated in place by the sim.

Every duration is in simulation ticks and every speed is pixels per tick, so a
seeded run replays identically whatever the frame rate did.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..core.vec2 import ZERO, Vec2


class Faction(str, Enum):
    HERO = "hero"
    ENEMY = "enemy"

    @property
    def hostile_to(self) -> "Faction":
        return Faction.ENEMY if self is Faction.HERO else Faction.HERO


class ActionState(str, Enum):
    """What a body is committed to this tick.

    Exactly one at a time, on one field, so an attack and a dodge cannot
    silently overlap -- that overlap is how "I dodged and still got hit while
    my own swing was out" bugs happen.
    """

    IDLE = "idle"
    WINDUP = "windup"  # telegraph; nothing can be hit yet
    ACTIVE = "active"  # the hitbox exists
    RECOVERY = "recovery"  # committed, cannot act, can be punished
    DODGING = "dodging"


# --- content -----------------------------------------------------------------
@dataclass(frozen=True)
class Weapon:
    id: str
    name: str
    damage: int
    variance: int
    arc: float  # full cone width in radians
    reach: float  # pixels from body centre to the far edge of the swing
    windup: int
    active: int
    recovery: int
    knockback: float
    hitstop: int
    projectile: bool = False
    projectile_speed: float = 0.0
    projectile_radius: float = 0.0
    projectile_lifetime: int = 0

    @property
    def total_ticks(self) -> int:
        return self.windup + self.active + self.recovery

    @classmethod
    def from_dict(cls, weapon_id: str, payload: dict) -> "Weapon":
        return cls(
            id=weapon_id,
            name=payload.get("name", weapon_id),
            damage=int(payload["damage"]),
            variance=int(payload.get("variance", 0)),
            arc=math.radians(float(payload.get("arc_degrees", 90))),
            reach=float(payload.get("reach", 0)),
            windup=int(payload["windup"]),
            active=int(payload["active"]),
            recovery=int(payload["recovery"]),
            knockback=float(payload.get("knockback", 0.0)),
            hitstop=int(payload.get("hitstop", 0)),
            projectile=bool(payload.get("projectile", False)),
            projectile_speed=float(payload.get("projectile_speed", 0.0)),
            projectile_radius=float(payload.get("projectile_radius", 2.0)),
            projectile_lifetime=int(payload.get("projectile_lifetime", 120)),
        )


@dataclass(frozen=True)
class EntityType:
    id: str
    name: str
    faction: Faction
    sprite: str
    hp: int
    speed: float
    radius: float
    weapon: Weapon
    brain: str
    aggro: float = 0.0

    # Hero only. Zero on everything else, which is how "enemies cannot dodge"
    # is expressed -- as data, not as a branch in the sim.
    dodge_speed: float = 0.0
    dodge_ticks: int = 0
    iframe_ticks: int = 0
    dodge_cooldown: int = 0

    # Charger only.
    charge_speed: float = 0.0
    charge_range: float = 0.0

    # Archer only.
    preferred_range: float = 0.0
    retreat_range: float = 0.0

    @property
    def can_dodge(self) -> bool:
        return self.dodge_ticks > 0

    @classmethod
    def from_dict(cls, type_id: str, payload: dict, weapons: dict[str, Weapon]) -> "EntityType":
        weapon_id = payload["weapon"]
        if weapon_id not in weapons:
            raise KeyError(f"{type_id} wants weapon '{weapon_id}', which is not in weapons.json")
        return cls(
            id=type_id,
            name=payload.get("name", type_id),
            faction=Faction(payload["faction"]),
            sprite=payload.get("sprite", type_id),
            hp=int(payload["hp"]),
            speed=float(payload["speed"]),
            radius=float(payload["radius"]),
            weapon=weapons[weapon_id],
            brain=payload.get("brain", "chaser"),
            aggro=float(payload.get("aggro", 0.0)),
            dodge_speed=float(payload.get("dodge_speed", 0.0)),
            dodge_ticks=int(payload.get("dodge_ticks", 0)),
            iframe_ticks=int(payload.get("iframe_ticks", 0)),
            dodge_cooldown=int(payload.get("dodge_cooldown", 0)),
            charge_speed=float(payload.get("charge_speed", 0.0)),
            charge_range=float(payload.get("charge_range", 0.0)),
            preferred_range=float(payload.get("preferred_range", 0.0)),
            retreat_range=float(payload.get("retreat_range", 0.0)),
        )


@dataclass(frozen=True)
class Bestiary:
    """Everything loadable, read once at startup."""

    weapons: dict[str, Weapon]
    types: dict[str, EntityType]

    def __getitem__(self, type_id: str) -> EntityType:
        try:
            return self.types[type_id]
        except KeyError:
            known = ", ".join(sorted(self.types))
            raise KeyError(f"unknown entity type '{type_id}'; known types: {known}") from None


def load_bestiary(entities_path: Path, weapons_path: Path) -> Bestiary:
    """Read `data/entities.json` and `data/weapons.json`.

    Keys starting with an underscore are comments. JSON has none of its own, and
    content files are exactly where an explanation is most worth having.
    """
    weapon_data = _read_json(weapons_path)
    weapons = {
        key: Weapon.from_dict(key, value)
        for key, value in weapon_data.items()
        if not key.startswith("_")
    }

    entity_data = _read_json(entities_path)
    types = {
        key: EntityType.from_dict(key, value, weapons)
        for key, value in entity_data.items()
        if not key.startswith("_")
    }
    return Bestiary(weapons=weapons, types=types)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- live state --------------------------------------------------------------
@dataclass
class Entity:
    """One body in the arena. Mutated in place by the sim, once per tick."""

    id: int
    type: EntityType
    pos: Vec2
    hp: int

    facing: float = 0.0  # radians; where a swing would go
    velocity: Vec2 = ZERO  # knockback and dash momentum, not walking

    state: ActionState = ActionState.IDLE
    state_ticks: int = 0  # ticks spent in the current state

    #: Bodies already hit by the swing in progress. Cleared when a new swing
    #: starts. Without it a four-tick active window deals damage four times.
    hit_ids: set[int] = field(default_factory=set)

    #: Direction locked in at the start of a dash. A dodge or a charge commits
    #: to where it was aimed and cannot be steered afterwards -- that commitment
    #: is what makes a charge sidesteppable and a dodge a decision.
    dash_dir: Vec2 = ZERO

    iframes: int = 0  # ticks of invulnerability left
    dodge_cooldown: int = 0
    stagger: int = 0  # ticks unable to act, from being hit
    attack_cooldown: int = 0  # AI pacing between swings

    # Cosmetic only. The renderer reads these; the sim never branches on them,
    # which is what lets the feel pass be turned off without changing a fight.
    flash: int = 0
    last_hit_by: int | None = None

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def is_hero(self) -> bool:
        return self.type.faction is Faction.HERO

    @property
    def radius(self) -> float:
        return self.type.radius

    @property
    def is_busy(self) -> bool:
        """Committed to something and unable to start anything else."""
        return self.state is not ActionState.IDLE or self.stagger > 0

    @property
    def is_invulnerable(self) -> bool:
        return self.iframes > 0

    @property
    def health_fraction(self) -> float:
        return max(0.0, min(1.0, self.hp / self.type.hp))


def spawn(next_id: int, entity_type: EntityType, pos: Vec2) -> Entity:
    return Entity(id=next_id, type=entity_type, pos=pos, hp=entity_type.hp)
