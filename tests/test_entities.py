"""Content loading. The game is tuned in JSON, so the JSON has to be right."""

from __future__ import annotations

import dataclasses
import math

import pytest

from hack_and_slash import config
from hack_and_slash.game import skills
from hack_and_slash.game.entities import Faction, load_bestiary

from .helpers import BESTIARY, HERO


CLASSES = BESTIARY.hero_classes
ENEMIES = tuple(t for t in BESTIARY.types.values() if t.faction is Faction.ENEMY)

#: The ten promoted classes, which `hero_classes` deliberately excludes.
ADVANCED = BESTIARY.advanced_classes

#: Everything the player can end up controlling. Every structural rule below --
#: four slots, the windup ceiling, iframes shorter than the roll, no dashing --
#: applies to a body the player drives, not to a body the character select
#: offers. Iterating `CLASSES` for those would have quietly narrowed each rule
#: from "every hero" to "the five starting ones" on the day promotion shipped,
#: and nothing would have failed to say so.
PLAYABLE = CLASSES + ADVANCED


def test_every_shipped_type_loads() -> None:
    assert set(BESTIARY.types) == {
        # the roster
        "knight", "rogue", "archer", "magician", "priest",
        # what it fights
        "grunt", "rat", "charger", "brute", "bowman", "mage",
        # and what it fights after the fork
        "revenant", "stalker",
        # and the fifth brain, in acts VII-VIII
        "demon",
        # one at the end of each act
        "boss", "houndmaster", "effigy", "sovereign",
        "herald", "gaoler", "choir", "hollow_king",
        "regent", "unmade",
        # promoted halfway, two per starting class
        "dark_knight", "holy_knight",
        "assassin", "shadow_rogue",
        "hunter", "magic_archer",
        "sage", "wizard",
        "battle_priest", "holy_priest",
        # cosmetic variants: an existing creature wearing another face, with
        # every number copied from the line named in `variant_of`
        "goblin", "goblin_slinger", "goblin_pup",
        "orc", "orc_charger",
        "beastman", "beastman_stalker",
        "imp", "hellhound",
    }


def test_the_roster_is_the_five_classes_in_file_order() -> None:
    """The character select reads this, so the order is content, not incidental.

    Faction is the only thing that makes something playable -- there is no
    second list to keep in step -- which is what this is really checking.
    """
    assert [c.id for c in CLASSES] == ["knight", "rogue", "archer", "magician", "priest"]


def test_every_class_is_actually_playable() -> None:
    """The three things a class needs that an enemy does not.

    A class missing any of them loads fine and then fails in a way that looks
    like a sim bug: no brain means the player's input is ignored, no dodge means
    the roll key does nothing, no heal means the run cannot be sustained.
    """
    for cls in PLAYABLE:
        assert cls.brain == "player", f"{cls.id} is not driven by the player"
        assert cls.can_dodge, f"{cls.id} cannot roll"
        assert cls.heal_between_stages > 0, f"{cls.id} recovers nothing between stages"


def test_comment_keys_are_not_loaded_as_content() -> None:
    # JSON has no comments, and content files are where explanation is most
    # worth having, so underscore keys carry it. They must not become entities.
    assert "_comment" not in BESTIARY.types
    assert "_comment" not in BESTIARY.weapons


def test_arc_is_converted_from_degrees_to_radians() -> None:
    # The data says 120 degrees because that is what a person can picture.
    assert BESTIARY.weapons["greatsword"].arc == pytest.approx(math.radians(120))
    assert HERO.weapon.arc == pytest.approx(math.radians(120))


def test_an_unknown_type_names_what_is_available() -> None:
    with pytest.raises(KeyError, match="archer"):
        BESTIARY["wyvern"]


def test_a_type_wanting_a_missing_weapon_fails_loudly(tmp_path) -> None:
    entities = tmp_path / "entities.json"
    entities.write_text(
        '{"ghoul": {"faction": "enemy", "hp": 5, "speed": 1, "radius": 4, '
        '"weapon": "scythe"}}',
        encoding="utf-8",
    )
    with pytest.raises(KeyError, match="scythe"):
        load_bestiary(entities, config.WEAPONS_DATA)


