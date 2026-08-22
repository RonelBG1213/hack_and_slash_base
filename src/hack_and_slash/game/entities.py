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
from .attributes import NEUTRAL, Attributes

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

    #: Ticks before this attack may be used again, counted from the swing
    #: starting. Zero means "as often as the state machine allows", which is
    #: every enemy attack and every class's light attack -- so a body whose
    #: attacks all read zero behaves exactly as it did before skills existed.
    cooldown: int = 0

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

    #: What using this attack grants its own user, and for how many ticks. The
    #: two are one fact in two fields on purpose: `buff_ticks` alone says *this
    #: is a buff*, which is what `is_buff` reads and what every branch guarding
    #: this feature keys off, and `buff` says *what it does*. A block with no
    #: duration is inert rather than permanent, which is the safe way round --
    #: the failure mode of forgetting the number is a skill that does nothing,
    #: not a hero that is permanently 30% faster.
    #:
    #: Neutral and zero on every attack in the game except the five in the Q
    #: slot, so `is_buff` is False everywhere the balance grid has ever
    #: measured and every branch added for this costs one falsy test. Same
    #: argument as `sim._touch_props` opening on an empty prop list.
    buff: Attributes = NEUTRAL
    buff_ticks: int = 0

    #: Per-mille cut in what a *skill cooldown* is stamped at, while this buff
    #: is live. Beside the block rather than in it, because `Attributes` is the
    #: layer equipment and the shrine also write to, and `progression.SPENDABLE`
    #: is derived from its fields -- a ninth field there would be a stat every
    #: class can buy, a ninth row on a character sheet whose eighth already
    #: draws through the hint, and a ninth key on the level panel. This is a
    #: skill effect, so it lives on the skill.
    #:
    #: Per-mille like `crit_chance` and `move_speed`, zero being the identity.
    #: Does not touch the dodge: `dodge_cooldown` is the roll, which is a
    #: defensive tool designed against the i-frame window rather than a skill.
    buff_haste: int = 0

    #: What this attack leaves on the body it *hits*, and for how long. The buff
    #: pair above pointed the other way round: that one is granted to the user
    #: when the window opens, this one is applied to the target when a blow is
    #: confirmed.
    #:
    #: A burn is a negative `regen`, a slow is a negative `move_speed`, and a
    #: vulnerability is a negative `defense` -- so status effects needed no new
    #: arithmetic anywhere, in the same way the difficulty dials needed none for
    #: three of their six. What they needed was somewhere to put the block and a
    #: timer to take it off again.
    #:
    #: **Three attacks in `data/weapons.json` carry these**, and all three are a
    #: promoted class's heavy or ultimate -- which is the only place in the game
    #: a status is invisible to the recorded grid, because the reference bot
    #: presses the light attack and nothing else. No enemy attack carries one:
    #: that is the change that moves all 280 cells, and
    #: `test_no_enemy_attack_inflicts_anything` is the guard. Removing the three
    #: blocks makes the whole layer inert, which is the rollback.
    inflict: Attributes = NEUTRAL
    inflict_ticks: int = 0

    @property
    def total_ticks(self) -> int:
        return self.windup + self.active + self.recovery

    @property
    def is_charge(self) -> bool:
        return self.charge_speed > 0.0

    @property
    def is_buff(self) -> bool:
        """Whether this attack buffs its user instead of hitting anything.

        Read off the duration rather than off the block, because a buff whose
        every field happens to be zero is still a buff -- it is a tuning
        mistake, and a mistake that reads as "the slot is an attack again" is
        much harder to see than one that reads as "the skill does nothing".
        """
        return self.buff_ticks > 0

    @property
    def is_inflicting(self) -> bool:
        """Whether this attack leaves anything behind on what it hits.

        Read off the duration rather than off the block, for the reason
        `is_buff` gives one property above: a block of zeroes with a duration is
        a tuning mistake, and it is far easier to spot as "the burn does
        nothing" than as "the attack stopped inflicting".
        """
        return self.inflict_ticks > 0

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
            cooldown=int(payload.get("cooldown", 0)),
            charge_speed=float(payload.get("charge_speed", 0.0)),
            projectile=bool(payload.get("projectile", False)),
            projectile_speed=float(payload.get("projectile_speed", 0.0)),
            projectile_radius=float(payload.get("projectile_radius", 2.0)),
            projectile_lifetime=int(payload.get("projectile_lifetime", 120)),
            projectile_count=int(payload.get("projectile_count", 1)),
            spread=math.radians(float(payload.get("spread_degrees", 0.0))),
            # Through `Attributes.from_dict`, which *raises* on an unknown key.
            # Worth reaching for deliberately: everything above this line uses
            # `payload.get`, so a misspelled weapon field is silently ignored,
            # and a `crit_rate` sitting quietly at zero in a content file is
            # exactly the kind of thing that gets tuned around for an afternoon.
            buff=Attributes.from_dict(payload.get("buff")),
            buff_ticks=int(payload.get("buff_ticks", 0)),
            buff_haste=int(payload.get("buff_haste", 0)),
            # Same door as `buff`, and the same reason for using it.
            inflict=Attributes.from_dict(payload.get("inflict")),
            inflict_ticks=int(payload.get("inflict_ticks", 0)),
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

    #: How dangerous this thing is, on a scale of its own. Read only by the loot
    #: layer, which pays out on it -- so a boss is worth more than the grunts
    #: standing around it on the same floor.
    #:
    #: Deliberately *not* derived from hp. A health number gets tuned for balance
    #: reasons every time a stage plays badly, and loot payouts silently moving
    #: every time that happens is how a reward curve rots without anyone
    #: touching it. One is a fight; the other is a wage.
    level: int = 1

    #: Whole-number upscale for the sprite. The atlas is a fixed 16px grid, so
    #: this is how something draws bigger than a tile without a second grid --
    #: and a whole number keeps the pixels hard, which `--smoke` enforces.
    sprite_scale: int = 1

    #: Enemy only: the id of the creature this one is a cosmetic variant of.
    #: Empty on everything else, which is how "this is its own creature" is
    #: expressed -- as data, not as a second list.
    #:
    #: The same trick `promotes_from` plays, for the same reason. It says *this
    #: is a variant*, which is what lets a test assert that it carries no numbers
    #: of its own, and it says *which line it copies*, which is what that test
    #: compares against. A `cosmetic: bool` beside a `copies: str` could disagree
    #: with each other; one field cannot disagree with itself.
    #:
    #: A variant exists so a stage can field a goblin instead of a grunt without
    #: fielding anything the balance grid has not already measured. Every stat is
    #: the base's, to the byte -- so substituting one into an arena moves nothing,
    #: and `test_a_variant_is_stat_identical_to_what_it_varies` is what makes that
    #: a fact rather than an intention.
    variant_of: str = ""

    #: Hero only, and only on an advanced class: the id of the class this one is
    #: promoted from. Empty on everything else, which is how "this is a starting
    #: class" is expressed -- as data, not as a second list.
    #:
    #: One field doing two jobs on purpose. It says *this is advanced*, which is
    #: what keeps it off the character select and out of the balance grid, and it
    #: says *which base it belongs to*, which is what the promotion menu is built
    #: from. A separate `advanced: bool` beside it could disagree with it; this
    #: cannot disagree with itself.
    promotes_from: str = ""

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

    #: Flanker only: how far off the straight line to the hero it approaches, in
    #: degrees, measured at the edge of its aggro. The angle closes to nothing as
    #: it arrives, so this is the *widest* the arc ever gets rather than a fixed
    #: offset -- a constant one orbits forever and never lands a hit.
    #:
    #: Zero on everything else, which is how "this walks straight at you" is
    #: expressed -- as data, the way `dodge_ticks` says enemies cannot roll.
    flank_degrees: float = 0.0

    #: The content half of the attribute layer -- crit, defense, evasion, regen
    #: and the flat bonuses. See `attributes.py`; every field defaults to the
    #: identity of its own operation, so a type that declares nothing fights
    #: exactly the way it did before the layer existed.
    #:
    #: **One field rather than one per attribute, and that is the point.**
    #: `test_a_variant_is_stat_identical_to_what_it_varies` iterates
    #: `dataclasses.fields`, so a variant is held to the whole block by the
    #: test that already exists, and the next attribute is covered the day it
    #: is added rather than the day somebody remembers to widen a list. That
    #: has since been collected on: the eighth (`move_speed`) needed no test
    #: edit at all.
    attributes: Attributes = NEUTRAL

    @property
    def full_hp(self) -> int:
        """What a fresh body of this type has, attribute block included.

        The content-level counterpart to `Entity.max_hp`, for the screens that
        describe a class before there is a body to ask -- the character select
        and the promotion panel. A live body always knows better, because it may
        have earned some.
        """
        return self.hp + self.attributes.max_hp

    @property
    def is_boss(self) -> bool:
        """Whether this is one of the things an act ends on.

        Driven by `sprite_scale` rather than by a name or a flag, which is the
        rule `render/hud.py` already decided the boss bar by: *a thing drawn
        twice the size of everything else is a thing whose health the player
        needs to be able to read*. Named here rather than left as a comparison
        in two files, because the second reader is `game/elites.py` -- and an
        affix layer that disagreed with the health bar about what a boss is
        would put a champion's mark on something with no bar to hang it from.
        """
        return self.sprite_scale > 1

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
            level=int(payload.get("level", 1)),
            variant_of=payload.get("variant_of", ""),
            promotes_from=payload.get("promotes_from", ""),
            dodge_speed=float(payload.get("dodge_speed", 0.0)),
            dodge_ticks=int(payload.get("dodge_ticks", 0)),
            iframe_ticks=int(payload.get("iframe_ticks", 0)),
            dodge_cooldown=int(payload.get("dodge_cooldown", 0)),
            heal_between_stages=int(payload.get("heal_between_stages", 0)),
            charge_range=float(payload.get("charge_range", 0.0)),
            preferred_range=float(payload.get("preferred_range", 0.0)),
            retreat_range=float(payload.get("retreat_range", 0.0)),
            flank_degrees=float(payload.get("flank_degrees", 0.0)),
            attributes=Attributes.from_dict(payload.get("attributes")),
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

        **Advanced classes are excluded**, and that exclusion is load-bearing
        rather than cosmetic. Eight places read this property -- the character
        select, both tools, and five test modules including the class x stage
        balance grid. An advanced class arriving in it would put fifteen columns
        on a screen laid out for five and take the grid from 80 cells to 280,
        every new one untuned. `advanced_classes` is the other half of the pair.
        """
        return tuple(
            t
            for t in self.types.values()
            if t.faction is Faction.HERO and not t.promotes_from
        )

    @property
    def advanced_classes(self) -> tuple[EntityType, ...]:
        """Every class reachable only by promotion, in file order.

        The complement of `hero_classes` within the hero faction. Exists so the
        structural tests -- four slots, the windup ceiling, ascending cooldowns
        -- can still be applied to advanced classes after the roster property
        stopped returning them. Without it those rules would quietly go from
        covering every hero class to covering only five.
        """
        return tuple(
            t for t in self.types.values() if t.faction is Faction.HERO and t.promotes_from
        )

    @property
    def variants(self) -> tuple[EntityType, ...]:
        """Every creature that is a cosmetic re-skin of another, in file order.

        The set the identity test iterates. Derived from the field rather than
        listed here for the same reason `hero_classes` is: a second list is a
        thing that can drift, and this one drifting means a creature carrying
        numbers nobody measured while claiming to carry none.
        """
        return tuple(t for t in self.types.values() if t.variant_of)

    def variants_of(self, base_id: str) -> tuple[EntityType, ...]:
        """Every face the `base_id` line wears, in file order.

        Several variants may share a base -- the point of one is a face, not a
        stat line, so two families are free to wear the same mechanics in
        different acts.
        """
        return tuple(t for t in self.variants if t.variant_of == base_id)

    def promotions_for(self, base_id: str) -> tuple[EntityType, ...]:
        """What `base_id` may promote into, in file order.

        Empty for a class with no promotions declared, which is the whole of the
        feature's off switch: delete the advanced entries from the JSON and the
        job panel never opens, with no code removed.
        """
        return tuple(t for t in self.advanced_classes if t.promotes_from == base_id)

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

    #: Ticks left before each attack may be used again, keyed by weapon index.
    #: A dict rather than a list sized to the type: an attack with no cooldown
    #: never writes an entry, so every enemy in the game carries an empty one
    #: and nothing has to know which bodies have skills and which do not.
    skill_cooldowns: dict[int, int] = field(default_factory=dict)

    stagger: int = 0  # ticks unable to act, from being hit
    attack_cooldown: int = 0  # AI pacing between swings

    #: What this body earned during this run, on top of what its type ships
    #: with. Written by the progression layer and by nothing else; neutral on
    #: every enemy in the game and on a hero that has not levelled.
    #:
    #: Lives on the `Entity` rather than on the `EntityType` because the type is
    #: frozen content shared by every run of that class -- and it survives
    #: `jobs.promote`, which swaps `type` on a live body and would otherwise
    #: throw away everything the run had earned at the exact midpoint of it.
    bonus: Attributes = NEUTRAL

    #: Hundredths of a hit point of regeneration banked but not yet paid out.
    #: Integer, so a long run cannot accumulate rounding drift and stop
    #: replaying from its seed. See `sim._regen`.
    regen_bank: int = 0

    #: The third attribute layer, and the only one with a lifetime shorter than
    #: a stage: what the Q slot granted this body, and how many ticks of it are
    #: left. Written by `actions.apply_buff`, counted down in
    #: `actions.tick_timers`, and reset to the shared `NEUTRAL` singleton on
    #: expiry -- by identity, because `attrs` tests against it.
    #:
    #: Deliberately *not* saved. `save.snapshot` writes `Run` state only and a
    #: save is taken between stages, so a buff dies with the `World` that was
    #: fighting when it was cast, exactly as `skill_cooldowns` already does.
    buff: Attributes = NEUTRAL
    buff_ticks: int = 0

    #: The live half of `Weapon.buff_haste`, on the same timer as `buff` and
    #: cleared beside it. Read only by `actions.begin_attack`, at the moment a
    #: cooldown is stamped.
    buff_haste: int = 0

    #: The fourth attribute layer: what somebody *else* put on this body, and
    #: how many ticks of it are left. A burn, a slow, a vulnerability.
    #:
    #: **A separate pair from `buff` above, deliberately.** The two look alike
    #: and could not share a slot: `apply_buff` replaces rather than stacks --
    #: which is only sound because every buff is shorter than the cooldown
    #: gating it, a property of the *content* -- so sharing would mean an
    #: enemy's burn wiping the Priest's Benediction and a cast of it putting out
    #: a fire. `render/hud.py` also reads `buff_ticks` to light the Q pip, and
    #: a hero who had been set alight would light it.
    #:
    #: Deliberately *not* saved, for the reason `buff` is not: a save is taken
    #: between stages, so a status dies with the `World` that applied it.
    status: Attributes = NEUTRAL
    status_ticks: int = 0

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

    def cooldown_on(self, weapon_index: int) -> int:
        """Ticks left before that attack may be used again.

        Zero for an attack that has never been used, and for every attack that
        has no cooldown at all -- which is why callers can ask about any index
        without first checking whether the body has skills.
        """
        return self.skill_cooldowns.get(weapon_index, 0)

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
    def attrs(self) -> Attributes:
        """Content, plus earned, plus the Q slot, plus whatever hit this body.

        Summed on every access rather than cached: the earned half changes when
        a level is spent, the content half changes when `jobs.promote` swaps the
        type, the third half expires on a timer, and a cache invalidated in
        three places is a cache that will be wrong in a fourth. The fourth half
        -- a status somebody else applied -- expires on a timer of its own.

        **Each optional half is tested by identity against the shared `NEUTRAL`
        singleton**, not summed unconditionally, and that is not a
        micro-optimisation. `sim._walk_speed` reads this once per body per tick,
        so an unconditional third addend would put an eight-field construction
        on every enemy on every tick of a 300,000-tick run to add zero to
        zero. The same trick `save._attributes` and `World._populate` already
        play, for the same reason -- which is why `apply_buff` must reset to the
        singleton rather than to a fresh `Attributes()` that merely equals it.
        """
        base = self.type.attributes + self.bonus
        if self.buff is not NEUTRAL:
            base = base + self.buff
        return base if self.status is NEUTRAL else base + self.status

    @property
    def max_hp(self) -> int:
        """This body's full health, attributes included.

        **Read this, never `entity.type.hp`.** The type's number is the content
        baseline and stopped being the whole answer when the attribute layer
        landed; a caller that reaches past this sees a maximum that a levelled
        hero has already exceeded. The two that matter most are
        `health_fraction` below -- which the reference bot's disengage rule keys
        off -- and `jobs.promote`, which carries health across the fork as a
        fraction and would turn a wrong ceiling into a silent heal or wound.
        """
        return self.type.hp + self.attrs.max_hp

    @property
    def health_fraction(self) -> float:
        return max(0.0, min(1.0, self.hp / self.max_hp))


def spawn(next_id: int, entity_type: EntityType, pos: Vec2) -> Entity:
    """A body at full health, its type's attribute block included.

    `bonus` is neutral here by construction -- nothing has been earned yet --
    so the type's own `max_hp` is the whole of the difference from `type.hp`.
    """
    return Entity(
        id=next_id,
        type=entity_type,
        pos=pos,
        hp=entity_type.hp + entity_type.attributes.max_hp,
    )
