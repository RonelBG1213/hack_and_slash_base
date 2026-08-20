"""The traps in the arenas: what the floor puts on the ground, and what it costs.

Forty arenas made of count, placement, cadence and reach -- and until now the
floor itself was always safe, so the only thing a player read was what was
walking at them. This is the layer that makes late terrain dangerous:

* **Spike** -- a floor tile that blinks. Punishes standing still.
* **Flame** -- mounted on a side wall, firing a lane inward on a cycle. Turns
  crossing the room into a timing problem.
* **Blade** -- a pendulum on a fixed track. The safe tile *travels*, so it is
  the one trap that cannot be waited out.

**Which kinds exist at all is decided by the floor**, and so is how many an arena
carries. That is the whole mechanic: a trap is a thing the campaign teaches at a
depth, one act apart, in the order above. The numbers are in `data/hazards.json`
and the arithmetic is here, the way `rooms.py` and `loot.py` split.

Two properties this layer is built around, and they are the reason it could be
added to a tuned game at all:

1. **It draws no dice on a measured tick.** Placement rolls once, at world
   construction, from `world.hazard_rng` and nothing else. Damage is a flat
   number off the floor curve -- no damage roll, and deliberately no crit or
   evasion roll, so `attr_rng` is untouched too. One interleaved draw on
   `world.rng` would shift every damage roll for the rest of the run and move
   all 280 cells of the recorded grid with no balance number changing. This is
   the same guarantee `loot.py` and `attributes.py` each rest on, arrived at from
   the other direction: they got their own stream, and this one also does not
   roll where it would matter.
2. **A trap's state is a pure function of the tick.** `is_live` is modular
   arithmetic on `world.tick`, and a blade's position is a triangle wave over it.
   There is nothing to serialise, so a run loaded from disk is standing in
   exactly the traps it was standing in when it was put down -- the same trick
   `rooms.offer` uses for the doors, for the same reason.

   The single exception is `Trap.rearm`, and it is a counter rather than state:
   without it a flame lane costs sixty hits a second and the damage curve means
   nothing.

**Traps damage the hero and not the enemies**, which is a deliberate asymmetry
and is argued in `data/hazards.json` under `harms`. In short: nothing in this
game paths around anything, so faction-neutral traps would make the best play
"stand behind the spikes and let the pack walk in", and a deeper floor would be
easier than a shallow one.

Pure Python -- no pygame. `world` is taken untyped here exactly as `combat.py`
takes it, which is what keeps `game/world.py` free to import this module.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .. import config
from ..core.collision import closest_point_on_segment, segment_distance
from ..core.level import Level, RoomKind
from ..core.vec2 import Vec2
from . import combat

#: The fifth stream on a `World`, xor'd into the run seed exactly as
#: `LOOT_STREAM` and `ATTR_STREAM` are. A different constant and nothing more
#: clever than that: the whole guarantee is that the sequences do not overlap,
#: and unrelated constants give unrelated sequences.
#:
#: Placement is the only thing that ever draws from it, and it draws once, at
#: construction. See the module docstring for why that matters.
HAZARD_STREAM = 0x7A0B5

#: How far from the hero's own spawn tile a trap may not be placed, in tiles.
#: A hero who materialises already standing in a spike has been given no
#: decision at all, and the first thing they would learn about the layer is that
#: it is unfair.
SAFE_TILES = 4

#: The same, measured from every enemy spawn. Smaller, because an enemy standing
#: near a trap is fine -- what is not fine is a trap placed so close to a spawn
#: that the body is inside its radius on tick zero, which at `harms: all` would
#: kill things before the fight starts.
SPAWN_CLEARANCE = 2


class TrapKind(str, Enum):
    """What a trap is.

    A `str` Enum for the reason `RoomKind` is one: it is the key in
    `data/hazards.json`, so a typo in the content file is refused by the
    constructor rather than turning into a plausible default.
    """

    SPIKE = "spike"
    FLAME = "flame"
    BLADE = "blade"


#: In the order the campaign introduces them, which is also the order they are
#: unlocked in. Written down rather than left to `TrapKind`'s declaration order,
#: because a kind added to the enum in the wrong place should not silently
#: reorder what the player is taught first.
TEACHING_ORDER = (TrapKind.SPIKE, TrapKind.FLAME, TrapKind.BLADE)


class Harms(str, Enum):
    """Who a trap damages. See `data/hazards.json` for why the default is HERO."""

    HERO = "hero"
    ALL = "all"


# --- the content file --------------------------------------------------------
@dataclass(frozen=True)
class Kind:
    """One trap kind's numbers, read out of `data/hazards.json`.

    `active` is how many ticks of `period` the trap is dangerous for. A blade
    carries `active == period`: it is dangerous on every tick and what changes
    is where it is, which is the whole of why it is the third kind.
    """

    from_floor: int
    period: int
    active: int
    radius: float

    #: Tiles a flame lane reaches inward from its nozzle. Unused by the other
    #: two, and zero there rather than None: it is a length, and a spike's
    #: length is nothing.
    reach: int = 0

    #: Tiles a blade's track spans. Unused by the other two, for the same reason.
    span: int = 0


@dataclass(frozen=True)
class Table:
    """The contents of `data/hazards.json`, read once.

    Frozen, because it is content in the same sense the bestiary, the loot table
    and the room table are: tuning a trap means editing the JSON.
    """

    enabled: bool
    harms: Harms
    bosses: bool
    damage_base: int
    damage_floor_step: float
    count_base: int
    count_floor_step: float
    count_cap: int
    rearm: int
    kinds: dict[TrapKind, Kind]

    @property
    def is_off(self) -> bool:
        """Whether the whole layer is inert -- the single switch and the rollback.

        Off, no trap is placed anywhere, `world.traps` is empty, and both sim
        phases that read it return on a falsy test. Because nothing here draws
        dice on a measured tick, that is the campaign exactly as it was measured
        rather than approximately so.
        """
        return not self.enabled

    def damage_on(self, floor: int) -> int:
        """What one trap hit costs on this floor.

        The same depth curve `data/loot.json` puts on a kill and
        `rooms.chest_worth` puts on a chest, reusing the shape rather than
        inventing a third idea of what deeper is worth.

        Draws no dice, which is the property the whole layer rests on.
        """
        return max(1, round(self.damage_base * (1 + self.damage_floor_step * (floor - 1))))

    def count_on(self, floor: int) -> int:
        """How many traps this floor carries, before the arena's own room runs out.

        Capped rather than left to climb: placement draws distinct positions out
        of the open floor, and a floor-40 arena is not much larger than a
        floor-10 one. Uncapped, a late stage becomes a grid of hazards and the
        thing the player is reading stops being the fight.
        """
        raw = round(self.count_base + self.count_floor_step * (floor - 1))
        return max(0, min(self.count_cap, raw))

    def unlocked_on(self, floor: int) -> tuple[TrapKind, ...]:
        """Which kinds this floor has seen taught, in teaching order."""
        return tuple(
            kind for kind in TEACHING_ORDER if floor >= self.kinds[kind].from_floor
        )

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        source = path or config.HAZARDS_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))

        try:
            harms = Harms(payload["harms"])
        except ValueError:
            raise ValueError(
                f"{source}: harms is '{payload['harms']}', which is not one of "
                f"{', '.join(member.value for member in Harms)}"
            ) from None

        rearm = int(payload["rearm"])
        if rearm < 1:
            # Zero is not a gentler setting, it is a different mechanic: a trap
            # that can hit on consecutive ticks costs sixty times the damage
            # number and no value in `damage` means anything any more. Better
            # said at startup than discovered by a hero dying instantly on
            # floor 3.
            raise ValueError(
                f"{source}: rearm is {rearm}, and a trap that can hit twice in "
                f"one tick makes every number under 'damage' meaningless"
            )

        kinds: dict[TrapKind, Kind] = {}
        for kind in TrapKind:
            entry = payload[kind.value]
            from_floor = int(entry["from_floor"])
            if from_floor < 1:
                raise ValueError(
                    f"{source}: {kind.value}.from_floor is {from_floor}, and "
                    f"there is no floor before 1"
                )

            period = int(entry["period"])
            if period < 1:
                raise ValueError(
                    f"{source}: {kind.value}.period is {period}, which is not a "
                    f"number of ticks"
                )

            # A blade has no active window -- it is dangerous on every tick of
            # its sweep -- so the file does not carry one and it takes the whole
            # period. Defaulted here rather than written into the JSON, so the
            # file cannot be edited into saying a blade blinks.
            active = int(entry.get("active", period))
            if not 1 <= active <= period:
                raise ValueError(
                    f"{source}: {kind.value}.active is {active}, which is not "
                    f"inside a period of {period}"
                )

            kinds[kind] = Kind(
                from_floor=from_floor,
                period=period,
                active=active,
                radius=float(entry["radius"]),
                reach=int(entry.get("reach", 0)),
                span=int(entry.get("span", 0)),
            )

        count = payload["count"]
        return cls(
            enabled=bool(payload["enabled"]),
            harms=harms,
            bosses=bool(payload["bosses"]),
            damage_base=int(payload["damage"]["base"]),
            damage_floor_step=float(payload["damage"]["floor_step"]),
            count_base=int(count["base"]),
            count_floor_step=float(count["floor_step"]),
            count_cap=int(count["cap"]),
            rearm=rearm,
            kinds=kinds,
        )


_TABLE: Table | None = None


def table() -> Table:
    """The shipped hazard table, read from disk once.

    Lazy rather than at import, for the reason `loot.table()` gives: a module
    that reads a file at import time turns a missing data file into a failure of
    `test_architecture.py`, reported as an import error naming the wrong problem.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


