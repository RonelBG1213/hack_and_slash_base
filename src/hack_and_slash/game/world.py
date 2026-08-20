"""Everything a run consists of, in one object.

`World` owns state and answers questions about it. It does not advance time --
that is `sim.step`. The split is what makes the sim testable: a test builds a
world, steps it a known number of ticks, and asserts on what it finds, with no
window, no clock and no input device anywhere in the picture.

Randomness lives here, in *four* seeded `Random`s, and the split matters. `rng`
is the fight: damage rolls, and nothing else. `loot_rng` is what a kill leaves
behind. `attr_rng` is crit and evasion. `hazard_rng` is where the traps stand.
All four are derived from the one seed, so a run still replays exactly -- but
neither a loot roll nor a crit roll can shift the sequence a damage roll draws
from, which is what let the loot layer and then the attribute layer each be added
to a tuned game without moving a single recorded number. `test_loot.py` and
`test_attributes.py` assert that rather than trusting it.

`hazard_rng` is the odd one and worth reading twice. It is drawn from **once**,
while this object is being constructed, and never again for the length of the
stage -- everything a trap does afterwards is arithmetic on `world.tick`. So the
hazard layer needed the offset for placement and then deliberately arranged to
need nothing else, because a die rolled on a *measured* tick is the one thing
none of these splits can protect against.

The rule for the next one: **a new subsystem that rolls dice gets its own
offset.** Two generators seeded identically are one generator, so the offset is
the entire mechanism.

Nothing anywhere else may call the module-level `random` functions; if it did, a
seeded run would stop replaying and every damage assertion in the suite would
become a coin toss.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from ..core.level import Direction, Level, PropKind, RoomKind
from ..core.spatial import SpatialHash
from ..core.vec2 import Vec2
from . import hazards
from .attributes import NEUTRAL, Attributes
from .entities import DEFAULT_HERO, Bestiary, Entity, Faction, spawn
from .events import Event
from .loot import Pickup

#: Offset that separates the loot stream from the combat one. Any constant would
#: do; what matters is that the two generators never see the same seed, because
#: two `Random`s seeded identically produce identical sequences and the whole
#: point of the split would be lost.
LOOT_STREAM = 0x10071

#: The same trick a third time, for the attribute layer. Crit and evasion are
#: dice, and a die rolled from `rng` would shift every damage roll after the
#: first hit -- moving all 280 cells of the recorded class-by-stage grids
#: without one balance number changing and without one assertion firing.
#:
#: `test_attribute_rolls_do_not_disturb_the_damage_stream` is the guard, and it
#: was written before the code it guards, the same way the loot one was.
ATTR_STREAM = 0x2A771


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
class RoomProp:
    """A fixture standing in a reward room: where it is, and whether it is spent.

    Built from `Level.props` the way entities are built from `EnemySpawn`, and
    kept out of `entities` for the reason `pickups` is: a fountain has no
    health, no faction and no brain, and putting one in that list would hand it
    to the broadphase, the separation pass and every AI brain in the game.

    `taken` is on the live prop rather than on a set of indices somewhere else,
    so the thing that knows it has been used is the thing itself -- and the
    renderer can draw a spent fountain differently without asking anybody.
    """

    kind: PropKind
    pos: Vec2
    leads_to: RoomKind | None = None

    #: Which wall this door stands against, or None for a fixture. Carried down
    #: from `Prop` untouched: the sim reports it upward on the tick the door is
    #: walked into, and the run turns it into the wall the *next* room is
    #: entered by. `sim` never asks what it means.
    wall: Direction | None = None

    taken: bool = False

    @property
    def is_door(self) -> bool:
        return self.kind is PropKind.DOOR


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

    #: Whether the attacker's crit fired when this was loosed. Carried on the
    #: shot because the roll happens at launch -- see `resolve_projectile_hits`
    #: for why it cannot happen at impact -- and read only to emit the event.
    crit: bool = False


class World:
    def __init__(
        self,
        level: Level,
        bestiary: Bestiary,
        seed: int = 0,
        carry_hp: int | None = None,
        hero_type_id: str = DEFAULT_HERO,
        purse: Purse | None = None,
        hero_bonus: Attributes = NEUTRAL,
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

        `hero_bonus` is what levelling has earned, and it is a constructor
        argument rather than something written onto the hero afterwards because
        of `carry_hp` below. The arriving health is clamped against the hero's
        maximum, and the maximum is not known until the attributes are on the
        body -- so a hero who earned +24 health and carried 154 into the stage
        would have it clipped back to the bare class's 130 by the very line
        meant to preserve it. Defaults to neutral, so every test and tool that
        predates the attribute layer is untouched.
        """
        self.level = level
        self.bestiary = bestiary
        self.rng = random.Random(seed)
        self.seed = seed
        self.carry_hp = carry_hp
        self.hero_type_id = hero_type_id
        self.purse = purse or Purse()
        self.hero_bonus = hero_bonus

        #: Separate from `rng` on purpose. See the module docstring: this is the
        #: guarantee that adding loot to a tuned game moved nothing.
        self.loot_rng = random.Random(seed ^ LOOT_STREAM)

        #: Crit and evasion. Separate from both of the others for the reason
        #: given at `ATTR_STREAM`, and separate from `loot_rng` too -- a fight
        #: draws from this one on hits and from that one on kills, and sharing
        #: would make each subsystem's dice depend on how the other went.
        self.attr_rng = random.Random(seed ^ ATTR_STREAM)

        #: Where the traps stand. The same trick a fourth time, and the last
        #: subsystem so far to need it -- see `hazards.HAZARD_STREAM`.
        #:
        #: What is unusual about this one is how little it is used: it is drawn
        #: from exactly once, by `hazards.place` below, and never again for the
        #: length of the stage. Everything a trap does afterwards is arithmetic
        #: on `world.tick`. That is deliberate and it is what let a hazard layer
        #: be added to a tuned campaign at all -- a die rolled on a measured tick
        #: would shift every damage roll after it.
        self.hazard_rng = random.Random(seed ^ hazards.HAZARD_STREAM)

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

        #: The fixtures of a reward room, and empty in all forty arenas. That
        #: emptiness is the whole argument that the interaction phase is free:
        #: on every tick the balance grid has ever measured, `_touch_props`
        #: returns on a falsy test before it reads anything.
        self.props: list[RoomProp] = [
            RoomProp(prop.kind, level.tile_center(*prop.tile), prop.leads_to, prop.wall)
            for prop in level.props
        ]

        #: What the floor itself does at this depth, and empty on floors that
        #: have not unlocked a trap yet, in every reward room, and whenever
        #: `data/hazards.json` says `enabled: false`.
        #:
        #: Note the difference from `props` above. That list is empty in all
        #: forty arenas, which is what makes the interaction phase free on a
        #: measured tick. **This one is not**, and that is the feature: a trap
        #: is in the arena and the balance grid was re-measured with it there.
        self.traps: tuple[hazards.Trap, ...] = hazards.place(
            level, self.purse.floor, self.hazard_rng
        )

        #: What the hero has used in this room, in the order it was used.
        #: Drained by `Run` exactly as `gold` and `xp` are, and for the same
        #: reason: `sim` takes a `World` and an `Intent` and knows nothing about
        #: a run, so it can report that a fountain was touched but not what a
        #: fountain is worth.
        self.taken: list[PropKind] = []

        #: The kind of room the door the hero walked out through leads to, set
        #: on the tick a reward room is won. None in an arena, which is what
        #: makes "an arena was cleared" and "a door was taken" two answers the
        #: run layer can tell apart.
        self.exit_to: RoomKind | None = None

        #: Which wall that door stood against, set on the same tick and for the
        #: same reason. `exit_to` says what the next room *holds*; this says
        #: which way the hero left it, and `Run._leave_room` turns that into the
        #: wall the next room is entered through -- so the rooms lie end to end
        #: and a run is a path rather than a series of identical boxes.
        self.exit_wall: Direction | None = None

        #: Experience this stage's kills have paid out, banked by `Run._bank`
        #: on the way out. On the world rather than on the run for the same
        #: reason gold is: `sim` takes a `World` and an `Intent` and knows
        #: nothing about the layer above it. Stays zero for the whole game while
        #: the shipped progression table has `xp_base: 0`.
        self.xp = 0

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

        # Before the clamp below, and before `hp` is read for any purpose: the
        # maximum this body can hold is not knowable until its attributes are
        # on it. Spawned at full health by `spawn`, so the earned health has to
        # be added to the current value as well as to the ceiling.
        if self.hero_bonus is not NEUTRAL:
            hero.bonus = self.hero_bonus
            hero.hp = hero.max_hp

        if self.carry_hp is not None:
            # Clamped at both ends. Above the maximum would turn a generous heal
            # into permanent bonus health; at or below zero would start the stage
            # already lost, with the death playing out before the player has
            # touched anything.
            hero.hp = max(1, min(self.carry_hp, hero.max_hp))

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
