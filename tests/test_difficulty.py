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
from hack_and_slash.game.attributes import NEUTRAL, PER_MILLE
from hack_and_slash.game.difficulty import (
    NEUTRAL_ENEMIES,
    NORMAL,
    Difficulty,
    Enemies,
    Table,
)
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


def test_a_tier_never_scales_what_the_hero_deals() -> None:
    """The half of the old rule that survived, and it is the half worth having.

    A tier moves what an enemy *is* -- its health, its speed, how far it sees,
    how often it swings, how often it slips a blow. It does not move what a
    greatsword is worth, because that is a property of the greatsword and of
    the class that carries it, and a difficulty that quietly buffed the hero
    would make every recorded per-class number a number about something else.

    Asserted on `combat.dealt`, which is where the enemy-side multiplier lives,
    rather than on a grunt's health delta. The old version measured the delta,
    and the day enemies gained evasion that became a test of whether one seeded
    die happened to come up -- it passed, and it would have gone on passing
    while meaning nothing.
    """
    for tier_id in ("forgiving", "normal", "relentless", "nightmare"):
        world = world_on(difficulty.table()[tier_id])
        hero = world.hero
        assert combat.dealt(world, hero, 17) == 17, (
            f"the hero's own output moved on {tier_id}"
        )


def test_a_harder_tier_makes_the_monsters_hit_harder() -> None:
    """The other side of `dealt`.

    Built here rather than read off a shipped tier, deliberately: **no tier
    currently ships with `damage` set at all.** It was drafted on Nightmare at
    1100 and taken back out when the first sweep showed the dials compounding
    far harder than expected -- 15 of 20 stages became unclearable. The
    mechanism has to keep working for the day somebody turns it back on, and a
    test that read the shipped content would have quietly stopped checking
    anything on the day it was switched off.
    """
    quiet = world_on(difficulty.table()["normal"])
    loud = world_on(Difficulty(id="loud", name="Loud", enemies=Enemies(damage=1400)))

    enemy_quiet = add_enemy(quiet, "grunt", quiet.hero.pos + Vec2(40, 0))
    enemy_loud = add_enemy(loud, "grunt", loud.hero.pos + Vec2(40, 0))

    assert combat.dealt(quiet, enemy_quiet, 100) == 100
    assert combat.dealt(loud, enemy_loud, 100) == 140
    assert combat.dealt(loud, loud.hero, 100) == 100, "the hero was scaled"


def test_no_tier_can_reduce_a_hit_below_the_floor() -> None:
    """`combat.MIN_DAMAGE` is not politeness: a hit that does nothing reads as a
    bug, and a fight where nothing can hurt anything runs to the tick limit and
    reports as a balance failure in every instrument this project has."""
    world = world_on(Difficulty(id="gentle", name="Gentle", incoming=1))
    hero = world.hero
    before = hero.hp
    combat.apply_hazard(world, hero, 1, Vec2(0.0, 0.0))
    assert before - hero.hp == combat.MIN_DAMAGE


def test_incoming_is_hero_only_whatever_the_tier() -> None:
    """`combat.incoming` is hero-only, and it is worth pinning directly as well
    as through a fight: the check is one `if` and it is the difference between a
    difficulty and a global damage multiplier.

    Named for `incoming` rather than for enemies, which is what it used to be
    called. Enemies *are* scaled now -- through their attribute block and
    through `combat.dealt` -- so a test called "an enemy is never scaled" would
    be claiming something the rest of this file spends its time disproving.
    The narrow claim is still true and still worth a test.
    """
    tier = difficulty.table()["relentless"]
    world = world_on(tier)
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(30, 0))

    # Derived from the tier rather than written out, so re-tuning
    # `data/difficulty.json` cannot break a test that is about the `if` rather
    # than about the number. It was `== 13` and broke on the first re-tune.
    assert combat.incoming(world, enemy, 100) == 100
    assert combat.incoming(world, world.hero, 100) == tier.scaled(100)
    assert tier.scaled(100) > 100, "Hard stopped being harder than Normal"