# --- balance the design depends on -------------------------------------------
def test_every_class_is_faster_than_everything_it_fights() -> None:
    """The deal the whole fight rests on, and it has to hold for all five.

    You can always disengage, so taking a hit is a decision you made rather than
    something the arena did to you. If an enemy ever out-runs a class, kiting
    stops working *for that class* and the design changes underneath the level
    for whoever picked it.

    Measured against the slowest class rather than an average or the default:
    an enemy that only outpaces the Knight is still an enemy that broke the
    game, for the third of players who picked the Knight.
    """
    slowest = min(PLAYABLE, key=lambda c: c.speed)
    for entity_type in ENEMIES:
        assert entity_type.speed < slowest.speed, (
            f"{entity_type.id} at {entity_type.speed} can outrun the "
            f"{slowest.name} at {slowest.speed}"
        )


def test_the_charger_is_faster_than_the_hero_only_while_charging() -> None:
    """Which is what makes the charge a threat and the telegraph the answer.

    The dash speed belongs to the *weapon*, not the creature -- a body with
    several attacks must only dash on the one that is actually a charge.
    """
    charger = BESTIARY["charger"]
    fastest = max(c.speed for c in PLAYABLE)
    assert charger.speed < min(c.speed for c in PLAYABLE)
    # Faster than *anyone* once committed, or the charge is not a threat to the
    # class that most needs to respect it.
    assert charger.weapon.charge_speed > fastest
    assert charger.weapon.is_charge


def test_only_charging_attacks_carry_a_dash() -> None:
    """The bug this forbids: a boss drifting forward during its ranged attack
    because the dash was a property of the creature rather than the attack.

    Checked across every boss, since each one declares its own three weapons and
    the mistake is exactly as easy to make the fourth time as the first."""
    for boss in (t for t in BESTIARY.types.values() if t.brain == "boss"):
        charging = [w.id for w in boss.weapons if w.is_charge]
        assert charging == [boss.weapons[1].id], (
            f"{boss.id} has charging attacks {charging}, but the brain only "
            "dashes on weapons[1]"
        )

    assert not BESTIARY.weapons["greatsword"].is_charge
    assert not BESTIARY.weapons["claw"].is_charge


def test_only_the_classes_can_dodge() -> None:
    # Expressed as data, not as a branch in the sim.
    for cls in PLAYABLE:
        assert cls.can_dodge, f"{cls.id} cannot roll"
    for entity_type in ENEMIES:
        assert not entity_type.can_dodge, f"{entity_type.id} can dodge"


def test_every_attack_has_a_readable_telegraph() -> None:
    # An attack with no windup cannot be reacted to, only pre-empted.
    for weapon_id, weapon in BESTIARY.weapons.items():
        assert weapon.windup >= 4, f"{weapon_id} has no tell"
        assert weapon.recovery > 0, f"{weapon_id} is free to whiff"


def test_enemy_attacks_are_slower_to_start_than_any_class_s_light_attack() -> None:
    """The player reacts to enemies; enemies do not react to the player.

    Compared against the *slowest light* attack, which is the strong form of the
    rule for the attack it applies to: every enemy tell in the game is longer
    than every class's default swing, so the rule holds whichever class was
    picked. The Magician's 12-tick bolt is the binding number and the rat's
    16-tick bite is what it binds against -- four ticks of room, deliberate
    rather than lucky.

    **Why the light slot and not all four.** This used to read `c.weapon`, which
    was the same thing when a class had one attack. It is stated as the light
    slot now because a heavy or an ultimate is allowed to telegraph for longer
    than anything an enemy does, and several of them do -- the Knight's
    Onslaught winds up for 30 ticks, longer than a brute's maul.

    That is not the rule failing, it is the rule not applying. An enemy's tell
    is imposed on you and the whole fight rests on being able to answer it with
    a swing of your own; a heavy's tell is one you chose to spend, from a slot
    that then goes on cooldown for five seconds. The attack you answer a
    telegraph *with* is the light one, and it is still faster than every tell in
    the game.
    """
    slowest_light = max(c.weapons[skills.LIGHT].windup for c in PLAYABLE)
    for entity_type in ENEMIES:
        for weapon in entity_type.weapons:
            assert weapon.windup > slowest_light, (
                f"{entity_type.id}'s {weapon.id} winds up in {weapon.windup} ticks, "
                f"faster than the slowest class light attack at {slowest_light}"
            )