def reset_cache() -> None:
    """Forget the loaded table. For tests that supply their own."""
    global _TABLE
    _TABLE = None


# --- one trap ----------------------------------------------------------------
@dataclass
class Trap:
    """A hazard standing in an arena: where it is, when it bites, and how hard.

    Geometry is two points, whatever the kind, and that is what lets one hit
    test serve all three. A spike's two points are the same point; a flame's are
    its nozzle and the far end of its lane; a blade's are the two ends of its
    track, and where it actually *is* comes from the tick.

    Kept out of `entities` for the reason `pickups` and `props` are: a trap has
    no health, no faction and no brain, and putting one in that list would hand
    it to the broadphase, the separation pass and every AI brain in the game.
    """

    kind: TrapKind
    a: Vec2
    b: Vec2
    radius: float
    damage: int
    period: int
    active: int

    #: Where in its cycle this trap started, drawn at placement. Without it every
    #: trap in an arena fires in unison, which reads as one enormous trap rather
    #: than as several -- and makes a floor with three of them strictly easier
    #: than a floor with one, because all three windows overlap.
    phase: int

    #: Ticks before this trap may hit the same body again. The one mutable field
    #: on the whole layer. See `data/hazards.json` under `rearm`.
    rearm: int = 0

    @property
    def is_moving(self) -> bool:
        """Whether this trap travels rather than blinks.

        True for a blade and only a blade. Read by the hit test to decide
        between the point it occupies and the segment it swept, and by the
        renderer to decide what to draw.
        """
        return self.kind is TrapKind.BLADE

    def is_live(self, tick: int) -> bool:
        """Whether this trap is dangerous on this tick.

        Modular arithmetic on the tick and nothing else -- no state, so a save
        that records the tick records the trap. A blade carries
        `active == period` and is therefore always live; what its tick decides
        is where it is, not whether it bites.
        """
        return (tick + self.phase) % self.period < self.active

    def at(self, tick: int) -> Vec2:
        """Where a moving trap is on this tick. The midpoint of a still one.

        A triangle wave: out along the track and back, once per period. Written
        as a fraction of the period rather than as a step per tick so that it
        cannot drift -- a blade advanced by addition would accumulate float error
        over the 240,000 ticks of a run, and a seeded run has to replay exactly.
        """
        if not self.is_moving:
            return self.a

        fraction = ((tick + self.phase) % self.period) / self.period
        # 0 -> 1 -> 0 across the period, linear in both halves.
        travel = fraction * 2.0 if fraction < 0.5 else (1.0 - fraction) * 2.0
        return self.a.lerp(self.b, travel)

    def segment(self, tick: int) -> tuple[Vec2, Vec2]:
        """The stretch of floor this trap is dangerous along, on this tick.

        A blade is tested against the segment it **swept** since last tick rather
        than the point it occupies. At a nine-tile span over three hundred ticks
        it crosses most of its own width in a single tick at the middle of the
        swing, and a point test would let it pass clean through a body -- the
        same tunnelling `_step_projectiles` sweeps to avoid, and the same
        `path_is_clear` exists for.
        """
        if self.is_moving:
            return (self.at(tick - 1), self.at(tick))
        return (self.a, self.b)

    def touches(self, tick: int, pos: Vec2, body_radius: float) -> bool:
        """Whether a body of `body_radius` at `pos` is caught this tick."""
        a, b = self.segment(tick)
        return segment_distance(pos, a, b) <= self.radius + body_radius


