"""Content loading. The game is tuned in JSON, so the JSON has to be right."""

from __future__ import annotations

import math

import pytest

from hack_and_slash import config
from hack_and_slash.game.entities import Faction, load_bestiary

from .helpers import BESTIARY


def test_every_shipped_type_loads() -> None:
    assert set(BESTIARY.types) == {"hero", "grunt", "charger", "archer"}


def test_comment_keys_are_not_loaded_as_content() -> None:
    # JSON has no comments, and content files are where explanation is most
    # worth having, so underscore keys carry it. They must not become entities.
    assert "_comment" not in BESTIARY.types
    assert "_comment" not in BESTIARY.weapons


def test_arc_is_converted_from_degrees_to_radians() -> None:
    # The data says 100 degrees because that is what a person can picture.
    assert BESTIARY.weapons["sword"].arc == pytest.approx(math.radians(100))
    assert BESTIARY["hero"].weapon.arc == pytest.approx(math.radians(100))


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
def test_the_hero_is_faster_than_everything_it_fights() -> None:
    """The deal the whole fight rests on.

    You can always disengage, so taking a hit is a decision you made rather than
    something the arena did to you. If an enemy ever out-runs the hero, kiting
    stops working and the design changes underneath the level.
    """
    hero_speed = BESTIARY["hero"].speed
    for type_id, entity_type in BESTIARY.types.items():
        if entity_type.faction is Faction.ENEMY:
            assert entity_type.speed < hero_speed, f"{type_id} can outrun the hero"


def test_the_charger_is_faster_than_the_hero_only_while_charging() -> None:
    # Which is what makes the charge a threat and the telegraph the answer.
    charger = BESTIARY["charger"]
    assert charger.speed < BESTIARY["hero"].speed
    assert charger.charge_speed > BESTIARY["hero"].speed


def test_only_the_hero_can_dodge() -> None:
    # Expressed as data, not as a branch in the sim.
    assert BESTIARY["hero"].can_dodge
    for type_id, entity_type in BESTIARY.types.items():
        if entity_type.faction is Faction.ENEMY:
            assert not entity_type.can_dodge, f"{type_id} can dodge"


def test_every_attack_has_a_readable_telegraph() -> None:
    # An attack with no windup cannot be reacted to, only pre-empted.
    for weapon_id, weapon in BESTIARY.weapons.items():
        assert weapon.windup >= 4, f"{weapon_id} has no tell"
        assert weapon.recovery > 0, f"{weapon_id} is free to whiff"


def test_enemy_attacks_are_slower_to_start_than_the_hero_s() -> None:
    # The player reacts to enemies; enemies do not react to the player.
    hero_windup = BESTIARY["hero"].weapon.windup
    for type_id, entity_type in BESTIARY.types.items():
        if entity_type.faction is Faction.ENEMY:
            assert entity_type.weapon.windup > hero_windup, f"{type_id} strikes too fast"


def test_the_hero_iframes_do_not_outlast_the_roll() -> None:
    """Invulnerability must end before the roll does.

    Otherwise the last frames of a dodge are free, and the correct way to play
    becomes rolling constantly rather than rolling at the right moment.
    """
    hero = BESTIARY["hero"]
    assert 0 < hero.iframe_ticks < hero.dodge_ticks