# --- the four slots ----------------------------------------------------------
def test_every_class_declares_its_four_slots_in_the_order_the_game_expects() -> None:
    """The hero-side counterpart to the boss ordering test below, and it exists
    for exactly the same reason: the slot is an *index*, so a class that lists
    its attacks in another order loads perfectly and then binds the ultimate to
    the light-attack button.

    Only the relationships are pinned, not the values. The numbers in these
    fifteen attacks are a first pass that the reference bot cannot measure --
    it plays light-only by design -- so asserting any of them would be pinning
    a guess. What is pinned is what makes a slot that slot.
    """
    for cls in PLAYABLE:
        assert len(cls.weapons) == len(skills.SLOTS), (
            f"{cls.id} has {len(cls.weapons)} attacks; every class needs "
            f"{len(skills.SLOTS)}"
        )
        light, neutral, heavy, ultimate = cls.weapons

        # Light is index 0 and free. Everything that predates skills reads
        # `type.weapon`, which is weapons[0], so this is what keeps the whole
        # recorded balance of the game measuring what it measured before.
        assert light.cooldown == 0, f"{cls.id}'s light attack is on a cooldown"

        cooldowns = [w.cooldown for w in (neutral, heavy, ultimate)]
        assert cooldowns == sorted(cooldowns) and len(set(cooldowns)) == 3, (
            f"{cls.id}'s cooldowns are {cooldowns}; they must ascend with the slot"
        )
        assert ultimate.cooldown >= 1200, (
            f"{cls.id}'s ultimate comes back every {ultimate.cooldown} ticks, "
            "which is not an ultimate"
        )

        # Neutral buys position; heavy buys damage. A neutral that out-damages
        # the light attack is just a better light attack on a cooldown.
        assert neutral.damage < light.damage, (
            f"{cls.id}'s {neutral.id} hits for {neutral.damage} against the "
            f"light attack's {light.damage}"
        )
        assert heavy.damage > light.damage, f"{cls.id}'s heavy does not hit harder"
        assert heavy.total_ticks > light.total_ticks, (
            f"{cls.id}'s heavy commits for no longer than its light attack"
        )

        # The ultimate is the largest payoff the class has. Measured as total
        # damage on the table rather than per hit, because two of the five are
        # fans -- a single Rain arrow hits for less than a Piercer and there are
        # five of them.
        assert _payload(ultimate) > _payload(heavy), (
            f"{cls.id}'s ultimate offers {_payload(ultimate)} damage against "
            f"its heavy's {_payload(heavy)}"
        )


def _payload(weapon) -> int:
    """Everything one use of an attack can deal, fans included."""
    return weapon.damage * max(1, weapon.projectile_count if weapon.projectile else 1)


def test_no_hero_skill_dashes() -> None:
    """`charge_speed` works on a hero attack and is deliberately unused.

    A lunging skill and the dodge would want designing against each other --
    both are "commit to a direction and cover ground" -- and that is a bigger
    question than adding four buttons. Recorded as a test so the absence reads
    as a decision rather than as something nobody got round to.
    """
    for cls in PLAYABLE:
        for weapon in cls.weapons:
            assert not weapon.is_charge, f"{cls.id}'s {weapon.id} dashes"


def test_no_class_s_iframes_outlast_its_roll() -> None:
    """Invulnerability must end before the roll does.

    Otherwise the last frames of a dodge are free, and the correct way to play
    becomes rolling constantly rather than rolling at the right moment. Five
    classes means five chances to get this wrong, and the symptom -- "this class
    feels weirdly unkillable" -- is a long way from the two numbers causing it.
    """
    for cls in PLAYABLE:
        assert 0 < cls.iframe_ticks < cls.dodge_ticks, (
            f"{cls.id} is invulnerable for {cls.iframe_ticks} of a "
            f"{cls.dodge_ticks}-tick roll"
        )