# --- placing them ------------------------------------------------------------
def _keep_clear(level: Level) -> list[tuple[tuple[int, int], int]]:
    """Tiles no trap may be placed on top of, with how much room each wants.

    The hero's spawn gets the wide berth: a hero who materialises already inside
    a spike has been given no decision, and the first thing the layer would teach
    is that it is unfair. Enemy spawns get a narrower one -- an enemy standing
    near a trap is fine, a body inside one on tick zero is not.
    """
    clearances = [(level.hero_spawn, SAFE_TILES)]
    clearances += [(spawn.tile, SPAWN_CLEARANCE) for spawn in level.enemy_spawns]
    return clearances


def _is_clear(tile: tuple[int, int], clearances) -> bool:
    for (cx, cy), room in clearances:
        if abs(tile[0] - cx) <= room and abs(tile[1] - cy) <= room:
            return False
    return True


def _open_tiles(level: Level, clearances) -> list[tuple[int, int]]:
    """Every walkable tile a trap could stand on, in reading order.

    Built as a list and sampled from, rather than guessed at and retried. A
    rejection loop on a crowded arena is a loop with no bound on it, and an
    unbounded loop inside world construction is a hang rather than a bad level.
    """
    return [
        (x, y)
        for y in range(level.height)
        for x in range(level.width)
        if level.is_walkable(x, y) and _is_clear((x, y), clearances)
    ]


