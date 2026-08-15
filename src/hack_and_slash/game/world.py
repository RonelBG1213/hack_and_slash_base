"""Everything a run consists of, in one object.

`World` owns state and answers questions about it. It does not advance time --
that is `sim.step`. The split is what makes the sim testable: a test builds a
world, steps it a known number of ticks, and asserts on what it finds, with no
window, no clock and no input device anywhere in the picture.

Randomness lives here, in *two* seeded `Random`s, and the split matters. `rng`
is the fight: damage rolls, and nothing else. `loot_rng` is what a kill leaves
behind. Both are derived from the one seed, so a run still replays exactly --
but a loot roll can never shift the sequence a damage roll draws from, which is
what lets the loot layer be added to a tuned game without moving a single
recorded number. `test_loot.py` asserts that rather than trusting it.

Nothing anywhere else may call the module-level `random` functions; if it did, a
seeded run would stop replaying and every damage assertion in the suite would
become a coin toss.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from ..core.level import Level
from ..core.spatial import SpatialHash
from ..core.vec2 import Vec2
from .entities import DEFAULT_HERO, Bestiary, Entity, Faction, spawn
from .events import Event
from .loot import Pickup

#: Offset that separates the loot stream from the combat one. Any constant would
#: do; what matters is that the two generators never see the same seed, because
#: two `Random`s seeded identically produce identical sequences and the whole
#: point of the split would be lost.
LOOT_STREAM = 0x10071


@dataclass(frozen=True)
class Purse:
    """What the hero is carrying into this stage, from the run above it.

    Two numbers that the world needs and cannot work out for itself: which floor
    this is, and how much extra its drops are worth. Passed as one thing so that
    a third does not mean another positional argument on a constructor with six
    of them already.
    """

    floor: int = 1
    gold_find: float = 0.0


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
    def __init__(
        self,
        level: Level,
        bestiary: Bestiary,
        seed: int = 0,
        carry_hp: int | None = None,
        hero_type_id: str = DEFAULT_HERO,
        purse: Purse | None = None,
    ) -> None:
        """One stage in progress.

        `carry_hp` is the hero's health on arrival -- the whole of the carry-over
        mechanism between stages. None means a fresh hero at full health, which
        is what a standalone fight and every test that predates the run layer
        expect.

        `hero_type_id` is which class is being played. It defaults, so a world
        built without an opinion is still a real fight -- which is what keeps
        every test and tool that predates classes working unchanged.

        `purse` is what the run above knows and this world does not: which floor
        it is and how much gold find has been bought. It defaults to floor one
        with no bonus, which is a perfectly coherent standalone fight -- so
        every tool and test that predates loot goes on working untouched.
        """
        self.level = level
        self.bestiary = bestiary
        self.rng = random.Random(seed)
        self.seed = seed
        self.carry_hp = carry_hp
        self.hero_type_id = hero_type_id
        self.purse = purse or Purse()

        #: Separate from `rng` on purpose. See the module docstring: this is the
        #: guarantee that adding loot to a tuned game moved nothing.
        self.loot_rng = random.Random(seed ^ LOOT_STREAM)

        self.tick = 0
        self.outcome = Outcome.RUNNING

        self.entities: list[Entity] = []
        self.projectiles: list[Projectile] = []
        self.events: list[Event] = []

        #: Loot on the floor, and what has been picked up off it. Kept out of
        #: `entities` deliberately -- a pickup has no health, no faction and no
        #: brain, and putting one in that list would hand it to the broadphase,
        #: the separation pass and every AI brain in the game.
        self.pickups: list[Pickup] = []
        self.gold = 0

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
        hero_type = self.bestiary[self.hero_type_id]
        hero = spawn(self._take_id(), hero_type, self.level.tile_center(*self.level.hero_spawn))

        if self.carry_hp is not None:
            # Clamped at both ends. Above the maximum would turn a generous heal
            # into permanent bonus health; at or below zero would start the stage
            # already lost, with the death playing out before the player has
            # touched anything.
            hero.hp = max(1, min(self.carry_hp, hero_type.hp))

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
