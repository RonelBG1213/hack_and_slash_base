"""Movement, the tick, and the shape of a run. No combat here -- that is
test_combat.py; this is about whether the world moves the way it says it does.
"""

from __future__ import annotations

import pytest

from hack_and_slash import config
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import intent as intents
from hack_and_slash.game.sim import Accumulator, step
from hack_and_slash.game.world import Outcome

from .helpers import BESTIARY, HERO, add_enemy, make_world, open_room, run

RIGHT = Vec2(1, 0)
DOWN = Vec2(0, 1)


# --- walking -----------------------------------------------------------------
def test_walking_covers_exactly_speed_pixels_per_tick() -> None:
    world = make_world()
    hero = world.hero
    start = hero.pos

    run(world, 60, intents.walk(RIGHT))

    expected = HERO.speed * 60
    assert hero.pos.x - start.x == pytest.approx(expected)
    assert hero.pos.y == pytest.approx(start.y)


def test_holding_two_directions_is_not_faster_than_one() -> None:
    """The oldest bug in top-down movement: diagonals at 1.41x speed."""
    straight = make_world()
    diagonal = make_world()

    run(straight, 40, intents.walk(RIGHT))
    run(diagonal, 40, intents.walk(Vec2(1, 1)))

    straight_distance = straight.hero.pos.distance_to(make_world().hero.pos)
    diagonal_distance = diagonal.hero.pos.distance_to(make_world().hero.pos)
    assert diagonal_distance == pytest.approx(straight_distance, rel=1e-6)


def test_a_half_pushed_direction_walks_at_half_speed() -> None:
    # Clamped, not normalised -- analogue input has to survive the trip.
    world = make_world()
    start = world.hero.pos
    run(world, 10, intents.walk(Vec2(0.5, 0)))
    assert world.hero.pos.x - start.x == pytest.approx(HERO.speed * 0.5 * 10)


def test_no_input_means_no_movement() -> None:
    world = make_world()
    start = world.hero.pos
    run(world, 30)
    assert world.hero.pos == start


# --- walls -------------------------------------------------------------------
def test_walking_into_a_wall_stops_flush_against_it() -> None:
    world = make_world(open_room(20, 20))
    hero = world.hero

    run(world, 400, intents.walk(RIGHT))  # far more than enough to cross the room

    # The room's right wall starts at tile 19.
    wall_x = 19 * config.TILE
    assert hero.pos.x == pytest.approx(wall_x - hero.radius)
    assert hero.is_alive


def test_the_hero_cannot_leave_the_arena_in_any_direction() -> None:
    for direction in (Vec2(1, 0), Vec2(-1, 0), Vec2(0, 1), Vec2(0, -1), Vec2(1, 1)):
        world = make_world(open_room(14, 14))
        run(world, 400, intents.walk(direction))
        tx, ty = world.level.tile_at(world.hero.pos)
        assert world.level.is_walkable(tx, ty), f"escaped heading {direction}"


def test_sliding_along_a_wall_keeps_moving() -> None:
    # Pressed into the top wall while running right: the run should continue.
    world = make_world(open_room(20, 20))
    hero = world.hero
    run(world, 120, intents.walk(Vec2(0, -1)))  # settle against the top wall
    resting_y = hero.pos.y
    before_x = hero.pos.x

    run(world, 60, intents.walk(Vec2(1, -1)))

    assert hero.pos.x > before_x + 30, "stuck against the wall instead of sliding"
    assert hero.pos.y == pytest.approx(resting_y)


# --- bodies against bodies ---------------------------------------------------
def test_two_bodies_do_not_occupy_the_same_point() -> None:
    world = make_world()
    hero = world.hero
    enemy = add_enemy(world, "grunt", hero.pos + Vec2(2, 0))

    run(world, 20)

    gap = hero.pos.distance_to(enemy.pos)
    assert gap > (hero.radius + enemy.radius) * 0.7, "bodies collapsed into one point"


# --- the tick ----------------------------------------------------------------
def test_the_same_seed_and_the_same_inputs_give_the_same_run() -> None:
    """Determinism. Every assertion about damage in the suite rests on this."""

    def play(seed: int):
        world = make_world(seed=seed)
        add_enemy(world, "grunt", world.hero.pos + Vec2(40, 0))
        script = [intents.walk(RIGHT)] * 30 + [intents.swing_at(RIGHT)] * 60
        for command in script:
            step(world, command)
        return [(e.id, e.pos, e.hp) for e in world.entities], world.tick

    assert play(99) == play(99)


def test_events_do_not_survive_the_tick_that_made_them() -> None:
    world = make_world()
    step(world, intents.dodge_toward(RIGHT))
    assert world.events, "a dodge should announce itself"
    step(world)
    assert world.events == [], "last tick's events leaked into this one"


def test_a_run_with_enemies_left_is_still_running() -> None:
    world = make_world()
    add_enemy(world, "grunt", world.hero.pos + Vec2(200, 0))
    run(world, 10)
    assert world.outcome is Outcome.RUNNING


def test_clearing_the_arena_wins() -> None:
    world = make_world()
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(150, 0))
    enemy.hp = 0  # killed by something the sim does not need to simulate here
    run(world, 1)
    assert world.outcome is Outcome.WON


def test_the_hero_dying_loses() -> None:
    world = make_world()
    add_enemy(world, "grunt", world.hero.pos + Vec2(150, 0))
    world.hero.hp = 0
    run(world, 1)
    assert world.outcome is Outcome.LOST


def test_the_dead_are_removed_from_the_world() -> None:
    world = make_world()
    enemy = add_enemy(world, "grunt", world.hero.pos + Vec2(150, 0))
    add_enemy(world, "grunt", world.hero.pos + Vec2(160, 0))
    enemy.hp = 0
    run(world, 1)
    assert all(e.id != enemy.id for e in world.entities)


# --- the accumulator ---------------------------------------------------------
def test_the_accumulator_pays_out_whole_ticks_and_banks_the_rest() -> None:
    accumulator = Accumulator(dt=1 / 60, max_frame=0.25)
    assert accumulator.ticks_for(1 / 60) == 1
    assert accumulator.ticks_for(1 / 120) == 0  # banked, not lost
    assert accumulator.ticks_for(1 / 120) == 1  # and paid out here


def test_a_long_stall_is_clamped_rather_than_replayed() -> None:
    """Without the clamp, a five-second pause fast-forwards the player through
    three hundred ticks of a fight they never saw."""
    accumulator = Accumulator(dt=1 / 60, max_frame=0.25)
    assert accumulator.ticks_for(5.0) == 15  # 0.25s worth, not 5s worth


def test_a_steady_frame_rate_averages_the_right_number_of_ticks() -> None:
    accumulator = Accumulator(dt=1 / 60, max_frame=0.25)
    total = sum(accumulator.ticks_for(1 / 60) for _ in range(600))
    assert total == pytest.approx(600, abs=1)