def _flame_mounts(level: Level, spec: Kind, clearances) -> list[tuple[Vec2, Vec2]]:
    """Every side wall a jet could be mounted on, with the lane it would fire.

    **Side walls only** -- the east and west edges, never the top or bottom. A
    lane that runs down the screen is far harder to read at this resolution than
    one that runs across it, and the arenas are all wider than they are tall.

    The lane is clipped at the first solid tile it meets, so a jet never burns
    through a pillar -- and a mount whose lane is immediately blocked is dropped
    entirely rather than shipped as a jet that fires into a wall.
    """
    mounts: list[tuple[Vec2, Vec2]] = []
    edges = ((0, 1), (level.width - 1, -1))

    for wall_x, inward in edges:
        for y in range(level.height):
            if not level.is_solid(wall_x, y):
                continue  # not a wall -- nothing to bolt a nozzle to

            # How far the lane gets before something solid stops it.
            reached = 0
            for step in range(1, spec.reach + 1):
                x = wall_x + inward * step
                if level.is_solid(x, y) or not _is_clear((x, y), clearances):
                    break
                reached = step

            if reached < 2:
                # A jet one tile long is a hot wall, not a hazard to cross.
                continue

            nozzle = level.tile_center(wall_x + inward, y)
            far = level.tile_center(wall_x + inward * reached, y)
            mounts.append((nozzle, far))
    return mounts


