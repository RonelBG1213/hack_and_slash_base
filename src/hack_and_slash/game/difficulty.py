"""How hard the fight is, chosen once per run.

**Why this is content and not a setting.** `scenes/options.py` is drawn on the
line that nothing on it may change how a fight resolves, and it names this
feature specifically: *a difficulty row would be a balance decision worn as a
preference, and the project's whole measurement culture rests on balance
decisions being made in `data/` where they can be swept.* That refusal still
stands and is still right. This module is the other half of the sentence -- the
decision lives in `data/difficulty.json`, beside every other tuning number, with
`tools/balance.py --difficulty` behind it.

**Seven dials, and one of them carries the tier.** `incoming` is a per-mille
multiplier on damage arriving at the hero, and it is the dial the recorded
brackets were swept on. The other six ride on `Enemies` and move the monsters
instead: `hp`, `damage`, `speed`, `aggro`, `cadence`, `evasion`. Counts are
still untouched -- a tier changes what the stage is made of, never how much of
it there is, because the stage literals are what the grid is pinned to.

**Expect `hp` to be the weakest of them.** This project has already measured
enemy health as close to inert: the enrage threshold is a fraction, so a boss
spends the same *proportion* of a shorter fight enraged, and both late bosses
were eventually tuned by damage after health changes moved the win rate by
nothing. It is a dial here because a tier wants a coherent story about its
monsters, not because it is expected to do the work -- `incoming` does that.

**`PER_MILLE` is the identity and that is load-bearing.** At 1000 `scaled`
takes an early return and the arithmetic is the arithmetic that was measured, so
"Normal is the game the recorded grid was measured against" is a millisecond
test rather than a sweep. The same trick `attributes.py` plays by defaulting
every field to the identity of its own operation, and it is here for the same
reason: it is what lets a dial be added to a tuned game and *proved* neutral.

The floor is deliberately **not** applied here. `combat.MIN_DAMAGE` is combat's
to own, and importing it would make this module depend on the one that depends
on it. Every caller applies the floor, and `test_combat.py` pins that they do.

Pure arithmetic on plain data -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .. import config
from .attributes import NEUTRAL, PER_MILLE, Attributes

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from .entities import EntityType


@dataclass(frozen=True)
class Enemies:
    """What the tier does to the things you fight.

    Six per-mille dials, and **every default is that dial's identity** -- which
    is not a convenience, it is the whole safety mechanism. `is_identity` below
    is derived by comparing each field against its own declared default, so a
    seventh dial is covered on the day it is declared rather than on the day
    somebody remembers to widen a list. The same argument `attributes.py` makes
    by defaulting every field to the identity of its own operation, and
    `Difficulty.incoming` makes by defaulting to `PER_MILLE`.

    **`evasion` is the odd one out and is written down as such.** Five of these
    are multipliers whose identity is 1000; evasion is an additive per-mille
    chance whose identity is 0. A field whose identity differs from its
    neighbours' is the field that gets forgotten, so it is stated here rather
    than left to be inferred from the number.

    Three of the six are applied through the attribute layer that already
    exists and need no code in `sim` or `combat` at all -- see `block_for`. The
    other three are read at their point of use: `damage` in `combat.dealt`,
    `aggro` in `ai.aggro_of`, `cadence` in `ai.cooldown_for`.
    """

    #: Enemy health. The strongest lever there is for an ordinary creature --
    #: revenant 46 -> 32 hp was the single biggest move in acts V-VIII -- and
    #: close to inert on a boss, whose enrage threshold is a *fraction*, so it
    #: spends the same proportion of a shorter fight enraged. That asymmetry is
    #: real and is the reason this dial bites hard on stages and softly on the
    #: eight fights that end an act.
    hp: int = PER_MILLE

    #: What an enemy's attacks are worth, before the hero's own `incoming`
    #: multiplier is applied to what lands. The two compound, deliberately and
    #: only where a tier sets both.
    damage: int = PER_MILLE

    #: Walking speed. Goes through `Attributes.move_speed`, which `sim` reads on
    #: the walking branch only -- enemies have no dash to stretch.
    speed: int = PER_MILLE

    #: How far away a creature notices you. Aimed squarely at disengaging, which
    #: the recorded reaction ladder says is the thing that actually separates a
    #: won run from a lost one -- so probably the strongest dial here, and the
    #: least measured.
    aggro: int = PER_MILLE

    #: The pause between one attack finishing and the next being allowed, so
    #: **below 1000 is more often**. Scales `ai.PAUSE_AFTER_ATTACK` and
    #: deliberately not `weapon.total_ticks`: the telegraph is what makes an
    #: attack readable and therefore dodgeable, and shortening it is a different
    #: and much harsher change than attacking more frequently.
    #:
    #: On the record as a weak lever. `ai.py` notes a flanker pause taken from
    #: 20 to 38 -- most of the way to a charger's -- moving "not one seed of
    #: eight on three separate stages".
    cadence: int = PER_MILLE

    #: Per-mille chance an enemy avoids a hit outright. **This is the whole of
    #: "the AI defends"**, and it needs no new mechanism: `combat.evades`
    #: already asks every target on every hit, already returns early at zero,
    #: and already draws from `world.attr_rng` rather than `world.rng` -- so it
    #: cannot disturb the damage stream the recorded grid rests on. An evaded
    #: hit lands no damage, no knockback, no stagger and no interrupt, and
    #: emits the BLOCKED event the renderer already draws.
    #:
    #: Additive, so **the identity is 0**, not 1000. See the class docstring.
    evasion: int = 0

    @property
    def is_identity(self) -> bool:
        """Whether this leaves every creature exactly as content declares it.

        Derived against each field's own default rather than against a written
        list of six comparisons, so the claim cannot rot when a dial is added.
        """
        return all(
            getattr(self, field.name) == field.default
            for field in dataclasses.fields(self)
        )

    def block_for(self, entity_type: "EntityType") -> Attributes:
        """The three dials that are expressible as an attribute block.

        `hp` is a multiplier here and a *flat* number in `Attributes`, so it is
        resolved against this type's own full health -- which is what makes one
        tier-wide percentage mean something different to a rat and to a boss,
        as it should. `speed` and `evasion` pass through, both already being
        per-mille in the layer that reads them.

        Integer throughout and floor division, like every other duration and
        dial in this project: a seeded run has to replay exactly, and integer
        arithmetic is the cheapest way to guarantee that.

        **Returns the shared `NEUTRAL` singleton by identity** whenever the
        three dials it covers are all neutral -- which is not the same question
        as `is_identity`, because a tier may move only cadence. Callers test
        `is not NEUTRAL` to decide whether to touch the body at all, so an
        equal-but-distinct block would put a bonus on every enemy in a fight
        that did not need one.
        """
        block = Attributes(
            max_hp=(entity_type.full_hp * (self.hp - PER_MILLE)) // PER_MILLE,
            evasion=self.evasion,
            move_speed=self.speed - PER_MILLE,
        )
        return NEUTRAL if block == NEUTRAL else block

    def scaled_damage(self, damage: int) -> int:
        """An enemy's hit, on this tier. The caller applies `combat.MIN_DAMAGE`.

        Same shape as `Difficulty.scaled` and same early return, for the same
        reason: at the identity it has to be provable that nothing happened.
        """
        if self.damage == PER_MILLE:
            return damage
        return (damage * self.damage) // PER_MILLE

    def scaled_aggro(self, radius: float) -> float:
        if self.aggro == PER_MILLE:
            return radius
        return radius * self.aggro / PER_MILLE

    def scaled_pause(self, pause: int) -> int:
        """Never below zero -- a negative pause would read as a bonus."""
        if self.cadence == PER_MILLE:
            return pause
        return max(0, (pause * self.cadence) // PER_MILLE)


#: Every creature exactly as `data/entities.json` declares it. The value every
#: default in the codebase reaches for, and the one Normal must carry.
NEUTRAL_ENEMIES = Enemies()


@dataclass(frozen=True)
class Difficulty:
    """One tier. Frozen, like every other piece of loaded content."""

    id: str = "normal"
    name: str = "Normal"

    #: One line for the select screen, in the voice of `select.ROLES`.
    blurb: str = ""

    #: Per-mille multiplier on damage the hero takes. 1000 changes nothing.
    incoming: int = PER_MILLE

    #: What the tier does to the monsters. Neutral by default, so a tier that
    #: declares nothing is the fight the recorded grid was measured against.
    enemies: Enemies = NEUTRAL_ENEMIES

    #: Whether the numbers above have been swept. False is not a defect -- it
    #: is the project's rule that a guess is flagged where it lives, exactly as
    #: `data/loot.json` separates its prices from its drop rates.
    measured: bool = True

    @property
    def is_identity(self) -> bool:
        """Whether this tier is arithmetically the game that was measured.

        **Both halves, and widening this was the one edit that mattered** when
        the monster dials landed. `Table.load` refuses a default tier that is
        not the identity, and that guard is the single thing protecting every
        recorded number in the project -- so a version of this property that
        still asked only about `incoming` would have let a default ship that
        quietly made every enemy tougher.
        """
        return self.incoming == PER_MILLE and self.enemies.is_identity

    def scaled(self, damage: int) -> int:
        """This hit, on this tier. Callers apply `combat.MIN_DAMAGE` underneath.

        The early return is the point of the method rather than an optimisation:
        at the identity it must be provable that nothing happened at all.
        """
        if self.incoming == PER_MILLE:
            return damage
        return (damage * self.incoming) // PER_MILLE


#: The tier every default in the codebase reaches for. Constructed rather than
#: loaded, so a `World` built by a test that has never heard of difficulty is
#: still the fight that test was written against, with no file read at all.
NORMAL = Difficulty()


def _enemies(source: Path, tier_id: str, payload: dict | None) -> Enemies:
    """Read one tier's monster block, refusing loudly on anything malformed.

    A missing block means neutral, which is how "this tier leaves the monsters
    alone" is expressed -- as an absent key, the way an enemy expresses that it
    cannot dodge by having no `dodge_ticks`.

    Unknown keys raise rather than being ignored, exactly as
    `Attributes.from_dict` does and for the same reason: this loader is
    otherwise forgiving, and a misspelled `agro` sitting silently at the
    identity is the kind of thing that gets tuned around for an afternoon
    before anybody reads the JSON.
    """
    if not payload:
        return NEUTRAL_ENEMIES

    known = {field.name for field in dataclasses.fields(Enemies)}
    unknown = sorted(set(payload) - known)
    if unknown:
        raise ValueError(
            f"{source}: tier {tier_id!r} sets unknown enemy dial(s) {unknown}; "
            f"the {len(known)} are {sorted(known)}"
        )

    block = Enemies(**{name: int(value) for name, value in payload.items()})

    for name in ("hp", "damage", "speed", "aggro"):
        if getattr(block, name) < 1:
            # Zero is not a gentler setting, it is a broken creature: no health
            # is dead on spawn, no speed is a statue, no aggro never wakes up.
            # Each of those leaves a stage that cannot be cleared, which every
            # instrument in this project reports as a balance failure. The same
            # argument the `incoming` guard makes one field up.
            raise ValueError(
                f"{source}: tier {tier_id!r} has enemy {name} "
                f"{getattr(block, name)}, and a creature with none of it "
                f"leaves a stage that cannot be finished"
            )

    if block.cadence < 0:
        raise ValueError(
            f"{source}: tier {tier_id!r} has enemy cadence {block.cadence}, "
            f"and a negative pause is not a faster attack"
        )

    if not 0 <= block.evasion < PER_MILLE:
        # At 1000 nothing can ever be hit, so the room is never cleared and the
        # stage runs to the tick limit -- the mirror image of the hero who
        # cannot be hurt, refused directly above for the same reason.
        raise ValueError(
            f"{source}: tier {tier_id!r} has enemy evasion {block.evasion}, "
            f"and a creature nothing can hit runs the stage out rather than "
            f"losing it"
        )

    return block


@dataclass(frozen=True)
class Table:
    """Every tier the game offers, in the order the select screen draws them."""

    tiers: tuple[Difficulty, ...]
    default_id: str

    def __getitem__(self, tier_id: str) -> Difficulty:
        for tier in self.tiers:
            if tier.id == tier_id:
                return tier
        raise KeyError(tier_id)

    def get(self, tier_id: str) -> Difficulty:
        """The named tier, or the default. For a save file naming a tier that
        no longer exists -- which is a reason to carry on at Normal, not a
        reason to refuse to load somebody's run."""
        try:
            return self[tier_id]
        except KeyError:
            return self.default

    @property
    def default(self) -> Difficulty:
        return self[self.default_id]

    @property
    def gentlest(self) -> Difficulty:
        """The easiest tier the game offers.

        **File order is the scale**, and that is a real contract rather than a
        convention: `scenes/select.py` draws the tiers in this order as a row
        and `_move_difficulty` clamps rather than wrapping, so the screen
        already treats the list as running from gentlest to harshest.

        Named here because the ceiling bracket needs it and used to find it by
        `min(tiers, key=lambda t: t.incoming)`. That worked while a tier was one
        number. With six more dials there is no single number to take the
        minimum of -- a tier could halve incoming damage and double enemy
        health -- so the question has to be answered by the order the designer
        put them in rather than derived from an arbitrary one of the dials.
        """
        return self.tiers[0]

    @property
    def index_of_default(self) -> int:
        return [tier.id for tier in self.tiers].index(self.default_id)

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        """Read the tiers, refusing loudly on anything malformed.

        Loud because this is content, not preference: `settings.py` is forgiving
        about a half-written file because the worst case there is somebody
        setting their window scale twice. A typo in a damage multiplier is a bug
        somebody has to see, and it is better said at startup than discovered by
        a hero dying twice as fast as the screen promised.
        """
        source = path or config.DIFFICULTY_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))

        entries = payload["tiers"]
        if not entries:
            raise ValueError(f"{source}: no tiers, and the game needs one to start")

        tiers: list[Difficulty] = []
        seen: set[str] = set()
        for entry in entries:
            tier_id = str(entry["id"])
            if tier_id in seen:
                raise ValueError(f"{source}: two tiers share the id {tier_id!r}")
            seen.add(tier_id)

            incoming = int(entry["incoming"])
            if incoming < 1:
                # Zero is not a gentler setting, it is a different game: a hero
                # nothing can hurt runs every stage to the tick limit, and every
                # instrument in this project reports that as a balance failure.
                # `combat.MIN_DAMAGE` makes the same argument one layer down.
                raise ValueError(
                    f"{source}: {tier_id!r} has incoming {incoming}, and a hero "
                    f"that cannot be hurt runs the stage out rather than winning it"
                )

            tiers.append(
                Difficulty(
                    id=tier_id,
                    name=str(entry["name"]),
                    blurb=str(entry.get("blurb", "")),
                    incoming=incoming,
                    enemies=_enemies(source, tier_id, entry.get("enemies")),
                    measured=bool(entry.get("_measured", False)),
                )
            )

        default_id = str(payload["default"])
        table = cls(tiers=tuple(tiers), default_id=default_id)

        if default_id not in seen:
            raise ValueError(
                f"{source}: default is {default_id!r}, which is not one of "
                f"{', '.join(sorted(seen))}"
            )

        if not table.default.is_identity:
            # The whole claim this feature rests on. A default that scales
            # damage means every recorded number in the project silently
            # describes a game nobody plays by default any more.
            raise ValueError(
                f"{source}: the default tier {default_id!r} has incoming "
                f"{table.default.incoming}, so the game it starts is not the "
                f"game the recorded balance grid was measured against"
            )

        return table


_TABLE: Table | None = None


def table() -> Table:
    """The shipped tiers, read from disk once.

    Lazy rather than at import, for the reason `loot.table()` gives: a module
    that reads a file at import time turns a missing data file into a failure of
    `test_architecture.py`, reported as an import error naming the wrong problem.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


def reset_cache() -> None:
    """Forget the loaded table. For tests that supply their own."""
    global _TABLE
    _TABLE = None
