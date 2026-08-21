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
from ..core.vec2 import Vec2, from_angle
from . import actions
from .attributes import PER_MILLE, Attributes
from .entities import ActionState, Entity, Weapon
from .events import Event, EventKind

#: A hit always lands for at least this much.
MIN_DAMAGE = 1

#: How hard a trap throws what it caught. A constant rather than a number per
#: trap kind, because what the shove is for is getting a body clear of the
#: hazard -- not expressing how heavy the hazard is. Sits between a light
#: weapon's knockback and a heavy one's, so being caught reads as an impact
#: without taking control away for longer than the mistake was worth.
HAZARD_KNOCKBACK = 2.2


def incoming(world, target: Entity, damage: int) -> int:
    """This hit, after the run's difficulty has had its say.

    **Applied to the hero and to nothing else.** A tier scales what the player
    takes, not what the player deals -- so an enemy's health, its cadence and
    the number of swings needed to kill it are identical on every tier, and a
    fight learned on one reads the same on another. Making it symmetric would
    have made Forgiving a shorter fight as well as a safer one, which is two
    changes wearing one name.

    Called from all three places damage reaches a body -- a swing, a shot and a
    trap. A trap is included on purpose: the hero cannot tell, mid-corridor,
    which of the two hurt it, and a tier that quietly excluded the floor would
    read as a bug on the stages built around spikes.

    `MIN_DAMAGE` is re-applied here rather than inside `Difficulty.scaled`,
    because the floor is combat's to own -- see that module's note on why it
    does not import this one. At the identity tier `scaled` returns its
    argument untouched and this is `max(MIN_DAMAGE, damage)` on a number that
    already cleared that floor, so the arithmetic is provably the arithmetic
    that was measured.
    """
    if not target.is_hero:
        return damage
    return max(MIN_DAMAGE, world.difficulty.scaled(damage))


def roll_damage(weapon: Weapon, rng) -> int:
    """The weapon's own number, rolled. **Draws from `world.rng` and nothing
    else in the game does.**

    Signature and draw count are both load-bearing and are deliberately
    untouched by the attribute layer: `tests/test_combat.py` reconstructs the
    first hit of a seeded run by calling this with a bare `random.Random(seed)`,
    and every recorded balance number was measured against exactly this
    sequence of draws. `resolve_damage` below *wraps* this rather than
    absorbing it, so that stays true.
    """
    if weapon.variance <= 0:
        return max(MIN_DAMAGE, weapon.damage)
    swing = rng.randint(-weapon.variance, weapon.variance)
    return max(MIN_DAMAGE, weapon.damage + swing)


def resolve_damage(
    base: int, attacker: Attributes, defender: Attributes, rng
) -> tuple[int, bool]:
    """Turn a rolled weapon number into what the target actually loses.

    Returns `(damage, was_crit)`. `rng` is **`world.attr_rng`**, never
    `world.rng` -- see the note on `ATTR_STREAM` in `world.py`.

    The order is fixed and changing it changes the game:

        base  ->  + attacker.damage  ->  x crit  ->  - defender.defense  ->  floor

    Flat damage before the crit, so a point of damage is worth more to a class
    that crits often -- which is the only thing making the two attributes
    interesting side by side. Defense after the crit, so armour is worth least
    against the biggest hit, which is what makes a crit read as one.

    `MIN_DAMAGE` still applies underneath everything, so no amount of defense
    makes a body immune. That floor is not politeness: a fight where nothing can
    hurt anything runs to the tick limit and reports as a balance failure in
    every instrument this project has.

    Zero crit chance takes an early return and draws no die at all, mirroring
    `roll_damage` at zero variance. That is what keeps a neutral fight drawing
    exactly the dice a pre-attribute fight drew.
    """
    damage = base + attacker.damage

    crit = attacker.crit_chance > 0 and rng.randrange(PER_MILLE) < attacker.crit_chance
    if crit:
        damage = (damage * (PER_MILLE + attacker.crit_damage)) // PER_MILLE

    return max(MIN_DAMAGE, damage - defender.defense), crit


def evades(defender: Attributes, rng) -> bool:
    """Whether this hit is avoided outright.

    Checked beside the i-frame gate rather than inside `resolve_damage`, because
    an evaded hit is not a hit for nothing -- it lands no knockback, no stagger
    and no hitstop, exactly as invulnerability does. Zero takes an early return
    and draws nothing, for the same reason crit does.
    """
    return defender.evasion > 0 and rng.randrange(PER_MILLE) < defender.evasion


def are_hostile(a: Entity, b: Entity) -> bool:
    return a.type.faction is not b.type.faction