def test_every_boss_declares_its_three_attacks_in_the_order_the_brain_expects() -> None:
    """The one assumption in this game that is positional rather than named.

    `ai.py` reads weapons[0] as the sweep it uses up close, weapons[1] as the
    charge it uses at mid range, and weapons[2] as what it shoots from far away.
    Nothing in the loader checks that, so a boss whose JSON lists them in any
    other order loads perfectly and then telegraphs one attack while landing
    another -- which reads as a physics bug, not as a typo in a content file.
    """
    for boss in (t for t in BESTIARY.types.values() if t.brain == "boss"):
        sweep, crush, volley = None, None, None
        assert len(boss.weapons) == 3, (
            f"{boss.id} has {len(boss.weapons)} attacks; the boss brain needs "
            "exactly three"
        )
        sweep, crush, volley = boss.weapons

        assert sweep.reach > 0 and not sweep.projectile, f"{boss.id}: weapons[0] is not a sweep"
        assert crush.is_charge, f"{boss.id}: weapons[1] does not charge"
        assert volley.projectile, f"{boss.id}: weapons[2] does not shoot"
        assert boss.charge_range > 0, f"{boss.id} can never reach its charge"
        # And the bar the HUD draws is keyed off the scale, not off the brain.
        assert boss.sprite_scale > 1, f"{boss.id} would fight without a boss bar"


def test_every_enemy_declares_what_killing_it_is_worth() -> None:
    """`level` is the loot layer's only input from the bestiary.

    Left at the default it would silently pay out as though a sovereign were a
    rat -- which is not an error anywhere, just a reward curve that quietly does
    nothing. So it is checked here rather than discovered in play.
    """
    for enemy in ENEMIES:
        assert enemy.level >= 1, f"{enemy.id} has a level below 1"
        # The rat's *line*, not the default. A variant copies its base's wage
        # along with everything else, so a re-skinned rat is legitimately on 1 --
        # but widening this to "or it is a variant" would stop it catching a
        # variant whose level was simply forgotten, which is the whole job.
        on_the_rats_line = enemy.id == "rat" or enemy.variant_of == "rat"
        assert enemy.level > 1 or on_the_rats_line, (
            f"{enemy.id} is still on the default level of 1; only the rat, which "
            "is the floor of the scale, and things that copy it are meant to be"
        )


def test_no_class_is_worth_anything_to_kill() -> None:
    """Heroes keep the default, and nothing pays out for one.

    Not a hypothetical: `Faction` has `hostile_to` in both directions and the
    loot roll is handed whatever just died. A class carrying a level would put a
    price on the player's own head the day something friendly-fires.
    """
    for cls in PLAYABLE:
        assert cls.level == 1, f"{cls.id} declares a level; only enemies should"


def test_the_top_of_the_level_ladder_is_a_boss() -> None:
    """The whole reason level is separate from floor.

    This used to assert that the *weakest* boss outranked the strongest
    ordinary enemy, which held for as long as the ladder was one act deep and
    stopped holding at eight bosses: the Warden is a level 5 fought on stage 5,
    and the stalker is a level 6 first met on stage 26. Nothing pays them out
    on the same floor, and forcing every act V-VIII enemy under an act I boss
    would flatten twenty stages of the scale to keep an ordering that no kill
    ever observes.

    The claim that survives -- and the one that has to -- is per stage:
    `test_a_boss_outranks_its_own_escort` in the playthrough suite checks the
    arenas as shipped, which is where a boss and a grunt actually share a floor
    number. This is the content half of it: the scale is topped by a boss, so
    the most valuable kill in the game is a fight rather than a chore.
    """
    bosses = [t for t in ENEMIES if t.brain == "boss"]
    rank_and_file = [t for t in ENEMIES if t.brain != "boss"]

    assert bosses and rank_and_file
    assert max(b.level for b in bosses) > max(e.level for e in rank_and_file)


def test_level_is_not_just_health_wearing_a_hat() -> None:
    """Level ranks danger; hp ranks how long something takes to kill.

    If the two agreed everywhere, the field would be dead weight and deriving it
    from hp would be the better design. They disagree on the brute, which is the
    slowest, healthiest thing in the game that is barely a threat on its own --
    and that disagreement is the argument for the field existing at all.
    """
    by_level = sorted(ENEMIES, key=lambda t: t.level)
    by_hp = sorted(ENEMIES, key=lambda t: t.hp)
    assert [t.id for t in by_level] != [t.id for t in by_hp]


# --- variants -----------------------------------------------------------------
#: The only three things a variant is allowed to change. Everything else in
#: `EntityType` is a number the balance grid has measured.
MAY_DIFFER = {"id", "name", "sprite", "variant_of"}


