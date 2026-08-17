"""The seven attributes, and the guarantee that adding them moved nothing.

Two of the tests here are load-bearing in the same way
`test_loot_rolls_do_not_disturb_the_damage_stream` is, and for the same reason:
`combat.roll_damage` draws from `world.rng` and nothing else in the game does.
A crit or an evasion roll taken from that generator would shift every damage
roll after the first one, moving all 280 cells of the recorded class-by-stage
grids **without a single balance number being touched**, and nothing else in the
suite would say a word.

They were written before the code they guard.
"""

from __future__ import annotations

import dataclasses
import random

from hack_and_slash.game.attributes import NEUTRAL, Attributes
from hack_and_slash.game.combat import MIN_DAMAGE, resolve_damage, roll_damage
from hack_and_slash.game.events import EventKind
from hack_and_slash.game.intent import NOTHING
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import World

from .helpers import BESTIARY, level_with

SEED = 4242


# --- the arithmetic ----------------------------------------------------------
def test_neutral_attributes_are_the_identity_of_addition() -> None:
    assert NEUTRAL + NEUTRAL == NEUTRAL
    assert all(getattr(NEUTRAL, f.name) == 0 for f in dataclasses.fields(NEUTRAL))


def test_adding_two_attribute_blocks_covers_every_field() -> None:
    """Fieldwise, and derived from `dataclasses.fields` rather than listed.

    A field added later is summed the day it lands, the same trick
    `test_a_variant_is_stat_identical_to_what_it_varies` plays.
    """
    one = Attributes(*range(1, len(dataclasses.fields(Attributes)) + 1))
    doubled = one + one
    for index, field in enumerate(dataclasses.fields(Attributes), start=1):
        assert getattr(doubled, field.name) == index * 2, field.name


def test_neutral_attributes_reproduce_todays_arithmetic() -> None:
    """The structural proof that the grid is unmoved.

    This is the whole reason the attribute layer can ship on top of a tuned
    game without a sweep: with every attribute at its default, `resolve_damage`
    returns exactly what `roll_damage` handed it. It settles in milliseconds
    where `tools/balance.py` takes minutes, and it covers every weapon in the
    shipped content rather than a sample.
    """
    rng = random.Random(SEED)
    untouched = random.Random(SEED)

    for weapon in BESTIARY.weapons.values():
        base = roll_damage(weapon, random.Random(7))
        damage, crit = resolve_damage(base, NEUTRAL, NEUTRAL, rng)
        assert damage == base, f"{weapon.id} changed from {base} to {damage}"
        assert not crit

    assert rng.getstate() == untouched.getstate(), (
        "neutral attributes drew a random number. Crit must take an early "
        "return at crit_chance 0, the way roll_damage does at variance 0"
    )


def test_a_hit_never_rounds_to_zero_however_much_defense_is_in_the_way() -> None:
    """`MIN_DAMAGE` is kept, and it is kept for a reason worth restating.

    A hit that does nothing reads as a bug -- and worse, a stage where nothing
    can hurt anything runs to the tick limit and reports as a balance failure.
    """
    damage, _ = resolve_damage(3, NEUTRAL, Attributes(defense=999), random.Random(1))
    assert damage == MIN_DAMAGE


def test_a_crit_multiplies_and_says_that_it_did() -> None:
    always = Attributes(crit_chance=1000, crit_damage=500)
    damage, crit = resolve_damage(10, always, NEUTRAL, random.Random(1))
    assert crit and damage == 15


def test_defense_is_taken_after_the_crit_not_before_it() -> None:
    """Order of operations, pinned because changing it changes the game.

    Defense last means armour is worth least against the biggest hit, which is
    the reading that makes a crit feel like a crit.
    """
    attacker = Attributes(crit_chance=1000, crit_damage=1000)
    damage, _ = resolve_damage(10, attacker, Attributes(defense=5), random.Random(1))
    assert damage == 15, "20 doubled then reduced, not 5 reduced then doubled"


# --- the guarantee -----------------------------------------------------------
def test_attribute_rolls_do_not_disturb_the_damage_stream() -> None:
    """The load-bearing test in this file.

    Run the same seeded fight twice: once with every attribute neutral, and
    once with a crit that fires on every single hit and multiplies by exactly
    one. The two fights are arithmetically identical -- so if the damage lists
    differ, a crit roll is being drawn from `world.rng`, and every recorded
    number in the project has quietly stopped meaning what it says.

    Crit rather than evasion, because an evaded hit changes the fight rather
    than the arithmetic and the two runs would legitimately diverge. This is
    the only shape that isolates the stream from the outcome.
    """
    plain = _damage_over_a_fight(NEUTRAL)
    critting = _damage_over_a_fight(Attributes(crit_chance=1000, crit_damage=0))

    assert plain == critting, (
        "the damage rolls changed when the attributes did -- something in the "
        "attribute layer is drawing from world.rng"
    )
    assert plain, "the fight did no damage at all, so it proves nothing"


def test_the_combat_stream_is_untouched_by_a_fight_full_of_crits() -> None:
    """The same claim from the other side, and cheaper to read when it fails.

    `test_attribute_rolls_do_not_disturb_the_damage_stream` compares outcomes;
    this compares the generator itself, the way
    `test_effects_draw_from_their_own_random_not_the_world_s` does.
    """
    quiet = _rng_state_after_a_fight(NEUTRAL)
    loud = _rng_state_after_a_fight(Attributes(crit_chance=1000, crit_damage=0))

    assert quiet == loud, "world.rng advanced further in one fight than the other"


def test_the_attribute_stream_is_not_the_combat_stream() -> None:
    """Two `Random`s seeded identically are one `Random`. The offset is the
    entire mechanism, so it is asserted rather than assumed."""
    world = World(level_with((10, 10), []), BESTIARY, seed=99)
    assert world.attr_rng.getstate() != world.rng.getstate()
    assert world.attr_rng.getstate() != world.loot_rng.getstate()


# --- helpers -----------------------------------------------------------------
def _fight(attributes: Attributes) -> World:
    """One seeded fight with every body carrying the same attribute block.

    Written onto the live entities rather than into the bestiary: `EntityType`
    is frozen content shared by every test in the suite, and a fixture that
    edited it would leak into whatever ran next.
    """
    world = World(
        level_with((10, 10), [("grunt", (9, 10)), ("rat", (11, 10)), ("grunt", (10, 9))]),
        BESTIARY,
        seed=SEED,
    )
    for entity in world.entities:
        entity.bonus = attributes
    return world


def _damage_over_a_fight(attributes: Attributes) -> list[int]:
    world = _fight(attributes)
    damage: list[int] = []
    for _ in range(600):
        step(world, NOTHING)
        damage.extend(e.amount for e in world.events if e.kind is EventKind.HIT)
    return damage


def _rng_state_after_a_fight(attributes: Attributes):
    world = _fight(attributes)
    for _ in range(600):
        step(world, NOTHING)
    return world.rng.getstate()
