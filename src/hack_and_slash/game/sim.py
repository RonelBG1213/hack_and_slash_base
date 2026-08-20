"""One tick of the world. The heart of the game.

`step(world, intent)` advances everything by exactly `config.DT` seconds' worth
of simulation and nothing else. It is called from a fixed-timestep accumulator,
never once per rendered frame, which is what makes a run reproducible from its
seed: a fight resolves the same way on a machine running at 30fps as on one
running at 240.

The phase order below is not arbitrary. Each phase reads the results of the last
one, and moving any of them changes the game:

1. **timers** -- i-frames, cooldowns and stagger expire before anything consults
   them, a trap's re-arm counter moves on, and health regeneration accrues.
   Still one phase and not three: they are all per-tick counters moving on
   before the tick reads any of them
2. **decide** -- the hero's intent arrives from outside; enemies produce theirs
3. **begin** -- new swings and dodges start, committing facing
4. **move** -- walking, dashes and knockback, resolved against walls
5. **separate** -- bodies pushed out of each other
6. **index** -- the broadphase is rebuilt *after* everything has moved, so a hit
   test never consults last tick's positions
7. **strike** -- open hitboxes and arrows resolve against where things are
   *now*, and then the traps do, last of the three. A blow and a spike landing
   on the same tick have one readable order rather than an order that depends
   on which side of the phase somebody dropped the call
8. **advance** -- state machines move on, opening hitboxes and loosing arrows for
   the tick to come
9. **settle** -- the run is judged, the dead drop what they were carrying, and
   then they are removed. A reward room's fixtures are read here too, last of
   all, and the phase opens on an empty list in every one of the forty arenas
"""

from __future__ import annotations

from .. import config
from ..core.collision import circle_separation, move_and_collide, path_is_clear
from ..core.vec2 import ZERO, Vec2, from_angle
from . import actions, ai, attributes, combat, hazards, loot, progression
from .entities import ActionState, Entity, Faction
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

#: How close the hero has to be to use a fixture, on top of their own radius.
#: The same shape and the same generosity as `loot.PICKUP_RADIUS`, and for the
#: same reason -- a fountain you have to stand exactly on is a fountain you
#: circle twice. A door is the one place it matters that this is not larger: two
#: doors close enough to share a reach would take the choice away.
TOUCH_RADIUS = 8.0


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
    hazards.tick_timers(world)
    _regen(world)

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
    hazards.resolve(world)

    for entity in list(world.entities):
        _advance_state(world, entity)

    _settle(world)


# --- phases ------------------------------------------------------------------
def _regen(world: World) -> None:
    """Pay out health regeneration, in whole points, once per tick.

    **Phase 1**, beside the timers, and that placement is a decision. Regen is
    per-tick accrual, which is exactly what phase 1 is for -- and putting it
    here means a hit and a regen arriving on the same tick have one readable
    order (the point is banked, then the fight happens) instead of an order that
    depends on which side of `strike` somebody dropped the call.

    Banked in hundredths and paid in whole points, so nothing anywhere holds a
    fractional hit point. A float bank would accumulate over the 240,000 ticks
    of a run, and a seeded run has to replay exactly.

    Two guards, and both are load-bearing rather than defensive:

    * **The dead do not regenerate.** The phase-1 loop has no liveness filter,
      and `_settle` culls a corpse one tick after it dies -- so without this a
      body could tick back above zero in the window between the two and quietly
      un-lose the run.
    * **Nothing is banked at full health**, so a hero that spends a whole stage
      untouched does not arrive at the next fight with a reservoir of instant
      healing saved up.
    """
    for entity in world.entities:
        rate = entity.attrs.regen
        if rate <= 0 or not entity.is_alive:
            continue

        ceiling = entity.max_hp
        if entity.hp >= ceiling:
            entity.regen_bank = 0
            continue

        entity.regen_bank += rate
        gained, entity.regen_bank = divmod(entity.regen_bank, attributes.REGEN_SCALE)
        if gained:
            entity.hp = min(ceiling, entity.hp + gained)


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

    if intent.attack and actions.begin_attack(entity, weapon_index=intent.weapon):
        if not entity.is_hero:
            # Read *after* the attack starts, so the pause is measured against
            # the attack actually chosen rather than the type's default one.
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


