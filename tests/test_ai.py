"""The three enemy brains, and the arrows one of them shoots.

Each brain exists to ask the player a different question. These tests check that
the question actually gets asked -- a charger that homes in mid-dash, or an
archer that shoots through a pillar, is not a harder enemy, it is a broken one.
"""

from __future__ import annotations

from hack_and_slash.core.level import Level
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import ai, intent as intents
from hack_and_slash.game.entities import ActionState
from hack_and_slash.game.events import EventKind
from hack_and_slash.game.sim import step

from .helpers import BESTIARY, add_enemy, make_world, open_room, run

GRUNT = BESTIARY["grunt"]
CHARGER = BESTIARY["charger"]
ARCHER = BESTIARY["archer"]
GORE = BESTIARY.weapons["gore"]
BOW = BESTIARY.weapons["arrow"]


def big_room():
    """Wide enough for an archer to keep its distance in."""
    return open_room(40, 20)


# --- the chaser --------------------------------------------------------------
def test_a_chaser_closes_the_distance() -> None:
    world = make_world(big_room())
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(120, 0))
    before = enemy.pos.distance_to(world.hero.pos)

    run(world, 40)

    assert enemy.pos.distance_to(world.hero.pos) < before - 20


def test_a_chaser_swings_once_it_is_close_enough() -> None:
    world = make_world(big_room())
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(120, 0))

    swung = False
    for _ in range(240):
        step(world)
        swung = swung or any(
            e.kind is EventKind.SWING and e.entity_id == enemy.id for e in world.events
        )
    assert swung, "walked all the way in and never attacked"


def test_a_chaser_ignores_a_hero_beyond_its_aggro_range() -> None:
    world = make_world(open_room(60, 20))
    far = world.hero.pos + Vec2(GRUNT.aggro + 60, 0)
    enemy = add_enemy(world, "grunt", far)

    run(world, 30)

    assert enemy.pos == far, "noticed the hero from outside its aggro range"


def test_a_chaser_keeps_walking_during_its_own_windup() -> None:
    # One that stops dead the moment it commits is trivially backed away from.
    world = make_world(big_room())
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(40, 0))

    for _ in range(120):
        step(world)
        if enemy.state is ActionState.WINDUP:
            break
    assert enemy.state is ActionState.WINDUP, "never committed to a swing"

    before = enemy.pos.x
    run(world, 5)
    assert enemy.pos.x < before, "froze the instant it decided to swing"


# --- the charger -------------------------------------------------------------
def test_a_charger_telegraphs_for_its_whole_windup_before_moving() -> None:
    """The tell has to be worth something.

    A charge that starts moving during its windup gives the player less warning
    than the data promises, and the whole enemy stops being sidesteppable.
    """
    world = make_world(big_room())
    enemy = add_enemy(world, "charger", world.hero.pos + Vec2(100, 0))

    run(world, 1)
    assert enemy.state is ActionState.WINDUP
    start = enemy.pos

    run(world, GORE.windup - 2)
    assert enemy.pos.distance_to(start) < 1.0, "crept forward during the telegraph"


def test_a_charger_commits_to_the_direction_it_telegraphed() -> None:
    """It locks its heading when the tell starts, not when the dash fires.

    Lock it at the end and the telegraph tells you nothing you can act on: the
    charge would simply follow you wherever you moved during it.
    """
    world = make_world(big_room())
    hero = world.hero
    enemy = add_enemy(world, "charger", hero.pos + Vec2(110, 0))

    run(world, 1)
    committed = enemy.dash_dir
    assert not committed.is_zero()

    # Step well out of the line while it winds up.
    run(world, GORE.windup, intents.walk(Vec2(0, -1)))
    assert enemy.dash_dir == committed, "re-aimed after committing"

    run(world, 10)
    assert enemy.state is ActionState.ACTIVE
    assert enemy.dash_dir == committed


def test_a_charger_dashes_faster_than_it_walks() -> None:
    world = make_world(big_room())
    enemy = add_enemy(world, "charger", world.hero.pos + Vec2(110, 0))

    run(world, GORE.windup + 1)
    assert enemy.state is ActionState.ACTIVE

    before = enemy.pos
    run(world, 5)
    travelled = enemy.pos.distance_to(before)
    assert travelled > CHARGER.speed * 5 * 1.5, "the charge is no faster than a walk"


def test_sidestepping_a_charge_avoids_it() -> None:
    """The whole point of the enemy: it is a positioning problem, not a damage tax."""
    world = make_world(big_room())
    hero = world.hero
    add_enemy(world, "charger", hero.pos + Vec2(120, 0))

    # Walk perpendicular to the charge for its entire duration.
    run(world, GORE.windup + GORE.active + 4, intents.walk(Vec2(0, -1)))

    assert hero.hp == hero.type.hp, "could not get out of the way"


# --- the archer --------------------------------------------------------------
def test_an_archer_looses_an_arrow_after_its_windup() -> None:
    world = make_world(big_room())
    hero = world.hero
    add_enemy(world, "archer", hero.pos + Vec2(ARCHER.preferred_range - 10, 0))

    run(world, BOW.windup + 2)
    assert world.projectiles, "wound up and never fired"


def test_an_arrow_flies_toward_the_hero_and_deals_damage() -> None:
    world = make_world(big_room())
    hero = world.hero
    add_enemy(world, "archer", hero.pos + Vec2(ARCHER.preferred_range - 10, 0))

    for _ in range(400):
        step(world)
        if hero.hp < hero.type.hp:
            break
    assert hero.hp < hero.type.hp, "never landed a shot on a stationary target"


