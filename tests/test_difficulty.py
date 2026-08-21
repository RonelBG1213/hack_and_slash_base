"""The difficulty tiers, and the claim the whole feature rests on.

That claim is **the default tier is arithmetically the game the recorded
balance grid was measured against** -- not approximately, not within a seed's
noise, but the same code path drawing the same dice. It is the same claim
`test_attributes.py` makes about a neutral attribute block, made the same way
and for the same reason: a dial added to a tuned game has to be provably inert
at rest, or every number in `docs/balance.md` quietly becomes a number about
some other game.

So the expensive half of this file is not the tiers. It is the identity.
"""

from __future__ import annotations

import json

import pytest

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import combat, difficulty
from hack_and_slash.game.attributes import PER_MILLE
from hack_and_slash.game.difficulty import NORMAL, Difficulty, Table
from hack_and_slash.game.entities import Faction
from hack_and_slash.game.world import Projectile, World

from .helpers import BESTIARY, add_enemy, level_with, open_room, run

SEED = 4321


def world_on(tier: Difficulty, level=None, seed: int = SEED) -> World:
    return World(level or open_room(), BESTIARY, seed=seed, difficulty=tier)


def table_from(payload: dict, tmp_path) -> Table:
    path = tmp_path / "difficulty.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return Table.load(path)


def a_payload(**overrides) -> dict:
    payload = {
        "default": "normal",
        "tiers": [
            {"id": "normal", "name": "Normal", "incoming": PER_MILLE},
            {"id": "hard", "name": "Hard", "incoming": 1500},
        ],
    }
    payload.update(overrides)
    return payload


# --- the identity ------------------------------------------------------------
def test_the_shipped_default_is_the_tier_that_changes_nothing() -> None:
    """If this fails, every recorded number in the project describes a game
    that is no longer the one a player gets by default."""
    assert difficulty.table().default.is_identity


def test_the_identity_tier_returns_the_hit_it_was_given() -> None:
    for damage in (1, 2, 7, 15, 113, 9999):
        assert NORMAL.scaled(damage) == damage


def test_a_fight_on_the_default_tier_is_identical_to_one_with_no_opinion() -> None:
    """The claim, on a real fight rather than on one method.

    A `World` built without saying anything about difficulty is what every test
    and tool that predates this feature builds. This runs that world and one
    built explicitly on the shipped default side by side and demands the same
    health, tick for tick -- so the default is not merely a multiplier of one,
    it is the same sequence of draws.
    """
    level = level_with((5, 5), [("grunt", (8, 5)), ("bowman", (12, 9))])

    silent = World(level, BESTIARY, seed=SEED)
    explicit = World(level, BESTIARY, seed=SEED, difficulty=difficulty.table().default)

    for _ in range(600):
        run(silent, 1)
        run(explicit, 1)
        assert (silent.hero is None) == (explicit.hero is None)
        if silent.hero is None:
            break
        assert silent.hero.hp == explicit.hero.hp, (
            f"tick {silent.tick}: the default tier drew a different fight from "
            f"a world that was never told difficulty exists"
        )


# --- the loader refuses ------------------------------------------------------
def test_the_loader_refuses_a_default_that_scales_damage(tmp_path) -> None:
    """The one guard that protects every recorded number in the project."""
    with pytest.raises(ValueError, match="recorded balance grid"):
        table_from(a_payload(default="hard"), tmp_path)


