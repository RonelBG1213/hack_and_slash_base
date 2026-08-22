"""Champions, and the claim that the campaign has never met one.

This is `test_difficulty.py`'s expensive half pointed at a different layer, and
the claim is the same shape: **a world built the way every tool, every sweep and
every other test in this project builds one is the fight the recorded 280 cells
were measured in** -- not approximately, but drawing the same dice in the same
order from the same generator.

It is settled here structurally rather than by a sweep, which is the pattern
`docs/testing.md` records four times already: the loot stream, the attribute
stream, the map stream and the hazard stream each proved the same thing about
themselves in milliseconds where `tools/balance.py` takes minutes and proves
less. This is the fifth.

Two things carry it, and they are deliberately independent:

* `World(...)` takes `elites=OFF` **by default**, so no caller that predates
  this layer can meet a champion however `data/elites.json` is tuned.
* `Table.roll_for` returns before it touches the generator when the layer is
  off, so the stream is not merely separate -- it is unsampled.
"""

from __future__ import annotations

import json
import random

import pytest

from hack_and_slash import config
from hack_and_slash.core import campaign_io
from hack_and_slash.game import elites
from hack_and_slash.game.attributes import NEUTRAL, PER_MILLE, Attributes
from hack_and_slash.game.difficulty import Difficulty, Enemies
from hack_and_slash.game.elites import OFF, Affix, Table
from hack_and_slash.game.world import Purse, World

from .helpers import BESTIARY, level_with, open_room

SEED = 4321

#: A layer that fires on everything, so a test does not have to hunt for the one
#: seed that rolled. `chance` at `PER_MILLE` is every ordinary spawn.
ALWAYS = Table(
    enabled=True,
    chance=PER_MILLE,
    from_floor=1,
    bosses=False,
    affixes=(Affix(id="armoured", name="Armoured", hp=1400, attributes=Attributes(defense=2)),),
)


def a_stage(*enemies: str):
    """A level with the named creatures in a row, away from the hero."""
    return level_with((3, 3), [(type_id, (10, 4 + i)) for i, type_id in enumerate(enemies)])


def world_with(table: Table, level=None, floor: int = 1, seed: int = SEED) -> World:
    return World(
        level or a_stage("grunt", "grunt", "grunt"),
        BESTIARY,
        seed=seed,
        purse=Purse(floor=floor),
        elites=table,
    )


def table_from(payload: dict, tmp_path) -> Table:
    path = tmp_path / "elites.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return Table.load(path)


def a_payload(**overrides) -> dict:
    payload = {
        "enabled": True,
        "chance": 100,
        "affixes": [{"id": "armoured", "name": "Armoured", "hp": 1400}],
    }
    payload.update(overrides)
    return payload


# --- the identity, which is the whole file -----------------------------------
def test_a_world_built_without_an_opinion_has_no_champions_in_it() -> None:
    """The guarantee, at the seam it lives at. Every caller in the project --
    `tools/balance.py`, `game/autoplay.py`, `tests/test_playthrough.py` -- builds
    a world this way."""
    assert World(open_room(), BESTIARY, seed=SEED).elites.is_off


def test_the_shipped_default_is_off_however_the_file_is_tuned() -> None:
    assert OFF.is_off
    assert OFF.chance == 0
    assert not OFF.affixes


def test_an_off_layer_draws_no_dice_at_all() -> None:
    """Not "draws from its own stream" -- draws *nothing*. The generator is
    constructed and never sampled, so tuning `data/elites.json` cannot move a
    world that did not ask for champions even by one number."""
    world = world_with(OFF)
    untouched = random.Random(SEED ^ elites.ELITE_STREAM)
    assert world.elite_rng.getstate() == untouched.getstate()


def test_every_enemy_in_a_default_world_carries_the_shared_neutral_block() -> None:
    """By identity and not by value. `_populate` gates on `is not NEUTRAL`, and
    an equal-but-distinct block would take that branch on every body."""
    for enemy in world_with(OFF).enemies():
        assert enemy.bonus is NEUTRAL


