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
from .attributes import NEUTRAL, PER_MILLE, Attributes
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


def can_use(entity: Entity, weapon_index: int = 0) -> bool:
    """Free to start *that particular* attack.

    The counterpart to `can_dodge`, and deliberately the same shape: being free
    to act is not the same as that attack being available, and conflating the
    two is how a cooldown turns into "the button does nothing and you cannot
    tell why".

    Anything whose attack has no cooldown -- every enemy, every class's light
    attack -- collapses to `can_act`, so this is safe to ask about any body.
    """
    if not can_act(entity):
        return False
    return entity.cooldown_on(weapon_index % len(entity.type.weapons)) <= 0


def begin_attack(
    entity: Entity, facing: float | None = None, weapon_index: int = 0
) -> bool:
    """Start a swing. Returns False when the body was not free to.

    Callers get a bool rather than an exception because "the player mashed
    attack during recovery" is the normal case, not an error. An attack still
    cooling down refuses the same way, and costs nothing -- the check happens
    before facing is committed, so a refused skill does not quietly turn the
    hero to face something.

    `weapon_index` is chosen once, here, and holds for the whole attack. That is
    what keeps a multi-attack body honest: it winds up, hits and recovers on the
    same weapon, so the tell a player read is the attack that lands.
    """
    # Out-of-range would otherwise surface much later as an IndexError from
    # inside the state machine, with nothing pointing back at the brain. Wrapped
    # here rather than at the assignment below, because the cooldown has to be
    # read against the index actually used.
    index = weapon_index % len(entity.type.weapons)
    if not can_use(entity, index):
        return False
    if facing is not None:
        entity.facing = facing

    entity.weapon_index = index
    # Stamped at the start of the swing, so the number in the data is the gap
    # between one attack beginning and the next -- which is what a player counts
    # -- rather than a pause that starts once the recovery has already run.
    cooldown = hasted(entity, entity.weapon)
    if cooldown > 0:
        entity.skill_cooldowns[index] = cooldown

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


def hasted(entity: Entity, weapon) -> int:
    """What this attack's cooldown is stamped at, buff haste included.

    **A buff never hastes its own gate**, and that is the whole safety story of
    this feature rather than a detail. Let it, and pressing the slot on cooldown
    shortens the wait for the next press, which shortens it again -- a ratchet
    that ends with the buff permanently live. Refusing it keeps
    `0 < buff_ticks < cooldown` a *static* property of the content files, which
    is what `test_a_buff_cannot_still_be_live_when_its_slot_comes_back` checks,
    instead of something that depends on how much haste a body happens to have
    when the key is pressed.

    Keyed on `weapon.is_buff` and not on the slot index, so it stays true if the
    buff ever moves off Q.

    Floor division on whole ticks, like every other duration in the project, and
    never below 1 -- a cooldown rounded to zero is an attack with no cooldown,
    which is the one thing index 0 is supposed to be alone in being.
    """
    cooldown = weapon.cooldown
    if cooldown <= 0 or weapon.is_buff or entity.buff_haste <= 0:
        return cooldown
    return max(1, cooldown * (PER_MILLE - entity.buff_haste) // PER_MILLE)


def apply_buff(entity: Entity) -> None:
    """Grant this body whatever its current attack buffs it with.

    Called when the active window opens, beside the swing and the arrow, so a
    buff costs the same windup it always did and is lost to an interrupt in the
    same way -- `interrupt` cancels a WINDUP, and a cancelled cast never reaches
    here. Being able to be hit out of it is what keeps the commitment real.

    **Replaces rather than stacks.** Every buff in the game is shorter than the
    cooldown that gates it -- pinned by
    `test_a_buff_cannot_still_be_live_when_its_slot_comes_back` -- so a second
    cast cannot arrive while the first is live, and replacing is the reading
    that stays correct if that ever stops being true. Adding would let one slot
    ratchet itself upwards by being pressed on time.

    A no-op for the hundreds of enemy bodies a run steps through: `is_buff` is
    False on every attack in the game but the five in the Q slot.
    """
    weapon = entity.weapon
    if not weapon.is_buff:
        return
    entity.buff = weapon.buff
    entity.buff_ticks = weapon.buff_ticks
    entity.buff_haste = weapon.buff_haste


def apply_status(entity: Entity, block: Attributes, ticks: int) -> None:
    """Put a timed block on a body somebody else hit.

    Takes the block and the duration rather than the weapon, because the
    projectile path has no weapon in scope by the time a shot lands -- an arrow
    carries `owner_id` and the owner may be dead and culled. So `Projectile`
    carries its own copy of these two, exactly as it already carries `damage`
    and `knockback`.

    **Replaces rather than stacks**, for the reason `apply_buff` replaces: a
    status that added would let an attack ratchet itself upward by being landed
    on time, and replacing is the reading that stays correct when two different
    attacks inflict two different things.

    A no-op for all but three attacks in the shipped game, and for every attack
    the reference bot presses: `inflict_ticks` is zero on every light attack and
    on every enemy weapon, which is what makes this call free on every tick the
    recorded grid has ever measured.
    """
    if ticks <= 0:
        return
    entity.status = block
    entity.status_ticks = ticks


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

    # Reset to the shared singleton and not to `Attributes()`, because
    # `Entity.attrs` tests `self.buff is NEUTRAL` by identity -- an equal-but-
    # distinct block would leave every subsequent tick paying for a sum of
    # zeroes. Cleared on the tick the counter reaches zero rather than lazily in
    # `attrs`, so the identity holds from the moment the buff ends instead of
    # from the next time somebody happens to ask.
    if entity.buff_ticks > 0:
        entity.buff_ticks -= 1
        if entity.buff_ticks == 0:
            entity.buff = NEUTRAL
            entity.buff_haste = 0

    # The same shape for the block somebody else applied, on its own timer.
    # Separate from the buff above rather than folded into it -- see the note on
    # `Entity.status` for why the two may never share a slot.
    if entity.status_ticks > 0:
        entity.status_ticks -= 1
        if entity.status_ticks == 0:
            entity.status = NEUTRAL

    # Empty for anything without skills, so this costs nothing on the hundreds
    # of enemy bodies a run steps through. Entries are left at zero rather than
    # removed: the HUD reads them every frame, and a key that vanishes is one
    # more thing for the drawing code to have an opinion about.
    for index, remaining in entity.skill_cooldowns.items():
        if remaining > 0:
            entity.skill_cooldowns[index] = remaining - 1