def _walk_speed(entity: Entity) -> float:
    """Walking speed in pixels per tick, attribute block included.

    Zero takes the type's own number straight back rather than multiplying it by
    1.0 -- the same early return `combat.evades` and the crit roll take, and for
    the same reason. Every enemy in the game and every hero that has bought
    nothing goes down that branch, so a fight with this dial untouched is
    arithmetically the fight that was measured, bit for bit, rather than
    approximately so.
    """
    bonus = entity.attrs.move_speed
    if bonus == 0:
        return entity.type.speed
    return entity.type.speed * (1 + bonus / attributes.PER_MILLE)


def _self_propulsion(entity: Entity, intent: Intent) -> Vec2:
    """How far a body moves under its own power this tick, knockback aside."""
    if entity.state is ActionState.DODGING:
        # `type.dodge_speed`, and deliberately not scaled by `move_speed`. The
        # roll is a fixed-distance defensive tool: how far it travels is how
        # much ground one i-frame window covers, so a speed stat that stretched
        # it would be buying invulnerability rather than mobility.
        return entity.dash_dir * entity.type.dodge_speed

    if entity.state is ActionState.ACTIVE and entity.weapon.is_charge:
        # A charge *is* its attack: the body moves for as long as the hitbox is
        # open, in the direction it committed to when the telegraph started.
        return entity.dash_dir * entity.weapon.charge_speed

    scale = actions.movement_scale(entity)
    if scale <= 0.0:
        return ZERO
    # Clamped, not normalised: a half-pushed stick should walk at half speed,
    # but two keys held at once must not add up to 1.41x.
    return intent.move.clamped(1.0) * (_walk_speed(entity) * scale)


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

    weapon = entity.weapon
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
    """Fire this attack's shots, fanned evenly across its spread.

    One shot goes straight ahead and ignores the spread entirely, so an archer
    is unchanged by the existence of volleys. Several fan symmetrically about
    the facing, which is what turns a shot you sidestep into a wall you have to
    go around.
    """
    weapon = entity.weapon
    count = max(1, weapon.projectile_count)

    for index in range(count):
        # -0.5..+0.5 across the fan; a single shot lands exactly on the facing.
        offset = 0.0 if count == 1 else (index / (count - 1) - 0.5) * weapon.spread
        heading = from_angle(entity.facing + offset)

        # The attacker's half of the attribute layer, applied here rather than
        # at impact, because a shot carries an id and the owner may be dead and
        # culled by the time it arrives. `NEUTRAL` for the defender: the target
        # is not known yet, and its defense is taken in `resolve_projectile_hits`
        # where it is. Per shot, like the damage roll and for the same reason.
        damage, crit = combat.resolve_damage(
            combat.roll_damage(weapon, world.rng),
            entity.attrs,
            attributes.NEUTRAL,
            world.attr_rng,
        )
        world.spawn_projectile(
            Projectile(
                id=world.take_projectile_id(),
                owner_id=entity.id,
                faction=entity.type.faction,
                # Started clear of the shooter's own body, so a shot cannot be
                # born already overlapping something standing next to it.
                pos=entity.pos + heading * (entity.radius + weapon.projectile_radius + 1.0),
                velocity=heading * weapon.projectile_speed,
                radius=weapon.projectile_radius,
                # Rolled per shot: a volley that lands three identical numbers
                # reads as one hit rather than three.
                damage=damage,
                crit=crit,
                knockback=weapon.knockback,
                ticks_left=weapon.projectile_lifetime,
            )
        )


def _settle(world: World) -> None:
    """Judge the run, take what the dead were carrying, then remove them.

    In that order: the hero has to still be in the list to be found dead, and
    culling first would make a loss indistinguishable from a hero who was never
    there. Loot goes between the two for the same reason -- a body that has
    already been culled cannot be asked what it was worth.
    """
    hero = world.hero
    if world.outcome is Outcome.RUNNING:
        if hero is None or not hero.is_alive:
            world.outcome = Outcome.LOST
        elif world.level.is_fight and not world.enemies():
            # `is_fight` and not simply "no enemies left". A reward room has
            # none from the tick it opens, so without this it would be cleared
            # before the hero had taken a step -- and the two facts are the same
            # today and different faults tomorrow.
            world.outcome = Outcome.WON

    _drop_loot(world)
    _award_xp(world)
    world.entities = [entity for entity in world.entities if entity.is_alive]

    # Before the pickup sweep, so a room won by walking through a door still
    # hoovers up whatever was on its floor -- `_collect_pickups` sweeps on WON
    # and would have already run by the time this set it.
    _touch_props(world, hero)
    _collect_pickups(world, hero)


