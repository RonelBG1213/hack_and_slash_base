"""Who hits whom, for how much, and what it does to them.

All randomness comes from the world's injected `Random`, so a seeded fight
replays identically and damage numbers can be asserted rather than approximated.

The three rules worth stating outright:

* **A swing hits each body at most once**, tracked in `attacker.hit_ids`, which
  is cleared when a new swing starts. A four-tick active window would otherwise
  deal its damage four times.
* **A body already hit by this swing is recorded even when the hit is eaten by
  i-frames.** Otherwise dodging the first frame of a swing means being hit by
  its second.
* **Damage never rounds to zero.** A hit that does nothing reads as a bug.
"""

from __future__ import annotations

from ..core.collision import circles_overlap, cone_hits
from ..core.vec2 import from_angle
from . import actions
from .entities import ActionState, Entity, Weapon
from .events import Event, EventKind

#: A hit always lands for at least this much.
MIN_DAMAGE = 1


def roll_damage(weapon: Weapon, rng) -> int:
    if weapon.variance <= 0:
        return max(MIN_DAMAGE, weapon.damage)
    swing = rng.randint(-weapon.variance, weapon.variance)
    return max(MIN_DAMAGE, weapon.damage + swing)


def are_hostile(a: Entity, b: Entity) -> bool:
    return a.type.faction is not b.type.faction


def apply_hit(world, attacker: Entity, target: Entity, weapon: Weapon, rng) -> bool:
    """Land a blow. Returns False if it was eaten by invulnerability.

    Knockback is applied as an impulse on `velocity`, which friction bleeds off
    over the next few ticks -- so a hit shoves a body rather than teleporting it,
    and a shove can push something into a wall or out of its own swing.
    """
    if target.is_invulnerable:
        world.emit(
            Event(EventKind.BLOCKED, target.pos, target.id, is_hero=target.is_hero)
        )
        return False

    damage = roll_damage(weapon, rng)
    target.hp = max(0, target.hp - damage)
    target.last_hit_by = attacker.id
    target.flash = actions.FLASH_TICKS

    push = (target.pos - attacker.pos).normalized()
    if push.is_zero():
        # Standing exactly on top of each other: shove along the swing instead,
        # which is at least the direction the blow came from.
        push = from_angle(attacker.facing)
    target.velocity = target.velocity + push * weapon.knockback

    target.stagger = actions.STAGGER_TICKS
    actions.interrupt(target)

    # Cosmetic freeze. The sim decrements this but never branches on it.
    world.hitstop = max(world.hitstop, weapon.hitstop)

    world.emit(
        Event(
            EventKind.HIT,
            target.pos,
            target.id,
            amount=damage,
            facing=attacker.facing,
            is_hero=target.is_hero,
        )
    )
    if not target.is_alive:
        world.emit(Event(EventKind.DEATH, target.pos, target.id, is_hero=target.is_hero))
    return True


def resolve_swings(world) -> None:
    """Every open hitbox against every valid target, once per tick."""
    for attacker in world.entities:
        if attacker.state is not ActionState.ACTIVE or not attacker.is_alive:
            continue
        weapon = attacker.type.weapon
        if weapon.projectile:
            continue  # loosed at the windup transition; the arrow does the hitting

        # Broadphase: reach plus the largest body that could be clipping the far
        # edge of the arc. Over-fetching here is free; under-fetching is a miss.
        search = weapon.reach + _widest_radius(world)
        for target in list(world.nearby(attacker.pos, search)):
            if target.id in attacker.hit_ids:
                continue
            if not target.is_alive or not are_hostile(attacker, target):
                continue
            if not cone_hits(
                attacker.pos, attacker.facing, weapon.arc, weapon.reach,
                target.pos, target.radius,
            ):
                continue

            # Recorded before the i-frame check, so a dodge that eats the first
            # frame of a swing is not punished by its second.
            attacker.hit_ids.add(target.id)
            apply_hit(world, attacker, target, weapon, world.rng)


def resolve_projectile_hits(world) -> None:
    """Arrows against bodies. Spent on the first thing they hit."""
    survivors = []
    for shot in world.projectiles:
        struck = False
        for target in list(world.nearby(shot.pos, shot.radius + _widest_radius(world))):
            if not target.is_alive or target.type.faction is shot.faction:
                continue
            if not circles_overlap(shot.pos, shot.radius, target.pos, target.radius):
                continue

            struck = True
            if target.is_invulnerable:
                world.emit(
                    Event(EventKind.BLOCKED, target.pos, target.id, is_hero=target.is_hero)
                )
                break

            target.hp = max(0, target.hp - shot.damage)
            target.last_hit_by = shot.owner_id
            target.flash = actions.FLASH_TICKS
            target.velocity = target.velocity + shot.velocity.normalized() * shot.knockback
            target.stagger = actions.STAGGER_TICKS
            actions.interrupt(target)
            world.emit(
                Event(
                    EventKind.HIT,
                    target.pos,
                    target.id,
                    amount=shot.damage,
                    is_hero=target.is_hero,
                )
            )
            if not target.is_alive:
                world.emit(
                    Event(EventKind.DEATH, target.pos, target.id, is_hero=target.is_hero)
                )
            break

        if struck:
            world.emit(Event(EventKind.PROJECTILE_SPENT, shot.pos, shot.id))
        else:
            survivors.append(shot)
    world.projectiles = survivors


def _widest_radius(world) -> float:
    """Largest body radius in play, for sizing broadphase queries.

    Read from the bestiary rather than the live entities: it is constant for a
    run, and a query that shrinks as enemies die would start missing the ones
    still standing.
    """
    return max(entity_type.radius for entity_type in world.bestiary.types.values())