def test_every_variant_names_a_base_that_exists() -> None:
    """A typo here is a creature quietly claiming to copy nothing.

    The identity test below iterates the same set, so a `variant_of` pointing at
    a name that is not in the bestiary would raise there rather than fail -- and
    a KeyError in a test is a broken test, not a reported problem.
    """
    assert BESTIARY.variants, "no variants loaded; the set is meant to be nine"
    for variant in BESTIARY.variants:
        assert variant.variant_of in BESTIARY.types, (
            f"{variant.id} is a variant of '{variant.variant_of}', which is not "
            f"a type; known types: {', '.join(sorted(BESTIARY.types))}"
        )


def test_a_variant_is_stat_identical_to_what_it_varies() -> None:
    """The load-bearing test of the whole variant idea.

    A variant exists so a stage can field a goblin where it fielded a grunt
    *without* fielding anything the class x stage grid has not already measured.
    That is only true if the numbers are the same ones -- and "the same ones" is
    a claim about twenty-odd fields that nobody is going to re-check by eye every
    time this data is touched.

    The alternative was a multi-minute balance sweep proving the grid did not
    move. This settles the same claim in milliseconds, and it settles it for
    every future variant rather than for the nine that exist today.

    Iterates `dataclasses.fields` rather than a list of names on purpose: a field
    added to `EntityType` later is covered the day it lands, where a hand-written
    list would silently stop checking it.
    """
    for variant in BESTIARY.variants:
        base = BESTIARY[variant.variant_of]
        for field in dataclasses.fields(variant):
            if field.name in MAY_DIFFER:
                continue
            mine = getattr(variant, field.name)
            theirs = getattr(base, field.name)
            assert mine == theirs, (
                f"{variant.id}.{field.name} is {mine!r}, but it is a variant of "
                f"{base.id}, which has {theirs!r}. A variant carries no numbers "
                "of its own -- if this one needs to, it wants its own entry in "
                "entities.json and its own tuning pass."
            )


def test_a_variant_is_never_a_variant_of_a_variant() -> None:
    """One hop, so "identical to its base" means one unambiguous thing.

    A chain would still be identical in practice -- identity is transitive -- but
    it would make the failure message above point at a creature that is itself a
    copy, and it invites a middle link that quietly acquires a number of its own.
    """
    for variant in BESTIARY.variants:
        base = BESTIARY[variant.variant_of]
        assert not base.variant_of, (
            f"{variant.id} varies {base.id}, which is itself a variant of "
            f"{base.variant_of}; variants copy an original, not each other"
        )


def test_no_class_is_a_variant() -> None:
    """`variant_of` is enemy-only, the way `promotes_from` is hero-only.

    A hero carrying one would put a class in `Bestiary.variants` and assert that
    its stats match another class's -- which is the opposite of what the roster
    is for.
    """
    for cls in PLAYABLE:
        assert not cls.variant_of, f"{cls.id} declares variant_of; only enemies should"


# --- promotion ---------------------------------------------------------------
def test_the_roster_excludes_promoted_classes() -> None:
    """The one filter this whole feature's safety rests on.

    Eight places read `hero_classes` -- the character select, both tools, and
    five test modules including the class x stage balance grid. A promoted class
    arriving in it would put fifteen columns on a screen laid out for five and
    take the grid from 80 cells to 280, every new one untuned and failing.

    So the two properties are asserted as a partition rather than individually:
    every hero is in exactly one of them, and nothing is in both.
    """
    assert all(not c.promotes_from for c in CLASSES)
    assert all(c.promotes_from for c in ADVANCED)

    heroes = {t.id for t in BESTIARY.types.values() if t.faction is Faction.HERO}
    assert {c.id for c in CLASSES} | {c.id for c in ADVANCED} == heroes
    assert not {c.id for c in CLASSES} & {c.id for c in ADVANCED}


def test_every_starting_class_promotes_into_exactly_two() -> None:
    """A fork, not a menu and not a rename.

    One promotion would be a free upgrade with nothing to weigh; three would not
    fit the panel, which puts them on keys 1 and 2.
    """
    for cls in CLASSES:
        offers = BESTIARY.promotions_for(cls.id)
        assert len(offers) == 2, (
            f"{cls.id} promotes into {[o.id for o in offers]}; every class needs two"
        )


