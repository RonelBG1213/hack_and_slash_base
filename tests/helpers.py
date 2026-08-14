"""Building small worlds to run fights in.

Every sim test wants the same thing: a known arena, a hero at a known spot,
enemies exactly where the test put them, and a seed. Real content is used
throughout -- `data/entities.json` and `data/weapons.json`, not invented stats --
so a test failing after a tuning change is telling the truth about the game.
"""

from __future__ import annotations

from contextlib import contextmanager

from hack_and_slash import config
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game.entities import (
    DEFAULT_HERO,
    Bestiary,
    Entity,
    EntityType,
    load_bestiary,
    spawn,
)
from hack_and_slash.game.world import World

#: Loaded once. The content files do not change during a run of the suite, and
#: re-reading them for every test is the slowest thing in it.
BESTIARY: Bestiary = load_bestiary(config.ENTITIES_DATA, config.WEAPONS_DATA)

#: The class a test fights as unless it names another one. There are five, but a
#: test about whether a cone hits what it is pointed at wants *a* hero rather
#: than an opinion about which -- and the one it gets is the same one the
#: campaign's recorded numbers were measured on, so a test and the balance
#: harness are always talking about the same body.
HERO: EntityType = BESTIARY[DEFAULT_HERO]


def open_room(width: int = 20, height: int = 20) -> Level:
    """A walled box with nothing in it. Somewhere to fight without a pillar
    turning a test about combat into a test about pathing."""
    rows = []
    for y in range(height):
        if y in (0, height - 1):
            rows.append("#" * width)
        else:
            rows.append("#" + "." * (width - 2) + "#")
    return Level(
        name="test room",
        rows=tuple(rows),
        hero_spawn=(width // 2, height // 2),
        enemy_spawns=(),
        tile=config.TILE,
    )


def make_world(level: Level | None = None, seed: int = 1234) -> World:
    """A world with a hero and no enemies. Add what the test needs."""
    return World(level or open_room(), BESTIARY, seed=seed)


def add_enemy(world: World, type_id: str, pos: Vec2) -> Entity:
    """Place an enemy at an exact pixel position, not a tile.

    Tests about reach and arcs need control finer than a tile gives.
    """
    enemy = spawn(world._take_id(), BESTIARY[type_id], pos)
    world.entities.append(enemy)
    return enemy


def level_with(hero_tile: tuple[int, int], enemies: list[tuple[str, tuple[int, int]]]) -> Level:
    room = open_room()
    return Level(
        name=room.name,
        rows=room.rows,
        hero_spawn=hero_tile,
        enemy_spawns=tuple(EnemySpawn(type_id, tile) for type_id, tile in enemies),
        tile=room.tile,
    )


@contextmanager
def enemies_idle():
    """Switch the enemy brains off for the duration of a block.

    Tests about reach, arcs and i-frame windows need the target to stay where it
    was put. Leaving the AI on turns a test about the cone into a test about
    whether a grunt happened to step forward, and the failure message would tell
    you nothing about either.
    """
    from hack_and_slash.game import ai, sim
    from hack_and_slash.game.intent import NOTHING as IDLE

    original = ai.decide
    sim.ai.decide = lambda world, entity: IDLE
    try:
        yield
    finally:
        sim.ai.decide = original


def run(world: World, ticks: int, intent=None) -> None:
    """Step the world, holding one intent the whole time."""
    from hack_and_slash.game.intent import NOTHING
    from hack_and_slash.game.sim import step

    for _ in range(ticks):
        step(world, intent if intent is not None else NOTHING)


def entity_by_id(world: World, entity_id: int) -> Entity | None:
    for entity in world.entities:
        if entity.id == entity_id:
            return entity
    return None
