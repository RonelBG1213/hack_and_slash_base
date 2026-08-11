"""Everything a run consists of, in one object.

`World` owns state and answers questions about it. It does not advance time --
that is `sim.step`. The split is what makes the sim testable: a test builds a
world, steps it a known number of ticks, and asserts on what it finds, with no
window, no clock and no input device anywhere in the picture.

Randomness lives here, in one seeded `Random`. Nothing anywhere else may call
the module-level `random` functions; if it did, a seeded run would stop
replaying and every damage assertion in the suite would become a coin toss.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from ..core.level import Level
from ..core.spatial import SpatialHash
from ..core.vec2 import Vec2
from .entities import Bestiary, Entity, Faction, spawn
from .events import Event


class Outcome(str, Enum):
    RUNNING = "running"
    WON = "won"
    LOST = "lost"


@dataclass
class Projectile:
    id: int
    owner_id: int
    faction: Faction
    pos: Vec2
    velocity: Vec2
    radius: float
    damage: int
    knockback: float
    ticks_left: int


class World:
    def __init__(self, level: Level, bestiary: Bestiary, seed: int = 0) -> None:
        self.level = level
        self.bestiary = bestiary
        self.rng = random.Random(seed)
        self.seed = seed

        self.tick = 0
        self.outcome = Outcome.RUNNING

        self.entities: list[Entity] = []
        self.projectiles: list[Projectile] = []
        self.events: list[Event] = []

        # Cell a little wider than the longest reach in the game, so a swing
        # query sweeps four buckets at worst.
        self.grid: SpatialHash = SpatialHash(cell=48)

        self._next_id = 0
        self.hero_id = -1

        #: Ticks the presentation layer should freeze on. The sim decrements it
        #: but never acts on it -- see events.py.
        self.hitstop = 0

        self._populate()

    # --- setup ---------------------------------------------------------------
    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _populate(self) -> None:
        hero_type = self.bestiary["hero"]
        hero = spawn(self._take_id(), hero_type, self.level.tile_center(*self.level.hero_spawn))
        self.hero_id = hero.id
        self.entities.append(hero)

        for entry in self.level.enemy_spawns:
            enemy_type = self.bestiary[entry.type_id]
            self.entities.append(
                spawn(self._take_id(), enemy_type, self.level.tile_center(*entry.tile))
            )

    # --- queries -------------------------------------------------------------
    @property
    def hero(self) -> Entity | None:
        """None once the hero is dead and culled. Callers must cope -- a run
        that has been lost still gets stepped while the death plays out."""
        for entity in self.entities:
            if entity.id == self.hero_id:
                return entity
        return None

    def enemies(self) -> list[Entity]:
        return [e for e in self.entities if e.type.faction is Faction.ENEMY and e.is_alive]

    def is_solid(self, tx: int, ty: int) -> bool:
        return self.level.is_solid(tx, ty)

    def nearby(self, pos: Vec2, radius: float):
        """Broadphase neighbours. Candidates, not hits -- test them properly."""
        return self.grid.query(pos, radius)

    def rebuild_index(self) -> None:
        self.grid.rebuild(self.entities, lambda entity: entity.pos)

    # --- output --------------------------------------------------------------
    def emit(self, event: Event) -> None:
        self.events.append(event)

    def drain_events(self) -> list[Event]:
        """Hand over this tick's events and forget them.

        The presentation layer must call this every frame. If it does not, the
        list grows for the length of the run -- so the sim clears it at the top
        of each step regardless, and an uncollected event is simply lost rather
        than leaked.
        """
        drained = self.events
        self.events = []
        return drained

    def spawn_projectile(self, projectile: Projectile) -> None:
        self.projectiles.append(projectile)

    def take_projectile_id(self) -> int:
        return self._take_id()