# --- the monsters ------------------------------------------------------------
def test_the_shipped_default_leaves_every_monster_alone() -> None:
    """The other half of "the default changes nothing", and the half that did
    not exist before the monster dials. `Table.load` refuses a default that is
    not the identity, and `Difficulty.is_identity` now asks about both halves --
    so this is really a test that widening that property was not forgotten."""
    assert difficulty.table().default.enemies.is_identity
    assert difficulty.table().default.is_identity


def test_every_enemy_dial_defaults_to_its_own_identity() -> None:
    """`Enemies.is_identity` is derived by comparing each field to its declared
    default, so the defaults *are* the identities and the two cannot drift.

    Spelled out here anyway, because the derivation would be vacuously true if
    somebody declared a dial whose default was not neutral -- five of these are
    multipliers at 1000 and `evasion` is additive at 0, and that asymmetry is
    the thing most likely to be got wrong.
    """
    assert NEUTRAL_ENEMIES.is_identity
    for name in ("hp", "damage", "speed", "aggro", "cadence"):
        assert getattr(NEUTRAL_ENEMIES, name) == PER_MILLE, name
    assert NEUTRAL_ENEMIES.evasion == 0

    for name in ("hp", "damage", "speed", "aggro", "cadence"):
        assert not Enemies(**{name: 900}).is_identity, name
    assert not Enemies(evasion=1).is_identity


def test_the_identity_tier_hands_back_the_shared_neutral_block() -> None:
    """By identity, not by equality. `World._populate` tests `is not NEUTRAL` to
    decide whether to touch a body at all, so an equal-but-distinct block would
    put a bonus on every enemy in a fight that did not need one -- and quietly
    end the claim that a Normal fight is untouched."""
    grunt = BESTIARY["grunt"]
    assert NEUTRAL_ENEMIES.block_for(grunt) is NEUTRAL

    # A tier that moves only cadence still touches no body, which is a
    # different question from `is_identity` and is why `block_for` rebuilds the
    # answer rather than reading that property.
    assert Enemies(cadence=700).block_for(grunt) is NEUTRAL


def test_a_monster_is_built_to_the_tier_it_is_fought_on() -> None:
    """The spawn path, end to end: health, speed and the evasion that is the
    whole of the defence, all through the attribute layer that already existed."""
    plain = world_on(difficulty.table()["normal"], level=level_with((3, 3), [("grunt", (8, 3))]))
    harsh = world_on(difficulty.table()["nightmare"], level=level_with((3, 3), [("grunt", (8, 3))]))

    quiet = next(e for e in plain.entities if not e.is_hero)
    loud = next(e for e in harsh.entities if not e.is_hero)

    assert quiet.bonus is NEUTRAL, "a Normal grunt was given a stat of its own"
    assert quiet.attrs.evasion == 0

    assert loud.max_hp > quiet.max_hp
    assert loud.hp == loud.max_hp, "spawned wounded -- the refill was forgotten"
    assert loud.attrs.evasion > 0
    assert loud.attrs.move_speed > 0


def test_the_hero_is_never_given_the_monster_block() -> None:
    """It is applied in the enemy loop, and the hero has its own block three
    lines above carrying what the run earned. Crossing the two would hand the
    player the difficulty they chose to be punished by."""
    world = world_on(difficulty.table()["nightmare"])
    assert world.hero.bonus is NEUTRAL
    assert world.hero.attrs.evasion == 0


def test_cadence_scales_the_pause_and_never_the_telegraph() -> None:
    """A tier may make an enemy attack more often. It may not make an attack
    less readable -- the windup is the tell, it is what makes a blow dodgeable,
    and `docs/design.md` promises a player can learn it."""
    from hack_and_slash.game import ai

    world = world_on(difficulty.table()["nightmare"])
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(40, 0))

    plain = ai.cooldown_for(enemy)
    hurried = ai.cooldown_for(enemy, difficulty.table()["nightmare"])

    assert hurried < plain, "the tier did not quicken the cadence"
    assert hurried >= enemy.weapon.total_ticks, (
        "the tier ate into the telegraph, not just the pause"
    )
    assert ai.cooldown_for(enemy, NORMAL) == plain