def _blade_tracks(level: Level, spec: Kind, clearances) -> list[tuple[Vec2, Vec2]]:
    """Every open run of floor long enough to hang a blade over.

    Horizontal and vertical both, because a blade is read by its motion rather
    than by its orientation -- the argument that keeps a flame lane on a side
    wall does not apply to something that is visibly moving.

    Every tile of the track has to be open. A blade that swings into a pillar
    would either clip through it or need a collision pass of its own, and a
    hazard is not worth a second collision pass.
    """
    tracks: list[tuple[Vec2, Vec2]] = []
    span = spec.span
    if span < 2:
        return tracks

    def run_is_open(x: int, y: int, dx: int, dy: int) -> bool:
        return all(
            level.is_walkable(x + dx * i, y + dy * i)
            and _is_clear((x + dx * i, y + dy * i), clearances)
            for i in range(span)
        )

    for y in range(level.height):
        for x in range(level.width):
            for dx, dy in ((1, 0), (0, 1)):
                if run_is_open(x, y, dx, dy):
                    tracks.append(
                        (
                            level.tile_center(x, y),
                            level.tile_center(x + dx * (span - 1), y + dy * (span - 1)),
                        )
                    )
    return tracks


def place(
    level: Level,
    floor: int,
    rng: random.Random,
    hazards: Table | None = None,
) -> tuple[Trap, ...]:
    """What this arena carries, given the floor it stands on.

    Called once, from `World.__init__`, and the only thing in this layer that
    ever draws a die. Everything after it is arithmetic on the tick.

    Nothing is placed at all in three cases, and each is a separate decision:
    the layer is switched off, the room is not a fight (a reward room is
    somewhere you are safe, and a trap in one would punish the player for taking
    the door the game offered), or it is a boss stage and `bosses` is false.
    """
    spec = hazards or table()
    if spec.is_off or not level.is_fight:
        return ()
    if level.kind is RoomKind.BOSS and not spec.bosses:
        return ()

    unlocked = spec.unlocked_on(floor)
    wanted = spec.count_on(floor)
    if not unlocked or wanted < 1:
        return ()

    clearances = _keep_clear(level)
    damage = spec.damage_on(floor)

    # Every position of every unlocked kind, worked out before anything is
    # drawn. Sampling from a built list rather than guessing and retrying is
    # what keeps this bounded -- see `_open_tiles`.
    pools: dict[TrapKind, list[tuple[Vec2, Vec2]]] = {}
    for kind in unlocked:
        if kind is TrapKind.SPIKE:
            pools[kind] = [
                (level.tile_center(*tile), level.tile_center(*tile))
                for tile in _open_tiles(level, clearances)
            ]
        elif kind is TrapKind.FLAME:
            pools[kind] = _flame_mounts(level, spec.kinds[kind], clearances)
        else:
            pools[kind] = _blade_tracks(level, spec.kinds[kind], clearances)

    traps: list[Trap] = []
    for _ in range(wanted):
        # Only the kinds that still have somewhere to go. An arena with no run
        # of nine open tiles simply carries no blade, rather than failing to
        # build -- the campaign is hand-authored and a stage is allowed to be
        # the wrong shape for a trap.
        available = [kind for kind in unlocked if pools[kind]]
        if not available:
            break

        kind = rng.choice(available)
        pool = pools[kind]
        a, b = pool.pop(rng.randrange(len(pool)))
        numbers = spec.kinds[kind]

        traps.append(
            Trap(
                kind=kind,
                a=a,
                b=b,
                radius=numbers.radius,
                damage=damage,
                period=numbers.period,
                active=numbers.active,
                # Spread around the cycle so an arena's traps do not fire in
                # unison. See the note on `Trap.phase`.
                phase=rng.randrange(numbers.period),
            )
        )

        # Everything that overlaps what was just placed comes out of every pool,
        # so two traps never end up on the same square of floor. Cheap because
        # the pools are already built and this is a handful of traps.
        _thin_pools(pools, a, b, numbers.radius)

    return tuple(traps)