def test_no_enemy_in_any_shipped_stage_is_a_champion() -> None:
    """All fifty arenas, because the claim is about the campaign and not about
    a room a test made up."""
    campaign = campaign_io.load(config.LEVELS_DIR / "campaign.json")
    for index, level in enumerate(campaign.stages):
        world = World(level, BESTIARY, seed=SEED + index, purse=Purse(floor=index + 1))
        assert not world.elite_ids, f"stage {index + 1} rolled a champion"
        for enemy in world.enemies():
            assert enemy.bonus is NEUTRAL


def test_the_elite_stream_is_not_any_of_the_others() -> None:
    """Two generators seeded identically are one generator, which is the whole
    mechanism -- `world.py` says so in the module docstring."""
    world = world_with(ALWAYS)
    states = [
        random.Random(SEED).getstate(),
        world.loot_rng.getstate(),
        world.attr_rng.getstate(),
        world.hazard_rng.getstate(),
    ]
    fresh = random.Random(SEED ^ elites.ELITE_STREAM).getstate()
    for other in states:
        assert fresh != other


def test_rolling_champions_does_not_disturb_the_damage_stream() -> None:
    """The test that was written for the loot layer, for the attribute layer,
    for the map stream and for the hazards, made a fifth time. A champion is
    rolled at construction; the fight's generator must be where it was."""
    plain = world_with(OFF)
    champions = world_with(ALWAYS)

    assert champions.elite_ids, "the fixture rolled nothing, so it proves nothing"
    assert plain.rng.getstate() == champions.rng.getstate()
    assert plain.loot_rng.getstate() == champions.loot_rng.getstate()
    assert plain.attr_rng.getstate() == champions.attr_rng.getstate()


# --- what a champion is ------------------------------------------------------
def test_a_champion_is_tougher_than_the_monster_it_was() -> None:
    plain = world_with(OFF).enemies()[0]
    champion = world_with(ALWAYS).enemies()[0]

    assert champion.max_hp > plain.max_hp
    assert champion.hp == champion.max_hp, "it spawned at its new ceiling"
    assert champion.attrs.defense > plain.attrs.defense


def test_an_affix_resolves_its_health_against_the_creature_it_lands_on() -> None:
    """The reason health is per-mille: +40% is a champion on both a rat and a
    brute, where a flat +20 is a rounding error on one and a different animal on
    the other."""
    affix = Affix(id="a", name="A", hp=1400)
    small = affix.block_for(BESTIARY["rat"]).max_hp
    large = affix.block_for(BESTIARY["brute"]).max_hp
    assert 0 < small < large


def test_a_champion_lands_beside_the_tier_block_rather_than_replacing_it() -> None:
    """A champion on Hard is both. Neither dial says that on its own."""
    tier = Difficulty(id="hard", name="Hard", enemies=Enemies(hp=1200))
    level = a_stage("grunt")

    on_tier = World(level, BESTIARY, seed=SEED, difficulty=tier).enemies()[0]
    both = World(
        level, BESTIARY, seed=SEED, difficulty=tier, elites=ALWAYS
    ).enemies()[0]

    assert both.max_hp > on_tier.max_hp
    assert both.attrs.defense > on_tier.attrs.defense


def test_a_champion_is_marked_for_the_renderer() -> None:
    world = world_with(ALWAYS)
    assert set(world.elite_ids) == {e.id for e in world.enemies()}
    assert set(world.elite_ids.values()) == {"armoured"}


def test_a_mark_is_never_drawn_on_a_body_the_affix_did_not_change() -> None:
    """The loader refuses an affix that changes nothing, and says why: a
    champion the player cannot tell from an ordinary monster is a mark that
    means nothing. But that question is asked of the affix in the abstract,
    while `hp` is per-mille of the creature it lands on and floors -- so a
    gentle health-only affix rounds away to nothing on the smallest bodies in
    the game and the promise stops holding exactly there.

    A rat has 8 health, so +10% of it is zero.
    """
    gentle = Table(
        enabled=True,
        chance=PER_MILLE,
        from_floor=1,
        affixes=(Affix(id="tough", name="Tough", hp=1100),),
    )
    assert not gentle.affixes[0].is_identity, "the loader would have taken this"
    assert gentle.affixes[0].block_for(BESTIARY["rat"]) is NEUTRAL

    world = world_with(gentle, level=a_stage("rat"))
    rat = world.enemies()[0]

    assert world.elite_ids == {}, "a ring over a monster with nothing on it"
    assert rat.bonus is NEUTRAL