def test_an_arrow_stops_at_a_wall_instead_of_passing_through() -> None:
    world = make_world(big_room())
    hero = world.hero
    archer = add_enemy(world, "archer", hero.pos + Vec2(60, 0))
    archer.facing = 0.0

    from hack_and_slash.game import actions

    actions.begin_attack(archer)
    run(world, BOW.windup + 1)
    assert world.projectiles
    # Follow this specific arrow -- the archer keeps shooting, so "are there any
    # projectiles left" would answer a different question entirely.
    tracked = world.projectiles[0].id

    # Long enough to cross the whole room several times over.
    run(world, 600)
    assert all(shot.id != tracked for shot in world.projectiles), (
        "an arrow is still in flight inside a sealed room"
    )


def test_a_fast_projectile_cannot_skip_over_a_wall() -> None:
    """The same mistake the substepped entity movement already fixed.

    Checking only where a projectile *landed* misses everything it flew over.
    Arrows get away with it today purely because 2.7px per tick cannot clear a
    16px tile -- the correctness rests on one number in weapons.json rather than
    on the code. Give a crossbow enemy a fast bolt and walls stop working, with
    no error to say so.

    The speed here is deliberately larger than a tile, which is the case a
    destination-only check cannot handle.
    """
    from hack_and_slash.game.world import Projectile

    # An interior wall with open floor on *both* sides. That is the shape that
    # exposes the bug: a destination-only check needs somewhere legal to land on
    # the far side, and the outer border of a plain room offers none.
    room = open_room(30, 24)
    rows = list(room.rows)
    rows[10] = "#" * 30
    level = Level(
        name="barrier", rows=tuple(rows), hero_spawn=(2, 2), enemy_spawns=(), tile=16
    )

    world = make_world(level)
    world.spawn_projectile(
        Projectile(
            id=world.take_projectile_id(),
            owner_id=999,
            faction=ARCHER.faction,
            pos=level.tile_center(15, 5),
            velocity=Vec2(0, 60),  # nearly four tiles in a single tick
            radius=2.5,
            damage=1,
            knockback=0.0,
            ticks_left=90,
        )
    )
    tracked = world.projectiles[0].id

    run(world, 3)

    survivor = next((s for s in world.projectiles if s.id == tracked), None)
    assert survivor is None or survivor.pos.y < 10 * 16, (
        f"a projectile at {survivor.pos if survivor else None} is past a wall it "
        "never touched -- its path was never swept, only its landing spot checked"
    )


def test_an_arrow_expires_rather_than_flying_forever() -> None:
    """A lifetime, not just a wall, ends an arrow -- otherwise a shot down a long
    empty corridor is a projectile the sim carries for the rest of the run."""
    world = make_world(open_room(60, 20))
    archer = add_enemy(world, "archer", world.hero.pos + Vec2(40, 0))
    archer.facing = 0.0

    from hack_and_slash.game import actions

    actions.begin_attack(archer)
    run(world, BOW.windup + 1)
    tracked = world.projectiles[0]
    assert tracked.ticks_left <= BOW.projectile_lifetime

    run(world, BOW.projectile_lifetime + 2)
    assert all(shot.id != tracked.id for shot in world.projectiles)


def test_an_archer_backs_away_when_the_hero_closes() -> None:
    world = make_world(big_room())
    hero = world.hero
    archer = add_enemy(world, "archer", hero.pos + Vec2(ARCHER.retreat_range - 20, 0))
    before = archer.pos.x

    run(world, 20)

    assert archer.pos.x > before + 3, "stood still while being closed down"


def test_an_archer_will_not_shoot_through_a_pillar() -> None:
    """Cover is the answer to an archer. If it shoots through walls, there is none."""
    rows = list(open_room(30, 12).rows)
    # A three-tile column of wall between the two of them.
    for y in (4, 5, 6):
        row = rows[y]
        rows[y] = row[:12] + "###" + row[15:]

    level = Level(
        name="cover", rows=tuple(rows), hero_spawn=(5, 5), enemy_spawns=(), tile=16
    )
    world = make_world(level)
    archer = add_enemy(world, "archer", level.tile_center(22, 5))
    archer.facing = 3.14159  # pointed straight at the hero

    fired = 0
    for _ in range(BOW.windup + 4):
        step(world)
        fired += sum(1 for e in world.events if e.kind is EventKind.SHOOT)
    assert fired == 0, "shot straight through a wall"


# --- brains in general -------------------------------------------------------
def test_a_brain_does_nothing_once_the_hero_is_gone() -> None:
    world = make_world(big_room())
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(50, 0))
    world.hero.hp = 0
    run(world, 1)  # culls the hero
    assert ai.decide(world, enemy).move.is_zero()


def test_enemies_do_not_attack_faster_than_their_cooldown_allows() -> None:
    world = make_world(big_room())
    hero = world.hero
    enemy = add_enemy(world, "grunt", hero.pos + Vec2(20, 0))

    swings = 0
    ticks = 300
    for _ in range(ticks):
        step(world)
        swings += sum(
            1 for e in world.events
            if e.kind is EventKind.SWING and e.entity_id == enemy.id
        )
    ceiling = ticks / ai.cooldown_for(enemy) + 1
    assert swings <= ceiling, f"{swings} swings in {ticks} ticks is faster than allowed"
