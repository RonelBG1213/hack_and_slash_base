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

#: The class played when nobody has chosen one -- tests, tools, and every
#: `World` or `Run` built without naming a class. The Knight rather than an
#: average of the five, because a reference has to be a real thing the player
#: can pick: the campaign is measured against it, and a number tuned against a
#: hero nobody plays is a number tuned against nothing.
DEFAULT_HERO = "knight"


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
    #: Speed of the dash this attack carries the body forward at, for the whole
    #: of its active window. A property of the *attack*, not the creature: a boss
    #: that charges on one attack must not drift forward on the other two.
    charge_speed: float = 0.0

    projectile: bool = False
    projectile_speed: float = 0.0
    projectile_radius: float = 0.0
    projectile_lifetime: int = 0

    #: Shots per volley, and the total angle they fan across. One shot ignores
    #: the spread; three across 30 degrees is a wall you step around rather than
    #: a bullet you sidestep.
    projectile_count: int = 1
    spread: float = 0.0

    @property
    def total_ticks(self) -> int:
        return self.windup + self.active + self.recovery

    @property
    def is_charge(self) -> bool:
        return self.charge_speed > 0.0

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
            charge_speed=float(payload.get("charge_speed", 0.0)),
            projectile=bool(payload.get("projectile", False)),
            projectile_speed=float(payload.get("projectile_speed", 0.0)),
            projectile_radius=float(payload.get("projectile_radius", 2.0)),
            projectile_lifetime=int(payload.get("projectile_lifetime", 120)),
            projectile_count=int(payload.get("projectile_count", 1)),
            spread=math.radians(float(payload.get("spread_degrees", 0.0))),
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

    #: Every attack this thing has, in the order the data listed them. Most
    #: things have exactly one; a boss is a boss largely because it has several.
    weapons: tuple[Weapon, ...]

    brain: str
    aggro: float = 0.0

    #: Whole-number upscale for the sprite. The atlas is a fixed 16px grid, so
    #: this is how something draws bigger than a tile without a second grid --
    #: and a whole number keeps the pixels hard, which `--smoke` enforces.
    sprite_scale: int = 1

    # Hero only. Zero on everything else, which is how "enemies cannot dodge"
    # is expressed -- as data, not as a branch in the sim.
    dodge_speed: float = 0.0
    dodge_ticks: int = 0
    iframe_ticks: int = 0
    dodge_cooldown: int = 0

    #: Health recovered between stages. The whole progression system, and the
    #: dial that decides whether carrying damage forward is tense or punishing.
    heal_between_stages: int = 0

    #: How close a charging brain gets before committing. A decision about when
    #: to attack, so it belongs to the creature -- the dash itself belongs to the
    #: weapon.
    charge_range: float = 0.0

    # Archer only.
    preferred_range: float = 0.0
    retreat_range: float = 0.0

    @property
    def can_dodge(self) -> bool:
        return self.dodge_ticks > 0

    @property
    def weapon(self) -> Weapon:
        """The default attack.

        Kept so everything with one attack -- which is everything except the
        boss -- reads the way it always did.
        """
        return self.weapons[0]

    @classmethod
    def from_dict(cls, type_id: str, payload: dict, weapons: dict[str, Weapon]) -> "EntityType":
        # "weapon" for the ordinary single-attack case, "weapons" for anything
        # that switches between several. Accepting both keeps the data honest
        # about which things are simple.
        wanted = payload.get("weapons") or [payload["weapon"]]
        for weapon_id in wanted:
            if weapon_id not in weapons:
                raise KeyError(
                    f"{type_id} wants weapon '{weapon_id}', which is not in weapons.json"
                )

        return cls(
            id=type_id,
            name=payload.get("name", type_id),
            faction=Faction(payload["faction"]),
            sprite=payload.get("sprite", type_id),
            hp=int(payload["hp"]),
            speed=float(payload["speed"]),
            radius=float(payload["radius"]),
            weapons=tuple(weapons[w] for w in wanted),
            sprite_scale=int(payload.get("sprite_scale", 1)),
            brain=payload.get("brain", "chaser"),
            aggro=float(payload.get("aggro", 0.0)),
            dodge_speed=float(payload.get("dodge_speed", 0.0)),
            dodge_ticks=int(payload.get("dodge_ticks", 0)),
            iframe_ticks=int(payload.get("iframe_ticks", 0)),
            dodge_cooldown=int(payload.get("dodge_cooldown", 0)),
            heal_between_stages=int(payload.get("heal_between_stages", 0)),
            charge_range=float(payload.get("charge_range", 0.0)),
            preferred_range=float(payload.get("preferred_range", 0.0)),
            retreat_range=float(payload.get("retreat_range", 0.0)),
        )


@dataclass(frozen=True)
class Bestiary:
    """Everything loadable, read once at startup."""

    weapons: dict[str, Weapon]
    types: dict[str, EntityType]

    @property
    def hero_classes(self) -> tuple[EntityType, ...]:
        """The roster the player chooses from, in the order the data listed it.

        Derived from the faction rather than from a separate list, so adding a
        class is one entry in `entities.json` and nothing else -- there is no
        second place to register it and therefore no way for the two to drift.

        Order matters: it is the order the character select shows, so it comes
        from the file rather than from sorting, and rearranging the roster is
        done by rearranging the JSON.
        """
        return tuple(t for t in self.types.values() if t.faction is Faction.HERO)

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

    #: Which of the type's attacks is in progress. Chosen when a swing starts
    #: and left alone until the next one, so every phase of an attack -- its
    #: windup, its hitbox, its recovery -- reads the same weapon. Change this
    #: mid-swing and a body would wind up with one attack and land another.
    weapon_index: int = 0

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
    def weapon(self) -> Weapon:
        """The attack this body is currently using.

        Everything that asks about timings, reach or damage goes through here
        rather than through `type.weapon`, so a thing with several attacks
        behaves correctly without any of that code knowing bosses exist.
        """
        return self.type.weapons[self.weapon_index]

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
