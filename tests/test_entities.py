"""Content loading. The game is tuned in JSON, so the JSON has to be right."""

from __future__ import annotations

import math

import pytest

from hack_and_slash import config
from hack_and_slash.game import skills
from hack_and_slash.game.entities import Faction, load_bestiary

from .helpers import BESTIARY, HERO


CLASSES = BESTIARY.hero_classes
ENEMIES = tuple(t for t in BESTIARY.types.values() if t.faction is Faction.ENEMY)


def test_every_shipped_type_loads() -> None:
    assert set(BESTIARY.types) == {
        # the roster
        "knight", "rogue", "archer", "magician", "priest",
        # what it fights
        "grunt", "rat", "charger", "brute", "bowman", "mage",
        # one at the end of each act
        "boss", "houndmaster", "effigy", "sovereign",
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
    for cls in CLASSES:
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
    slowest = min(CLASSES, key=lambda c: c.speed)
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
    fastest = max(c.speed for c in CLASSES)
    assert charger.speed < min(c.speed for c in CLASSES)
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
    for cls in CLASSES:
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
    slowest_light = max(c.weapons[skills.LIGHT].windup for c in CLASSES)
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
    for cls in CLASSES:
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
    for cls in CLASSES:
        for weapon in cls.weapons:
            assert not weapon.is_charge, f"{cls.id}'s {weapon.id} dashes"


def test_no_class_s_iframes_outlast_its_roll() -> None:
    """Invulnerability must end before the roll does.

    Otherwise the last frames of a dodge are free, and the correct way to play
    becomes rolling constantly rather than rolling at the right moment. Five
    classes means five chances to get this wrong, and the symptom -- "this class
    feels weirdly unkillable" -- is a long way from the two numbers causing it.
    """
    for cls in CLASSES:
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