def test_every_promotion_descends_from_a_class_that_exists() -> None:
    """A typo in `promotes_from` is otherwise invisible: the class loads, and it
    is simply never offered to anybody."""
    roster = {c.id for c in CLASSES}
    for cls in ADVANCED:
        assert cls.promotes_from in roster, (
            f"{cls.id} promotes from '{cls.promotes_from}', which is not a class"
        )


def test_a_promoted_class_inherits_its_base_s_light_and_neutral() -> None:
    """Promotion changes the top two slots and nothing else about the kit.

    The light attack in particular: it is `weapons[0]`, which everything that
    predates skills reads through `type.weapon`, and it is the attack the whole
    recorded balance of the game was measured on. A promotion that replaced it
    would make a promoted class a different game rather than a specialisation of
    the one being played.
    """
    for cls in ADVANCED:
        base = BESTIARY[cls.promotes_from]
        assert cls.weapons[skills.LIGHT].id == base.weapons[skills.LIGHT].id, (
            f"{cls.id} does not swing what a {base.id} swings"
        )
        assert cls.weapons[skills.NEUTRAL].id == base.weapons[skills.NEUTRAL].id
        # And the other two must actually be new, or the branch is a stat patch.
        assert cls.weapons[skills.HEAVY].id != base.weapons[skills.HEAVY].id
        assert cls.weapons[skills.ULTIMATE].id != base.weapons[skills.ULTIMATE].id


def test_a_promotion_never_changes_the_size_of_the_body() -> None:
    """`Entity.radius` reads through to the type, and promotion swaps the type on
    a body that is already standing somewhere.

    A wider radius would take effect on the next tick with the hero possibly
    already overlapping the wall it was standing beside -- a collision resolved
    by shoving it somewhere it could not have walked.
    """
    for cls in ADVANCED:
        base = BESTIARY[cls.promotes_from]
        assert cls.radius == base.radius, (
            f"{cls.id} is {cls.radius} wide against the {base.id}'s {base.radius}"
        )


def test_the_fork_is_not_a_decision_about_healing() -> None:
    """The two branches of a class recover the same amount between stages.

    This used to be a stronger claim -- that no advanced class differed from its
    *base* at all -- on the grounds that `heal_between_stages` could never pay
    out: promotion happened on the way into the final stage and there was no
    stage after it.

    Twenty stages now follow the fork, and the measurement forced the issue. The
    Knight line finishes 1/6 runs at the base class's 56 and 6/6 at 84; the
    Rogue line goes 1/6 to 4/6 at 60. Acts V-VIII cost more health per stage
    than acts I-IV do, and a heal that was right for the first half is not right
    for the second. Those two lines were re-measured; the Archer, Magician and
    Priest lines needed nothing and kept their inherited numbers.

    **What has to stay true is the narrower thing, and it is the original point
    of the rule:** the choice between two branches must never be a choice about
    healing. "The healing one" is the obvious and wrong design for half of
    these -- the Holy Priest and the Holy Knight would both collapse into it --
    so a branch has to earn "outlasts it" from health, arc and knockback.

    A tier may heal more than the tier below it. A branch may not heal more than
    its twin.

    **Regen is the second heal channel, and it is checked here for the reason
    the rule exists rather than as an afterthought.** `heal_between_stages` was
    the only way to recover health when this test was written. An attribute
    block that gave the Holy branch more regen than its twin would make the fork
    a decision about healing through a door this test was not watching, and the
    number would not appear anywhere near the one it was competing with.
    """
    for cls in ADVANCED:
        twin = next(
            other
            for other in ADVANCED
            if other.promotes_from == cls.promotes_from and other.id != cls.id
        )
        assert cls.heal_between_stages == twin.heal_between_stages, (
            f"{cls.id} and {twin.id} recover different amounts between stages, "
            "which makes the fork partly a decision about healing"
        )
        assert cls.heal_between_stages >= BESTIARY[cls.promotes_from].heal_between_stages, (
            f"{cls.id} recovers less between stages than the {cls.promotes_from} "
            "it was promoted from, which is a stealth nerf for taking the fork"
        )
        assert cls.attributes.regen == twin.attributes.regen, (
            f"{cls.id} regenerates {cls.attributes.regen} where {twin.id} "
            f"regenerates {twin.attributes.regen}. Same rule as the line above "
            "and the same reason -- regen is healing, so a branch that has more "
            "of it is 'the healing one' however the number is spelled"
        )