def _drop_loot(world: World) -> None:
    """What the newly dead leave on the floor.

    Called once per tick, immediately before the cull, which is what makes it
    safe: a body is dead and still in the list for exactly one settle, so every
    kill is paid out exactly once and no "have I looted this already" flag is
    needed anywhere.

    Enemies only. Nothing pays out for a dead hero, which is checked in
    `test_entities.py` from the other end -- no class carries a level.
    """
    table = loot.table()
    for entity in world.entities:
        if entity.is_alive or entity.type.faction is not Faction.ENEMY:
            continue
        world.pickups.extend(
            table.roll_drops(
                entity.type.level,
                world.purse.floor,
                entity.pos,
                # The loot stream, never `world.rng`. Drawing from that one here
                # would shift every damage roll for the rest of the run.
                world.loot_rng,
                world.purse.gold_find,
            )
        )


def _award_xp(world: World) -> None:
    """What the newly dead are worth in experience.

    Beside `_drop_loot` and before the cull, which is what makes it safe for
    exactly the reason the loot pass is safe: a body is dead and still in the
    list for one settle, so every kill pays out once and no "have I counted
    this" flag is needed.

    Accumulated onto the world and banked by `Run._bank`, the same road gold
    travels -- the sim never sees a `Run`.

    Draws no dice. This is the one subsystem added to the game that needed no
    RNG stream of its own, because there is nothing here to roll.
    """
    payout = progression.table()
    if payout.is_off:
        return
    for entity in world.entities:
        if entity.is_alive or entity.type.faction is not Faction.ENEMY:
            continue
        world.xp += payout.xp_for(entity.type.level)


def _touch_props(world: World, hero: Entity | None) -> None:
    """Use whatever the hero is standing on, in a room that has anything to use.

    **This returns on the first line in every arena the balance grid has ever
    measured.** `World.props` is built from `Level.props`, and all forty stage
    files carry none -- so the cost of this phase on a measured tick is one
    falsy test, and the claim that adding rooms did not move the grid is a fact
    about the code rather than a hope. It is the same argument the loot layer
    and the attribute layer each rest on.

    What it does *not* do is decide what a fixture is worth. A fountain heals by
    an amount that depends on the class, a chest pays by the floor, and a shrine
    hands out a currency this module has never heard of -- all of which are
    facts about a `Run`, and `sim` takes a `World` and an `Intent` and knows
    nothing about one. So this records that a thing was used, exactly as
    `_drop_loot` records gold onto the world, and the layer above collects.

    A door is the exception that ends the room: it is the reward room's only
    win condition, since there is nothing in one to kill.
    """
    if not world.props:
        return
    if hero is None or not hero.is_alive or world.outcome is not Outcome.RUNNING:
        return

    reach = hero.radius + TOUCH_RADIUS
    for prop in world.props:
        if prop.taken or prop.pos.distance_to(hero.pos) > reach:
            continue

        prop.taken = True
        world.emit(Event(EventKind.PROP, prop.pos, hero.id, is_hero=True))

        if prop.is_door:
            world.exit_to = prop.leads_to
            world.exit_wall = prop.wall
            world.outcome = Outcome.WON
            # Returned rather than broken out of, and the difference is real:
            # two doors within one reach would otherwise both be marked taken
            # and the second would overwrite where the hero was going.
            return

        # Doors deliberately absent from this list. The run asks `exit_to`
        # where it went and `taken` what it picked up, and one door in both
        # would make "did I use anything" a question with two answers.
        world.taken.append(prop.kind)


def _collect_pickups(world: World, hero: Entity | None) -> None:
    """Bank whatever the hero is standing on -- and everything else once the
    stage is won.

    The sweep is not a convenience. A stage is won on the tick its last enemy
    dies, and the run layer builds the next `World` on that same tick, so a drop
    from the final kill would be destroyed before anyone could walk to it. The
    fight being over is exactly when picking things up stops being interesting,
    so it happens on its own.

    `hero` is passed in because it was read before the cull; looking it up again
    here would return None for a hero who died this tick, and a dead hero
    collecting a coin is worse than not collecting one.
    """
    if hero is None or not hero.is_alive or not world.pickups:
        return

    sweeping = world.outcome is Outcome.WON
    reach = hero.radius + loot.PICKUP_RADIUS

    remaining = []
    for pickup in world.pickups:
        if not sweeping and pickup.pos.distance_to(hero.pos) > reach:
            remaining.append(pickup)
            continue
        world.gold += pickup.gold
        world.emit(
            Event(
                EventKind.PICKUP,
                pickup.pos,
                hero.id,
                amount=pickup.gold,
                is_hero=True,
                rarity=pickup.rarity.value if pickup.rarity else "",
            )
        )
    world.pickups = remaining


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