def test_an_affix_that_rounds_away_still_costs_the_layer_its_dice() -> None:
    """The skip is about what is *recorded*, never about what is rolled.

    Moving the roll behind the identity test would make how far this stream
    advances depend on which creature the affix happened to land on -- which is
    the one thing every one of the five streams exists to prevent.
    """
    gentle = Table(
        enabled=True,
        chance=PER_MILLE,
        from_floor=1,
        affixes=(Affix(id="tough", name="Tough", hp=1100),),
    )
    level = a_stage("rat", "rat")

    # Two rats, so two rolls -- even though neither of them is recorded.
    by_hand = random.Random(SEED ^ elites.ELITE_STREAM)
    for _ in range(2):
        gentle.roll_for(BESTIARY["rat"], 1, by_hand)

    world = World(level, BESTIARY, seed=SEED, purse=Purse(floor=1), elites=gentle)

    assert world.elite_ids == {}
    assert world.elite_rng.random() == by_hand.random(), (
        "the world's stream is not where two rolls leave it"
    )


def test_nothing_under_game_reads_the_mark() -> None:
    """The mark is the renderer's copy of a fact the sim already has as
    attributes. A second reading under `game/` is how the two start
    disagreeing."""
    import pathlib

    root = pathlib.Path(elites.__file__).parent
    for module in root.glob("*.py"):
        if module.name == "world.py":
            continue
        assert "elite_ids" not in module.read_text(encoding="utf-8"), module.name


def test_the_same_seed_rolls_the_same_champions() -> None:
    table = Table(
        enabled=True, chance=500, from_floor=1, affixes=elites.table().affixes
    )
    first = world_with(table, a_stage(*["grunt"] * 12))
    again = world_with(table, a_stage(*["grunt"] * 12))
    assert first.elite_ids == again.elite_ids


def test_a_different_seed_rolls_different_champions() -> None:
    table = Table(
        enabled=True, chance=500, from_floor=1, affixes=elites.table().affixes
    )
    level = a_stage(*["grunt"] * 12)
    rolls = {
        tuple(sorted(world_with(table, level, seed=s).elite_ids.values()))
        for s in range(8)
    }
    assert len(rolls) > 1


# --- what a champion may never be --------------------------------------------
def test_no_boss_is_ever_a_champion() -> None:
    """A boss is already the act's statement. It is also the one body with a
    health bar of its own, and a mark on it competes with that."""
    world = world_with(ALWAYS, a_stage("sovereign", "grunt"))
    assert BESTIARY["sovereign"].is_boss, "the fixture is not fighting a boss"

    marked = [e for e in world.enemies() if e.id in world.elite_ids]
    assert marked, "the fixture rolled nothing"
    assert all(not e.type.is_boss for e in marked)


def test_a_boss_costs_the_layer_no_dice() -> None:
    """The early return happens before the generator is touched, so a stage full
    of bosses leaves the stream exactly where a stage of none would."""
    rng = random.Random(11)
    before = rng.getstate()
    assert ALWAYS.roll_for(BESTIARY["sovereign"], 5, rng) is None
    assert rng.getstate() == before


def test_a_champion_waits_for_the_floor_the_table_names() -> None:
    late = Table(enabled=True, chance=PER_MILLE, from_floor=5, affixes=ALWAYS.affixes)
    assert not world_with(late, floor=4).elite_ids
    assert world_with(late, floor=5).elite_ids


def test_an_early_floor_costs_the_layer_no_dice() -> None:
    late = Table(enabled=True, chance=PER_MILLE, from_floor=5, affixes=ALWAYS.affixes)
    rng = random.Random(11)
    before = rng.getstate()
    assert late.roll_for(BESTIARY["grunt"], 1, rng) is None
    assert rng.getstate() == before


