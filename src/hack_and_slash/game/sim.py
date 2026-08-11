"""One tick of the world. The heart of the game.

`step(world, intent)` advances everything by exactly `config.DT` seconds' worth
of simulation and nothing else. It is called from a fixed-timestep accumulator,
never once per rendered frame, which is what makes a run reproducible from its
seed: a fight resolves the same way on a machine running at 30fps as on one
running at 240.

The phase order below is not arbitrary. Each phase reads the results of the last
one, and moving any of them changes the game:

1. **timers** -- i-frames, cooldowns and stagger expire before anything consults them
2. **decide** -- the hero's intent arrives from outside; enemies produce theirs
3. **begin** -- new swings and dodges start, committing facing
4. **move** -- walking, dashes and knockback, resolved against walls
5. **separate** -- bodies pushed out of each other
6. **index** -- the broadphase is rebuilt *after* everything has moved, so a hit
   test never consults last tick's positions
7. **strike** -- open hitboxes and arrows resolve against where things are *now*
8. **advance** -- state machines move on, opening hitboxes and loosing arrows for
   the tick to come
9. **settle** -- the dead are removed and the run is judged
"""

from __future__ import annotations

from .. import config
from ..core.collision import circle_separation, move_and_collide, path_is_clear
from ..core.vec2 import ZERO, Vec2, from_angle
from . import actions, ai, combat
from .entities import ActionState, Entity
from .events import Event, EventKind
from .intent import NOTHING, Intent
from .world import Outcome, Projectile, World

#: Per-tick decay on knockback momentum. At 0.8 a shove travels about a tile
#: before it dies out -- long enough to read as impact, short enough that it
#: never takes control away for long.
FRICTION = 0.8

#: Momentum below this is dropped to zero rather than trailing off forever.
MOMENTUM_EPSILON = 0.05

#: How hard overlapping bodies push apart, per tick. A full push looks springy;
#: this settles a crowd over a few ticks instead.
SEPARATION_STRENGTH = 0.5


def step(world: World, hero_intent: Intent = NOTHING) -> None:
    """Advance the world by one fixed tick."""
    world.events = []
    world.tick += 1

    # A one-shot mailbox, cleared like the event list. The presentation layer
    # reads it after the step and runs the freeze on its own clock -- if the sim
    # counted it down instead, a scene that pauses stepping during hitstop would
    # freeze the very counter that ends the freeze.
    world.hitstop = 0

    for entity in world.entities:
        actions.tick_timers(entity)

    intents = _gather_intents(world, hero_intent)

    for entity in world.entities:
        _begin_actions(world, entity, intents.get(entity.id, NOTHING))

    for entity in world.entities:
        _move(world, entity, intents.get(entity.id, NOTHING))

    _separate(world)
    _step_projectiles(world)

    world.rebuild_index()

    combat.resolve_swings(world)
    combat.resolve_projectile_hits(world)

    for entity in list(world.entities):
        _advance_state(world, entity)

    _settle(world)


# --- phases ------------------------------------------------------------------
def _gather_intents(world: World, hero_intent: Intent) -> dict[int, Intent]:
    """The hero's intent comes from outside; everything else thinks for itself.

    Both go into the same dict and through the same code below, which is the
    point: there is no separate movement path for enemies to cheat on.
    """
    intents: dict[int, Intent] = {}
    for entity in world.entities:
        if not entity.is_alive:
            continue
        if entity.id == world.hero_id:
            intents[entity.id] = hero_intent
        else:
            intents[entity.id] = ai.decide(world, entity)
    return intents


def _begin_actions(world: World, entity: Entity, intent: Intent) -> None:
    if not entity.is_alive:
        return

    # Facing tracks aim only while free. Once a swing or a roll has started it
    # is locked -- being able to spin mid-swing would make every attack a
    # homing one and every dodge direction a lie.
    if actions.can_act(entity) and not intent.aim.is_zero():
        entity.facing = intent.aim.angle()

    # Roll the way you are walking; fall back to where you are looking. Written
    # out rather than with `or` because a Vec2 is a tuple, and Vec2(0, 0) is
    # perfectly truthy -- the short version silently never reaches the fallback.
    roll_dir = intent.move if not intent.move.is_zero() else intent.aim

    if intent.dodge and actions.begin_dodge(entity, roll_dir):
        world.emit(
            Event(EventKind.DODGE, entity.pos, entity.id, facing=entity.facing,
                  is_hero=entity.is_hero)
        )
        return  # a dodge and an attack cannot start on the same tick

    if intent.attack and actions.begin_attack(entity):
        if not entity.is_hero:
            entity.attack_cooldown = ai.cooldown_for(entity)


def _move(world: World, entity: Entity, intent: Intent) -> None:
    if not entity.is_alive:
        return

    displacement = _self_propulsion(entity, intent) + entity.velocity

    entity.velocity = entity.velocity * FRICTION
    if entity.velocity.length() < MOMENTUM_EPSILON:
        entity.velocity = ZERO

    if displacement.is_zero():
        return

    entity.pos = move_and_collide(
        entity.pos, entity.radius, displacement, world.is_solid, world.level.tile
    )