def test_the_loader_refuses_a_tier_nothing_can_hurt(tmp_path) -> None:
    payload = a_payload()
    payload["tiers"][1]["incoming"] = 0
    with pytest.raises(ValueError, match="cannot be hurt"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_two_tiers_sharing_an_id(tmp_path) -> None:
    payload = a_payload()
    payload["tiers"][1]["id"] = "normal"
    with pytest.raises(ValueError, match="share the id"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_a_default_that_names_no_tier(tmp_path) -> None:
    with pytest.raises(ValueError, match="which is not one of"):
        table_from(a_payload(default="nightmare"), tmp_path)


def test_an_unknown_tier_falls_back_rather_than_raising() -> None:
    """Bounded forgiveness, and the only piece of it in this loader: a renamed
    tier is a reason to carry on at the default, not to refuse somebody the run
    they were halfway through."""
    assert difficulty.table().get("a tier that never existed").is_identity


# --- every path damage arrives by --------------------------------------------
def test_a_swing_hurts_more_on_a_harder_tier() -> None:
    losses = {}
    for tier_id in ("forgiving", "normal", "relentless"):
        world = world_on(difficulty.table()[tier_id])
        hero = world.hero
        enemy = add_enemy(world, "grunt", hero.pos + Vec2(10, 0))
        before = hero.hp
        combat.apply_hit(world, enemy, hero, enemy.weapon, world.rng)
        losses[tier_id] = before - hero.hp

    assert losses["forgiving"] < losses["normal"] < losses["relentless"], losses


def test_a_shot_hurts_more_on_a_harder_tier() -> None:
    """The path that bypasses `resolve_damage` entirely -- a projectile carries
    its attacker's half from launch, so a tier applied only inside that function
    would silently leave every arrow in the game unscaled."""
    losses = {}
    for tier_id in ("forgiving", "normal", "relentless"):
        world = world_on(difficulty.table()[tier_id])
        hero = world.hero
        world.spawn_projectile(
            Projectile(
                id=world.take_projectile_id(),
                owner_id=999,
                faction=Faction.ENEMY,
                pos=hero.pos,
                velocity=Vec2(1.0, 0.0),
                radius=3.0,
                damage=20,
                knockback=1.0,
                ticks_left=60,
            )
        )
        # The broadphase is what finds the target, and it is built rather than
        # live -- a shot dropped straight into the list is invisible until it is.
        world.rebuild_index()
        before = hero.hp
        combat.resolve_projectile_hits(world)
        losses[tier_id] = before - hero.hp

    assert losses["forgiving"] < losses["normal"] < losses["relentless"], losses


def test_a_trap_hurts_more_on_a_harder_tier() -> None:
    """The third path, and the one easiest to forget: a trap has no attacker and
    no weapon, so it reaches the hero through neither of the two above."""
    losses = {}
    for tier_id in ("forgiving", "normal", "relentless"):
        world = world_on(difficulty.table()[tier_id])
        hero = world.hero
        before = hero.hp
        combat.apply_hazard(world, hero, 20, Vec2(0.0, 0.0))
        losses[tier_id] = before - hero.hp

    assert losses["forgiving"] < losses["normal"] < losses["relentless"], losses


def test_a_tier_scales_what_the_hero_takes_and_not_what_it_deals() -> None:
    """A tier is a statement about the player's mistakes, not about the enemy's
    health. If this fails, Forgiving is also a *shorter* fight, which is two
    changes wearing one name -- and every enemy's time-to-kill, the number the
    whole cadence layer is tuned against, moves with the menu."""
    taken = {}
    for tier_id in ("forgiving", "relentless"):
        world = world_on(difficulty.table()[tier_id])
        hero = world.hero
        enemy = add_enemy(world, "grunt", hero.pos + Vec2(10, 0))
        before = enemy.hp
        combat.apply_hit(world, hero, enemy, hero.weapon, world.rng)
        taken[tier_id] = before - enemy.hp

    assert taken["forgiving"] == taken["relentless"], taken


def test_no_tier_can_reduce_a_hit_below_the_floor() -> None:
    """`combat.MIN_DAMAGE` is not politeness: a hit that does nothing reads as a
    bug, and a fight where nothing can hurt anything runs to the tick limit and
    reports as a balance failure in every instrument this project has."""
    world = world_on(Difficulty(id="gentle", name="Gentle", incoming=1))
    hero = world.hero
    before = hero.hp
    combat.apply_hazard(world, hero, 1, Vec2(0.0, 0.0))
    assert before - hero.hp == combat.MIN_DAMAGE


def test_an_enemy_is_never_scaled_whatever_the_tier() -> None:
    """`combat.incoming` is hero-only, and it is worth pinning directly as well
    as through a fight: the check is one `if` and it is the difference between a
    difficulty and a global damage multiplier."""
    world = world_on(difficulty.table()["relentless"])
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(30, 0))
    assert combat.incoming(world, enemy, 10) == 10
    assert combat.incoming(world, world.hero, 10) == 13