def test_aggro_widens_with_the_tier() -> None:
    """The dial aimed at disengaging, which the reaction ladder says is the
    thing that actually decides a run."""
    from hack_and_slash.game import ai

    plain = world_on(difficulty.table()["normal"])
    harsh = world_on(difficulty.table()["nightmare"])
    grunt = BESTIARY["grunt"]

    quiet = add_enemy(plain, "grunt", plain.hero.pos + Vec2(40, 0))
    loud = add_enemy(harsh, "grunt", harsh.hero.pos + Vec2(40, 0))

    assert ai.aggro_of(plain, quiet) == grunt.aggro
    assert ai.aggro_of(harsh, loud) > grunt.aggro


def test_a_monster_out_past_its_scaled_aggro_still_sleeps() -> None:
    """The widening has to actually reach the cutoff, not just the helper."""
    from hack_and_slash.game import ai
    from hack_and_slash.game.intent import NOTHING

    world = world_on(difficulty.table()["nightmare"])
    grunt = BESTIARY["grunt"]
    far = add_enemy(world, "grunt", world.hero.pos + Vec2(grunt.aggro * 2, 0))
    near = add_enemy(world, "grunt", world.hero.pos + Vec2(grunt.aggro * 1.1, 0))

    assert ai.decide(world, far) is NOTHING
    assert ai.decide(world, near) is not NOTHING, (
        "a tier that widens aggro did not wake something inside the wider radius"
    )


def test_the_gentlest_tier_is_file_order_and_not_the_softest_number() -> None:
    """The ceiling bracket asks this question, and with seven dials there is no
    single number to minimise. A tier could halve incoming damage and double
    enemy health; picking the softest `incoming` would then hand that bracket
    the harder fight while looking perfectly correct."""
    table = difficulty.table()
    assert table.gentlest is table.tiers[0]

    contrived = Table(
        tiers=(
            Difficulty(id="soft", name="Soft", incoming=900,
                       enemies=Enemies(hp=2000)),
            Difficulty(id="normal", name="Normal"),
        ),
        default_id="normal",
    )
    assert contrived.gentlest.id == "soft"


# --- what the loader refuses -------------------------------------------------
def test_the_loader_refuses_an_unknown_enemy_dial(tmp_path) -> None:
    """Forgiving everywhere else, strict here, exactly as `Attributes.from_dict`
    is: a misspelled `agro` sitting silently at the identity is the kind of
    thing that gets tuned around for an afternoon before anybody reads the JSON."""
    payload = a_payload()
    payload["tiers"][1]["enemies"] = {"agro": 1200}
    with pytest.raises(ValueError, match="unknown enemy dial"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_a_monster_with_none_of_something(tmp_path) -> None:
    """Zero is not a gentler setting. No health is dead on spawn, no speed is a
    statue, no aggro never wakes -- each leaves a stage that cannot be cleared,
    which every instrument in this project reports as a balance failure."""
    for dial in ("hp", "speed", "aggro"):
        payload = a_payload()
        payload["tiers"][1]["enemies"] = {dial: 0}
        with pytest.raises(ValueError, match="cannot be finished"):
            table_from(payload, tmp_path)


def test_the_loader_refuses_a_monster_nothing_can_hit(tmp_path) -> None:
    """The mirror of the hero who cannot be hurt, and refused for the same
    reason: the room is never cleared, the stage runs to the tick limit, and it
    reports as a balance failure rather than as the setting it is."""
    payload = a_payload()
    payload["tiers"][1]["enemies"] = {"evasion": PER_MILLE}
    with pytest.raises(ValueError, match="runs the stage out"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_a_default_that_touches_the_monsters(tmp_path) -> None:
    """The guard that protects every recorded number in the project, on the half
    of it that is new. A default tier quietly making every enemy tougher would
    be the same failure as one scaling damage, and it has to fail the same way."""
    payload = a_payload()
    payload["tiers"][0]["enemies"] = {"hp": 1200}
    with pytest.raises(ValueError, match="recorded balance grid"):
        table_from(payload, tmp_path)