def _self_propulsion(entity: Entity, intent: Intent) -> Vec2:
    """How far a body moves under its own power this tick, knockback aside."""
    if entity.state is ActionState.DODGING:
        return entity.dash_dir * entity.type.dodge_speed

    if entity.state is ActionState.ACTIVE and entity.type.charge_speed > 0:
        # The charger's dash *is* its attack: it moves for as long as the hitbox
        # is open, in the direction it committed to when the telegraph started.
        return entity.dash_dir * entity.type.charge_speed

    scale = actions.movement_scale(entity)
    if scale <= 0.0:
        return ZERO
    # Clamped, not normalised: a half-pushed stick should walk at half speed,
    # but two keys held at once must not add up to 1.41x.
    return intent.move.clamped(1.0) * (entity.type.speed * scale)


def _separate(world: World) -> None:
    """Push overlapping bodies apart so a crowd does not become one point.

    Both bodies give ground, so a heavy thing does not shove a light one through
    a wall. The push is resolved against the level afterwards, because being
    pushed out of a friend and into a pillar is not an improvement.
    """
    living = [e for e in world.entities if e.is_alive]
    for i, first in enumerate(living):
        for second in living[i + 1 :]:
            # A dash goes through its own kind. Otherwise a charger ploughing
            # into the pack stops dead on its friends, and the attack the player
            # was told to dodge simply never arrives.
            if first.state is ActionState.DODGING or second.state is ActionState.DODGING:
                continue

            offset = circle_separation(first.pos, first.radius, second.pos, second.radius)
            if offset.is_zero():
                continue
            share = offset * (SEPARATION_STRENGTH * 0.5)
            first.pos = move_and_collide(
                first.pos, first.radius, share, world.is_solid, world.level.tile
            )
            second.pos = move_and_collide(
                second.pos, second.radius, -share, world.is_solid, world.level.tile
            )


def _step_projectiles(world: World) -> None:
    """Fly, expire, and stop at walls. Hits are resolved separately."""
    survivors = []
    for shot in world.projectiles:
        shot.ticks_left -= 1
        if shot.ticks_left <= 0:
            world.emit(Event(EventKind.PROJECTILE_SPENT, shot.pos, shot.id))
            continue

        moved = shot.pos + shot.velocity
        # Swept, not sampled. A projectile fast enough to cross a tile in one
        # tick would otherwise land cleanly on the far side of a wall it never
        # touched -- the same failure substepping fixed for bodies.
        if not path_is_clear(shot.pos, moved, world.is_solid, world.level.tile):
            world.emit(Event(EventKind.PROJECTILE_SPENT, moved, shot.id))
            continue

        shot.pos = moved
        survivors.append(shot)
    world.projectiles = survivors


def _advance_state(world: World, entity: Entity) -> None:
    """Tick the state machine, and act on whatever it just entered."""
    entered = actions.advance(entity)
    if entered is not ActionState.ACTIVE:
        return

    weapon = entity.type.weapon
    if weapon.projectile:
        _loose_projectile(world, entity)
        world.emit(
            Event(EventKind.SHOOT, entity.pos, entity.id, facing=entity.facing,
                  is_hero=entity.is_hero)
        )
    else:
        world.emit(
            Event(EventKind.SWING, entity.pos, entity.id, facing=entity.facing,
                  is_hero=entity.is_hero)
        )


def _loose_projectile(world: World, entity: Entity) -> None:
    weapon = entity.type.weapon
    heading = from_angle(entity.facing)
    world.spawn_projectile(
        Projectile(
            id=world.take_projectile_id(),
            owner_id=entity.id,
            faction=entity.type.faction,
            # Started clear of the shooter's own body, so an arrow cannot be
            # born already overlapping something standing next to the archer.
            pos=entity.pos + heading * (entity.radius + weapon.projectile_radius + 1.0),
            velocity=heading * weapon.projectile_speed,
            radius=weapon.projectile_radius,
            damage=combat.roll_damage(weapon, world.rng),
            knockback=weapon.knockback,
            ticks_left=weapon.projectile_lifetime,
        )
    )


def _settle(world: World) -> None:
    """Judge the run, then remove the dead.

    In that order: the hero has to still be in the list to be found dead, and
    culling first would make a loss indistinguishable from a hero who was never
    there.
    """
    hero = world.hero
    if world.outcome is Outcome.RUNNING:
        if hero is None or not hero.is_alive:
            world.outcome = Outcome.LOST
        elif not world.enemies():
            world.outcome = Outcome.WON

    world.entities = [entity for entity in world.entities if entity.is_alive]


# --- driving the sim from real time ------------------------------------------
class Accumulator:
    """Turns wall-clock frame times into a whole number of fixed ticks.

    The sim must never see a variable timestep, and the renderer must never be
    blocked waiting for one. This is the piece between them: it banks real
    elapsed seconds and pays out whole ticks.

    A long stall -- dragging the window, a breakpoint -- is clamped rather than
    replayed, because fast-forwarding a player through a fight they never saw is
    worse than losing the time.
    """

    def __init__(self, dt: float = config.DT, max_frame: float = config.MAX_FRAME_TIME) -> None:
        self.dt = dt
        self.max_frame = max_frame
        self._banked = 0.0

    def ticks_for(self, elapsed_seconds: float) -> int:
        self._banked += min(elapsed_seconds, self.max_frame)
        ticks = int(self._banked / self.dt)
        self._banked -= ticks * self.dt
        return ticks
