"""Starting and advancing what a body is doing. No world, no damage, no pygame.

A swing is a state machine, not an event:

    IDLE -> WINDUP -> ACTIVE -> RECOVERY -> IDLE
             tell     hitbox    punishable

Only `ACTIVE` can hit anything, and that is the whole design. **Windup** is the
tell -- it is what makes an attack readable and therefore dodgeable, and it is
the first number to change when an enemy feels unfair. **Recovery** is the price
of missing: it is why whiffing a swing into empty air is a mistake rather than a
free action.

Timings live in `data/weapons.json`, so tuning the feel of the game never
touches this file.
"""

from __future__ import annotations

from ..core.vec2 import ZERO, Vec2, from_angle
from .entities import ActionState, Entity

#: How much of your walking speed you keep mid-swing. Not zero -- rooting the
#: hero for the length of every attack reads as unresponsive -- but low enough
#: that committing to a swing is committing to a position.
ATTACK_MOVE_SCALE = 0.35

#: Ticks unable to act after taking a hit. Deliberately short: long enough that
#: getting hit interrupts what you were doing, short enough that being surrounded
#: is dangerous rather than a death sentence you cannot act during.
STAGGER_TICKS = 5

#: How long a body flashes white after being hit. Cosmetic; the sim never reads it.
FLASH_TICKS = 6


def can_act(entity: Entity) -> bool:
    """Free to start something new."""
    return entity.state is ActionState.IDLE and entity.stagger <= 0


def can_dodge(entity: Entity) -> bool:
    return can_act(entity) and entity.type.can_dodge and entity.dodge_cooldown <= 0


def begin_attack(
    entity: Entity, facing: float | None = None, weapon_index: int = 0
) -> bool:
    """Start a swing. Returns False when the body was not free to.

    Callers get a bool rather than an exception because "the player mashed
    attack during recovery" is the normal case, not an error.

    `weapon_index` is chosen once, here, and holds for the whole attack. That is
    what keeps a multi-attack body honest: it winds up, hits and recovers on the
    same weapon, so the tell a player read is the attack that lands.
    """
    if not can_act(entity):
        return False
    if facing is not None:
        entity.facing = facing

    # Out-of-range would otherwise surface much later as an IndexError from
    # inside the state machine, with nothing pointing back at the brain.
    entity.weapon_index = weapon_index % len(entity.type.weapons)
    entity.state = ActionState.WINDUP
    entity.state_ticks = 0
    # A fresh swing forgets what the last one hit, which is what stops a
    # multi-tick active window dealing its damage once per tick.
    entity.hit_ids.clear()

    if entity.weapon.is_charge:
        # A charge locks its heading now, at the *start* of the telegraph, not
        # when the dash fires. That is what gives the player the whole windup to
        # step out of the line -- lock it at the end and the tell tells you
        # nothing you can act on.
        entity.dash_dir = from_angle(entity.facing)
    return True


def begin_dodge(entity: Entity, direction: Vec2) -> bool:
    """Roll. Invulnerability starts immediately, not part-way through.

    Front-loading the i-frames matters: a dodge whose invulnerability begins a
    few ticks in punishes reacting at the last moment, which is exactly when a
    player reacts.
    """
    if not can_dodge(entity):
        return False

    heading = direction.normalized()
    if heading.is_zero():
        # Dodging with no direction held rolls the way you are looking, rather
        # than doing nothing and eating the cooldown.
        heading = from_angle(entity.facing)

    entity.state = ActionState.DODGING
    entity.state_ticks = 0
    entity.dash_dir = heading
    entity.facing = heading.angle()
    entity.iframes = entity.type.iframe_ticks
    return True


def state_duration(entity: Entity) -> int:
    """How many ticks the current state lasts."""
    weapon = entity.weapon
    match entity.state:
        case ActionState.WINDUP:
            return weapon.windup
        case ActionState.ACTIVE:
            return weapon.active
        case ActionState.RECOVERY:
            return weapon.recovery
        case ActionState.DODGING:
            return entity.type.dodge_ticks
        case _:
            return 0


def advance(entity: Entity) -> ActionState | None:
    """Move the state machine on by one tick.

    Called at the *end* of a tick, after hitboxes have been resolved, so a state
    is always live for the full number of ticks its data says it is. Returns the
    state just entered, or None if nothing changed -- the caller needs the
    transition to know when to open a hitbox or loose an arrow.
    """
    if entity.state is ActionState.IDLE:
        return None

    entity.state_ticks += 1
    if entity.state_ticks < state_duration(entity):
        return None

    entity.state_ticks = 0
    match entity.state:
        case ActionState.WINDUP:
            entity.state = ActionState.ACTIVE
        case ActionState.ACTIVE:
            entity.state = ActionState.RECOVERY
        case ActionState.RECOVERY:
            entity.state = ActionState.IDLE
        case ActionState.DODGING:
            entity.state = ActionState.IDLE
            entity.dash_dir = ZERO
            # The cooldown starts when the roll ends, so back-to-back dodging
            # is gated by the gap between rolls rather than their length.
            entity.dodge_cooldown = entity.type.dodge_cooldown
        case _:
            return None
    return entity.state


def interrupt(entity: Entity) -> None:
    """Cancel a swing that has not opened its hitbox yet.

    Being hit during your windup loses you the attack; being hit once the blade
    is already out does not. That asymmetry is what makes trading blows a real
    choice instead of always losing to whoever swung first.
    """
    if entity.state is ActionState.WINDUP:
        entity.state = ActionState.IDLE
        entity.state_ticks = 0
        entity.hit_ids.clear()


def movement_scale(entity: Entity) -> float:
    """Fraction of walking speed available in the current state."""
    if entity.stagger > 0:
        return 0.0
    match entity.state:
        case ActionState.WINDUP | ActionState.ACTIVE | ActionState.RECOVERY:
            return ATTACK_MOVE_SCALE
        case ActionState.DODGING:
            return 0.0  # the dash provides the motion; input does not add to it
        case _:
            return 1.0


def tick_timers(entity: Entity) -> None:
    """Count down everything that expires, once per tick."""
    if entity.iframes > 0:
        entity.iframes -= 1
    if entity.dodge_cooldown > 0:
        entity.dodge_cooldown -= 1
    if entity.stagger > 0:
        entity.stagger -= 1
    if entity.attack_cooldown > 0:
        entity.attack_cooldown -= 1
    if entity.flash > 0:
        entity.flash -= 1