def _thin_pools(pools, a: Vec2, b: Vec2, radius: float) -> None:
    """Drop every candidate placement that would overlap the one just taken.

    Measured segment-to-endpoint rather than segment-to-segment, which is a
    little generous and deliberately so: two traps that merely come near each
    other are fine, two that share floor are one confusing trap.
    """
    keep_apart = radius * 2.0
    for kind, pool in pools.items():
        pools[kind] = [
            (pa, pb)
            for pa, pb in pool
            if segment_distance(pa, a, b) > keep_apart
            and segment_distance(pb, a, b) > keep_apart
        ]


# --- the two sim phases ------------------------------------------------------
def tick_timers(world) -> None:
    """**Phase 1.** Re-arm counters move on before anything consults them.

    Beside the entity timers, because that is exactly what this is: a per-tick
    counter that has to have expired before the tick reads it. Returns on a
    falsy test in every arena with the layer switched off, and in every reward
    room whatever the setting.
    """
    for trap in world.traps:
        if trap.rearm > 0:
            trap.rearm -= 1


def resolve(world) -> None:
    """**Phase 7.** Every live trap against whatever is standing in it.

    Last in the strike phase, after swings and arrows, so a trap and a blow
    landing on the same tick have one readable order rather than an order that
    depends on which side of the phase somebody dropped the call.

    Draws no dice. The damage is the number `place` stamped on the trap from the
    floor curve, and it is applied through `combat.apply_hazard`, which does not
    roll for crit or evasion. That is the guarantee in the module docstring, and
    it is what makes `enabled: false` an exact rollback rather than an
    approximate one.
    """
    if not world.traps:
        return

    harms_all = table().harms is Harms.ALL
    rearm = table().rearm
    tick = world.tick

    for trap in world.traps:
        if trap.rearm > 0 or not trap.is_live(tick):
            continue

        for entity in world.entities:
            if not entity.is_alive:
                continue
            if not harms_all and not entity.is_hero:
                # The deliberate asymmetry. See `data/hazards.json` under
                # `harms` for why the default is the hero alone.
                continue
            if not trap.touches(tick, entity.pos, entity.radius):
                continue

            # The roll is the answer to every trap: `apply_hazard` checks
            # i-frames first, so a dodge passes through a jet exactly as it
            # passes through a swing. A hit that was eaten does not re-arm the
            # trap either -- rolling through a blade should not buy quiet time
            # on the far side of it.
            if combat.apply_hazard(world, entity, trap.damage, _push_from(trap, entity, tick)):
                trap.rearm = rearm
            break  # one body per trap per tick, and the hero is the one that matters


def escape_from(a: Vec2, b: Vec2, pos: Vec2) -> Vec2:
    """The shortest way out of the stretch of floor between `a` and `b`.

    Away from the **nearest point on the trap**, not away from its centre or its
    ends -- which for a flame lane is the difference between stepping out of it
    and running its whole length. A body standing in the middle of a seven-tile
    jet has the wall of fire on two sides of it and open floor a few pixels
    above; the nearest point is what finds that.

    A body sitting exactly on the line has no "away" to compute, so it is sent
    across the trap instead: perpendicular is the shortest way off a lane, and
    for a spike -- where there is no line and no perpendicular either -- any
    fixed direction will do as well as any other.

    Shared by the trap's own knockback and by the reference bot's sidestep,
    deliberately: the direction a trap throws you and the direction a hero
    should step are the same question, and two answers to it would drift.
    """
    nearest = closest_point_on_segment(pos, a, b)
    away = (pos - nearest).normalized()
    if not away.is_zero():
        return away

    span = b - a
    if span.is_zero():
        return Vec2(0.0, -1.0)
    return span.perpendicular().normalized()


def _push_from(trap: Trap, entity, tick: int) -> Vec2:
    """Which way a trap shoves what it caught.

    Out of the trap by the shortest route, so a spike throws you off it and a
    jet throws you clear of the lane rather than along it -- being knocked
    *down* a hazard is being hit by it twice, and the second hit is one the
    player could not have read.
    """
    a, b = trap.segment(tick)
    return escape_from(a, b, entity.pos)
