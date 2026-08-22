"""Champions -- an ordinary monster that rolled something extra.

The roadmap calls this the largest variety multiplier per hour of work available
to the project, and the reason is that **it adds run-to-run difference without
touching the stage literals**. Every arena is a hand-written list of creatures
at coordinates, fixed on every seed forever; an affix is the one thing that can
make the twelfth grunt of the run different from the eleventh without a single
edit to `levels/`.

**The affix slot was already built.** `EntityType.attributes` is content and
`Entity.bonus` is what one body earned, and `World._populate` already writes a
block into the second of those for the difficulty tier. An affix is a second
addend on that same line -- so this file needed no new arithmetic anywhere in
`combat`, `sim` or `ai`, exactly as the difficulty dials needed none for three
of their six.

**Stat affixes only, and it is structural rather than a rule anybody has to
remember.** An affix carries an `Attributes` block, and `Attributes.from_dict`
refuses a key it does not know -- so an affix that summoned adds, or paced
differently, or pathed around a pillar is not something this loader rejects, it
is something the schema cannot say. That matters more here than it reads:
`docs/limits.md` records that nothing in this game paths around walls, so a
behavioural affix interacts with the one limit the level design is built on.

**Health is per-mille of the creature, never a flat number.** `difficulty.py`
makes the same argument about its own `hp` dial: one flat figure means something
different to a rat and to a boss, and +20 health is a rounding error on one and
a different creature on the other. `Attributes.max_hp` is flat, so an affix
declares `hp` and `block_for` resolves it against the body it landed on.

**The layer draws no dice when it is off.** `roll_for` returns None before it
touches the generator at all, so a world built without champions
draws exactly the numbers it drew before this file existed -- and `world.rng` is
not the generator it would have drawn from anyway. That is the same guarantee
the loot, attribute and hazard layers each rest on, made a fifth time.

Pure Python -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path

from .. import config
from .attributes import NEUTRAL, PER_MILLE, Attributes
from .entities import EntityType

#: Xor'd into the world's seed to make this layer's own generator. The fifth,
#: after loot, attributes, hazards and the map -- and for the fifth time the
#: reason is that a die drawn from `world.rng` shifts every damage roll after
#: it, silently, across all 280 recorded cells.
ELITE_STREAM = 0x3117E


@dataclass(frozen=True)
class Affix:
    """One thing a champion can be.

    `weight` is relative and the roll is weighted rather than uniform, so the
    table can carry a rare and dangerous one beside three ordinary ones without
    needing a second dial to say how rare.
    """

    id: str
    name: str
    weight: int = 1

    #: Per-mille of the creature's own health. 1000 changes nothing, which is
    #: the identity of the operation, like every other multiplier in the
    #: project.
    hp: int = PER_MILLE

    #: Everything else, in the attributes' own units. `max_hp` is refused at
    #: load -- see the module docstring.
    attributes: Attributes = NEUTRAL

    @property
    def is_identity(self) -> bool:
        """Whether this affix would change nothing about the body it landed on.

        Derived over `dataclasses.fields` rather than written as two
        comparisons, in `difficulty.Enemies.is_identity`'s image: a third dial
        is covered the day it is declared rather than the day somebody
        remembers to widen this.
        """
        if self.attributes is not NEUTRAL and self.attributes != NEUTRAL:
            return False
        return all(
            getattr(self, f.name) == f.default
            for f in fields(self)
            if f.name not in ("id", "name", "weight", "attributes")
        )

    def block_for(self, entity_type: EntityType) -> Attributes:
        """This affix as a block for one creature.

        Returns the **shared** `NEUTRAL` when it comes to nothing, by identity
        and not merely by value: `World._populate` gates on `is not NEUTRAL`,
        and an equal-but-distinct block would take that branch on every body in
        the game.
        """
        if self.is_identity:
            return NEUTRAL

        health = (entity_type.full_hp * (self.hp - PER_MILLE)) // PER_MILLE
        if not health:
            return self.attributes

        return Attributes(max_hp=health) + self.attributes


@dataclass(frozen=True)
class Table:
    """The whole layer: whether it runs, how often, and on what."""

    enabled: bool = False
    chance: int = 0
    from_floor: int = 1

    #: Whether a boss may roll one. False, and the argument is the same one
    #: `docs/design.md` makes about the acts: a boss is already the act's
    #: statement, and a champion prefix on it is a second one competing with the
    #: first. It is a dial rather than a hard rule because the arena mode, when
    #: it lands, has no acts to make a statement about.
    bosses: bool = False

    affixes: tuple[Affix, ...] = ()

    @property
    def is_off(self) -> bool:
        """Whether this layer can produce anything at all.

        Three ways to be off and they are deliberately not one: `enabled` is the
        rollback, `chance` is the tuning dial at rest, and an empty list is a
        table somebody is part-way through writing.
        """
        return not self.enabled or self.chance <= 0 or not self.affixes

    def roll_for(self, entity_type: EntityType, floor: int, rng) -> "Affix | None":
        """What this creature rolled, or None.

        **Every early return here happens before `rng` is touched**, which is
        the whole of the claim that a world without champions draws the numbers
        it always drew. The live path draws exactly two: one to decide whether,
        one to decide which.

        Returns the `Affix` rather than its block, because the caller needs both
        halves and they must not be derived twice: the sim wants the attributes
        and the renderer wants the name, and a second lookup keyed on anything
        but this one object is a second answer that can disagree.
        """
        if self.is_off or floor < self.from_floor:
            return None
        if entity_type.is_boss and not self.bosses:
            return None

        if rng.randrange(PER_MILLE) >= self.chance:
            return None

        return rng.choices(self.affixes, weights=[a.weight for a in self.affixes])[0]

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        """Read the layer, refusing loudly on anything malformed.

        Loud because this is content, not preference -- `difficulty.Table.load`
        gives the full argument. The guards below are the ones that separate a
        hard champion from a broken one, and two of them are the same guards
        that file already makes about a tier.
        """
        source = path or config.ELITES_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))

        chance = int(payload.get("chance", 0))
        if not 0 <= chance <= PER_MILLE:
            raise ValueError(
                f"{source}: chance is {chance}, and it is per-mille -- "
                f"0 to {PER_MILLE}"
            )

        enabled = bool(payload.get("enabled", False))
        affixes = tuple(
            _affix(source, entry) for entry in payload.get("affixes", ())
        )

        seen: set[str] = set()
        for affix in affixes:
            if affix.id in seen:
                raise ValueError(f"{source}: two affixes share the id {affix.id!r}")
            seen.add(affix.id)

        if enabled and not affixes:
            raise ValueError(
                f"{source}: the layer is enabled and declares no affixes, so "
                f"every roll it wins hands back nothing"
            )
        if enabled and chance == 0:
            # A switched-on layer that can never fire is a typo, not a setting:
            # `enabled: false` already says "off" and says it where the rollback
            # is documented.
            raise ValueError(
                f"{source}: the layer is enabled with chance 0, which is off "
                f"wearing the word on. Set enabled to false instead"
            )

        from_floor = int(payload.get("from_floor", 1))
        if from_floor < 1:
            raise ValueError(f"{source}: from_floor is {from_floor}, and floors start at 1")

        return cls(
            enabled=enabled,
            chance=chance,
            from_floor=from_floor,
            bosses=bool(payload.get("bosses", False)),
            affixes=affixes,
        )


def _affix(source: Path, payload: dict) -> Affix:
    """One entry, with the guards that keep a champion fightable."""
    unknown = set(payload) - {"id", "name", "weight", "hp", "attributes"}
    if unknown:
        raise ValueError(
            f"{source}: {payload.get('id', '?')!r} has keys this file does not "
            f"define: {', '.join(sorted(unknown))}"
        )

    affix_id = str(payload["id"])
    weight = int(payload.get("weight", 1))
    if weight < 1:
        raise ValueError(
            f"{source}: {affix_id!r} has weight {weight}, and an affix that "
            f"cannot be rolled is a line nobody will ever see"
        )

    hp = int(payload.get("hp", PER_MILLE))
    if hp < 1:
        # The same refusal `difficulty.py` makes about `incoming`: a body with
        # no health is not a gentler setting, it is a creature that dies to the
        # first thing that touches it.
        raise ValueError(f"{source}: {affix_id!r} has hp {hp}, and it is per-mille")

    block = Attributes.from_dict(payload.get("attributes"))

    if block.max_hp:
        raise ValueError(
            f"{source}: {affix_id!r} sets max_hp, which is flat. Health on an "
            f"affix is `hp`, per-mille of the creature -- a flat +20 is a "
            f"rounding error on a brute and a different animal on a rat"
        )
    if block.move_speed <= -PER_MILLE:
        raise ValueError(
            f"{source}: {affix_id!r} has move_speed {block.move_speed}, which "
            f"roots the creature. Nothing paths around walls in this game, so a "
            f"monster that cannot walk is a stage that never ends"
        )
    if not 0 <= block.evasion < PER_MILLE:
        raise ValueError(
            f"{source}: {affix_id!r} has evasion {block.evasion}, and a "
            f"creature nothing can hit is a stage that runs to the tick limit"
        )

    affix = Affix(
        id=affix_id,
        name=str(payload["name"]),
        weight=weight,
        hp=hp,
        attributes=block,
    )
    if affix.is_identity:
        # Refused rather than tolerated, because a champion is a *mark* as well
        # as a block: the renderer draws one on anything that rolled, so an
        # affix that changes nothing would be a name over a monster that is not
        # different in any way the player can find. That is worse than no affix.
        raise ValueError(
            f"{source}: {affix_id!r} changes nothing about the creature it "
            f"lands on, and a champion the player cannot tell from an ordinary "
            f"monster is a mark that means nothing"
        )
    return affix


#: The layer at rest, constructed rather than loaded -- so a `World` built by a
#: test that has never heard of champions is the fight that test was written
#: against, with no file read at all. This is `difficulty.NORMAL`'s trick, and
#: it is the default at every seam in the project.
OFF = Table()


_TABLE: Table | None = None


def table() -> Table:
    """The shipped layer, read from disk once. Lazy, as every other one is."""
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


def reset_cache() -> None:
    """Forget the loaded table. For tests that supply their own."""
    global _TABLE
    _TABLE = None