# --- the loader --------------------------------------------------------------
def test_the_loader_refuses_a_flat_health_affix(tmp_path) -> None:
    """The one people will reach for. Health is per-mille of the creature."""
    payload = a_payload(
        affixes=[{"id": "a", "name": "A", "attributes": {"max_hp": 20}}]
    )
    with pytest.raises(ValueError, match="sets max_hp"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_an_affix_that_roots_a_creature(tmp_path) -> None:
    """Nothing paths around walls in this game, so a monster that cannot walk is
    a stage that never ends -- and every instrument reports that as a balance
    failure."""
    payload = a_payload(
        affixes=[{"id": "a", "name": "A", "attributes": {"move_speed": -1000}}]
    )
    with pytest.raises(ValueError, match="roots the creature"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_an_affix_nothing_can_hit(tmp_path) -> None:
    payload = a_payload(
        affixes=[{"id": "a", "name": "A", "attributes": {"evasion": PER_MILLE}}]
    )
    with pytest.raises(ValueError, match="cannot be hit|nothing can hit|evasion"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_an_affix_that_changes_nothing(tmp_path) -> None:
    """A champion is a mark as well as a block, so an affix the player cannot
    tell from an ordinary monster is worse than no affix."""
    payload = a_payload(affixes=[{"id": "a", "name": "A"}])
    with pytest.raises(ValueError, match="changes nothing"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_an_affix_that_can_never_be_rolled(tmp_path) -> None:
    payload = a_payload(
        affixes=[{"id": "a", "name": "A", "hp": 1400, "weight": 0}]
    )
    with pytest.raises(ValueError, match="weight"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_two_affixes_sharing_an_id(tmp_path) -> None:
    entry = {"id": "a", "name": "A", "hp": 1400}
    with pytest.raises(ValueError, match="share the id"):
        table_from(a_payload(affixes=[entry, dict(entry)]), tmp_path)


def test_the_loader_refuses_a_chance_that_is_not_per_mille(tmp_path) -> None:
    with pytest.raises(ValueError, match="per-mille"):
        table_from(a_payload(chance=1200), tmp_path)


def test_the_loader_refuses_a_layer_that_is_on_and_can_never_fire(tmp_path) -> None:
    """Off wearing the word on. `enabled: false` already says it, where the
    rollback is documented."""
    with pytest.raises(ValueError, match="off wearing the word on"):
        table_from(a_payload(chance=0), tmp_path)


def test_the_loader_refuses_a_layer_that_is_on_with_no_affixes(tmp_path) -> None:
    with pytest.raises(ValueError, match="declares no affixes"):
        table_from(a_payload(affixes=[]), tmp_path)


def test_the_loader_refuses_a_key_it_does_not_define(tmp_path) -> None:
    """Where a behavioural affix would arrive, and the reason it cannot: the
    schema has no word for it."""
    payload = a_payload(
        affixes=[{"id": "a", "name": "A", "hp": 1400, "summons": "grunt"}]
    )
    with pytest.raises(ValueError, match="keys this file does not define"):
        table_from(payload, tmp_path)


def test_an_affix_may_only_carry_attributes_the_game_has(tmp_path) -> None:
    payload = a_payload(
        affixes=[{"id": "a", "name": "A", "attributes": {"flight_speed": 4}}]
    )
    # `KeyError`, because this one is `Attributes.from_dict`'s refusal rather
    # than this loader's -- the schema has no word for it one layer down, which
    # is the point.
    with pytest.raises(KeyError, match="unknown attribute"):
        table_from(payload, tmp_path)


# --- the shipped table -------------------------------------------------------
def test_the_shipped_table_is_reachable_only_by_asking() -> None:
    """It ships enabled, and that is safe *because* of the seam rather than in
    spite of it: `World` defaults to `OFF`, so the file being on decides what a
    champion is and never whether anybody meets one."""
    assert not elites.table().is_off
    assert World(open_room(), BESTIARY, seed=SEED).elites is OFF


def test_every_shipped_affix_changes_something() -> None:
    for affix in elites.table().affixes:
        assert not affix.is_identity


def test_no_shipped_affix_is_gentler_than_the_monster_it_lands_on() -> None:
    """An affix that made a body *easier* would be a mark the player learns to
    hope for, which is the opposite of what it is for."""
    for affix in elites.table().affixes:
        assert affix.hp >= PER_MILLE
        assert affix.attributes.defense >= 0
        assert affix.attributes.damage >= 0
