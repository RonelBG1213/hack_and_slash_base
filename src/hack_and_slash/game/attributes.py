"""The eight numbers a body fights with, over and above its content stats.

Two layers, and they are separate because they have different lifetimes.
`EntityType.attributes` is content -- frozen, shared by every run of that class,
and the place an enemy's armour or a class's base crit belongs.
`Entity.bonus` is what one body earned in one run, and it dies with the run.
`Entity.attrs` is the sum, and it is the only thing the sim ever reads.

**Every field defaults to the identity of its own operation.** A block with
nothing set adds nothing, multiplies by nothing, blocks nothing and heals
nothing, so `combat.resolve_damage` reduces to `combat.roll_damage` and the game
is arithmetically the one that was measured. That is not a convenience for
testing -- it is what let this layer be added to a tuned game and *proved*
unmoved in milliseconds by `test_neutral_attributes_reproduce_todays_arithmetic`
rather than argued about over a twenty-minute sweep.

**Integers throughout, in per-mille and hundredths**, for the same reason every
duration in this project is ticks rather than seconds. A run is 240,000 ticks
and regen accrues on every one of them; float accumulation over that many
additions is a thing you have to reason about, and integer accumulation is not.
A seeded run has to replay exactly, and the cheapest way to guarantee that is to
have nothing in the arithmetic that could round differently.

Pure arithmetic on plain data -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

#: Denominator for the two chance fields and the crit multiplier. Per-mille
#: rather than per-cent because a 0.5% crit rate is a sensible thing to want and
#: rounding it to zero or to one whole percent are both wrong.
PER_MILLE = 1000

#: Denominator for `regen`. Hundredths of a hit point per tick, so the slowest
#: meaningful regen is one point every hundred ticks -- a little under two
#: seconds -- and the dial has somewhere to go below "one per second".
REGEN_SCALE = 100


@dataclass(frozen=True)
class Attributes:
    """What a body brings to a fight beyond its type's stats.

    Frozen, so a block can be shared and cached without anybody being able to
    write through it. Combine two with `+`.
    """

    #: Flat, on top of `EntityType.hp`. Read through `Entity.max_hp`, never by
    #: reaching for `entity.type.hp` -- see the note on that property.
    max_hp: int = 0

    #: Flat, added to the weapon's rolled damage before anything else happens.
    #: Deliberately not a multiplier: the classes are separated by an order of
    #: magnitude in damage per swing (a rogue's dagger is 5, a magician's bolt
    #: is 15), and a percentage would hand the same point to the magician three
    #: times over.
    damage: int = 0

    #: Flat, subtracted last -- after the crit, so armour is worth least
    #: against the biggest hit. `combat.MIN_DAMAGE` still applies underneath, so
    #: no amount of this makes a body immune.
    defense: int = 0

    #: Per-mille chance a hit is a critical one. Zero takes an early return and
    #: draws no random number at all, exactly as `roll_damage` does at zero
    #: variance -- which is what keeps a fight with the layer switched off
    #: drawing the same number of dice as a fight before the layer existed.
    crit_chance: int = 0

    #: Per-mille *bonus* on a critical hit, so 500 is one and a half times and
    #: 0 is a crit that changes nothing. A bonus rather than a multiplier so
    #: that the neutral value is zero like everything else here; a field whose
    #: identity was 1000 would be the one that got forgotten.
    crit_damage: int = 0

    #: Per-mille chance to avoid a hit entirely. Named `evasion` and not
    #: `dodge`: `dodge_ticks`, `dodge_cooldown` and `Intent.dodge` are the roll,
    #: which is a decision the player makes, and this is a die the game rolls
    #: for them. Two meanings for one word in one namespace is a bug waiting to
    #: be written. The HUD calls it Dodge, where there is no other meaning to
    #: collide with.
    evasion: int = 0

    #: Hundredths of a hit point per tick, banked in `Entity.regen_bank` and
    #: paid out whole. See `sim._regen`.
    regen: int = 0

    #: Per-mille *bonus* on the class's own walking speed, so 100 is +10% and
    #: zero is a body that walks exactly as its type says. A bonus rather than a
    #: multiplier, so the neutral value is zero like everything else here.
    #:
    #: Walking only. `sim._self_propulsion` reads it on the walking branch and
    #: deliberately not on the dodge dash: the roll is a fixed-distance
    #: defensive tool, and stretching it changes how much ground one i-frame
    #: window covers, which is a balance surface rather than a speed stat.
    #:
    #: Appended last on purpose. The field order *is* `progression.SPENDABLE`
    #: order, which is the order the level panel draws its rows -- so inserting
    #: one in the middle silently moves which digit spends what.
    move_speed: int = 0

    def __add__(self, other: "Attributes") -> "Attributes":
        """Fieldwise, and derived rather than listed.

        Written over `dataclasses.fields` so that an eighth attribute is summed
        correctly on the day it is declared, instead of on the day somebody
        notices it was left out of a hand-written constructor call.
        """
        if not isinstance(other, Attributes):
            return NotImplemented
        return Attributes(
            **{
                field.name: getattr(self, field.name) + getattr(other, field.name)
                for field in dataclasses.fields(self)
            }
        )

    def scaled(self, factor: int) -> "Attributes":
        """Every field multiplied by the same whole number.

        Written over `dataclasses.fields` for the reason `__add__` is: a ninth
        attribute scales correctly on the day it is declared, rather than on the
        day somebody notices it was left out of a hand-written constructor call.

        Integer throughout, like everything else here. A rarity multiplier is a
        whole number in `data/equipment.json` precisely so that this cannot
        round -- a scaled block has to replay exactly, and `2.5 * 25` is the sort
        of thing that does not.
        """
        return Attributes(
            **{
                field.name: getattr(self, field.name) * factor
                for field in dataclasses.fields(self)
            }
        )

    @classmethod
    def from_dict(cls, payload: dict | None) -> "Attributes":
        """Read a block out of the content files.

        A missing block and an empty one both mean neutral, which is how "this
        creature has no attributes" is expressed -- as an absent key, the way
        an enemy expresses that it cannot dodge by having no `dodge_ticks`.

        Unknown keys raise rather than being ignored. The loader is otherwise
        forgiving, but a misspelled `crit_rate` sitting silently at zero in a
        content file is exactly the kind of thing that gets tuned around for an
        afternoon before anybody reads the JSON.
        """
        if not payload:
            return NEUTRAL

        known = {field.name for field in dataclasses.fields(cls)}
        unknown = sorted(set(payload) - known)
        if unknown:
            raise KeyError(
                f"unknown attribute(s) {unknown}; the {len(known)} are {sorted(known)}"
            )
        return cls(**{name: int(value) for name, value in payload.items()})


#: Every attribute at the identity of its own operation. The default for both
#: layers, and the value the whole "the recorded grid is unmoved" claim rests
#: on -- see the module docstring.
NEUTRAL = Attributes()