def apply_hit(world, attacker: Entity, target: Entity, weapon: Weapon, rng) -> bool:
    """Land a blow. Returns False if it was eaten by invulnerability.

    Knockback is applied as an impulse on `velocity`, which friction bleeds off
    over the next few ticks -- so a hit shoves a body rather than teleporting it,
    and a shove can push something into a wall or out of its own swing.
    """
    if target.is_invulnerable or evades(target.attrs, world.attr_rng):
        # Evasion reuses BLOCKED on purpose: to a player the two are the same
        # event -- an attack that arrived and did nothing -- and `effects.py`
        # already draws it. A second event kind would be a second thing to draw
        # that means the same thing.
        world.emit(
            Event(EventKind.BLOCKED, target.pos, target.id, is_hero=target.is_hero)
        )
        return False

    damage, crit = resolve_damage(
        roll_damage(weapon, rng), attacker.attrs, target.attrs, world.attr_rng
    )
    damage = incoming(world, target, damage)
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
    if crit:
        world.emit(Event(EventKind.CRIT, target.pos, target.id, amount=damage,
                         is_hero=target.is_hero))
    if not target.is_alive:
        world.emit(Event(EventKind.DEATH, target.pos, target.id, is_hero=target.is_hero))
    return True


def apply_hazard(world, target: Entity, damage: int, push: Vec2) -> bool:
    """Hurt a body with something that is not a body. Returns False if it missed.

    A trap has no attacker and no weapon, which is why this exists rather than
    `apply_hit` growing two optional arguments. Three differences, and every one
    of them is load-bearing rather than a simplification:

    1. **It rolls nothing.** `damage` arrives already decided -- a flat number
       off the floor curve in `data/hazards.json` -- and there is no crit or
       evasion roll on top. So a trap draws from neither `world.rng` nor
       `world.attr_rng`, and cannot shift the sequence a damage roll or a crit
       roll reads from. That is the whole reason the hazard layer could be added
       to a tuned campaign, and it is the same guarantee `loot.py` gets from
       having its own stream.
    2. **`last_hit_by` is left alone.** Nothing killed you; the floor did. A
       trap that claimed the kill would put an id in there that belongs to no
       entity, and everything downstream of that field would have to learn what
       a trap is.
    3. **No stagger and no interrupt.** A trap that cancelled the swing you were
       mid-way through would make a mistimed step cost the attack as well as the
       health, and the two together is more than the mistake was worth. It still
       shoves, because being thrown clear of a hazard is how you stop taking it.

    Invulnerability is checked exactly as it is for a blow, and that is the
    design: **the roll is the answer to every trap.** A dodge passes through a
    jet the way it passes through a sword.
    """
    if target.is_invulnerable:
        # Reuses BLOCKED, exactly as an evaded blow does: to a player these are
        # the same event -- something arrived and did nothing -- and
        # `effects.py` already draws it.
        world.emit(Event(EventKind.BLOCKED, target.pos, target.id, is_hero=target.is_hero))
        return False

    damage = incoming(world, target, damage)
    target.hp = max(0, target.hp - damage)
    target.flash = actions.FLASH_TICKS

    if not push.is_zero():
        # No knockback number of its own: a trap shoves by a fixed amount,
        # because what the shove is for is getting the body clear of the hazard
        # rather than expressing how heavy the hazard is.
        target.velocity = target.velocity + push * HAZARD_KNOCKBACK

    world.emit(
        Event(EventKind.TRAP, target.pos, target.id, amount=damage, is_hero=target.is_hero)
    )
    if not target.is_alive:
        world.emit(Event(EventKind.DEATH, target.pos, target.id, is_hero=target.is_hero))
    return True


def resolve_swings(world) -> None:
    """Every open hitbox against every valid target, once per tick."""
    for attacker in world.entities:
        if attacker.state is not ActionState.ACTIVE or not attacker.is_alive:
            continue
        weapon = attacker.weapon
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
    """Arrows against bodies. Spent on the first thing they hit.

    **The attacker's half of the attribute layer was already applied at
    launch**, in `sim._loose_projectile`, and that split is forced rather than
    chosen: a shot carries `owner_id`, not a body, and by the time it lands the
    owner may be dead and culled out of `world.entities`. So the attacker's
    damage bonus and its crit are folded into `shot.damage` when the arrow is
    loosed, and only the *target's* half -- evasion and defense -- is resolved
    here, where the target is in scope.

    The visible consequence is that an arrow's crit is decided when it is fired
    rather than when it arrives. Nothing can observe the difference: the roll is
    from `attr_rng` either way and the arrow's damage is already fixed at launch
    for the same reason.
    """
    survivors = []
    for shot in world.projectiles:
        struck = False
        for target in list(world.nearby(shot.pos, shot.radius + _widest_radius(world))):
            if not target.is_alive or target.type.faction is shot.faction:
                continue
            if not circles_overlap(shot.pos, shot.radius, target.pos, target.radius):
                continue

            struck = True
            if target.is_invulnerable or evades(target.attrs, world.attr_rng):
                world.emit(
                    Event(EventKind.BLOCKED, target.pos, target.id, is_hero=target.is_hero)
                )
                break

            # Attacker's side already in `shot.damage`; only the target's
            # defense is left to apply, and the floor still holds under it.
            damage = incoming(
                world, target, max(MIN_DAMAGE, shot.damage - target.attrs.defense)
            )
            target.hp = max(0, target.hp - damage)
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
                    amount=damage,
                    is_hero=target.is_hero,
                )
            )
            if shot.crit:
                world.emit(Event(EventKind.CRIT, target.pos, target.id,
                                 amount=damage, is_hero=target.is_hero))
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
