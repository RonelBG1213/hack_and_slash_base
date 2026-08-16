"""Promotion: the second and last decision a run asks for.

The character select picks one of five. Halfway through the campaign that class
forks into two advanced ones, and this is what happens when one is chosen.

**Promotion swaps the type on the live hero rather than building a new world.**
That is not a shortcut, it is forced by the order things happen in: `Run._advance`
constructs the next `World` -- hero included -- and only *then* is `just_advanced`
true and the panel opened. By the time a player is looking at a choice, the body
that choice applies to already exists. So the swap goes through `Entity.type`,
which is a plain field on a mutable dataclass, exactly as the shop's Poultice
already writes `hero.hp`.

**Health carries as a fraction, never as a number.** An advanced class has a
different maximum, so copying the raw value would make promoting into a bigger
class a stealth heal and promoting into a smaller one a stealth wound. Keeping
the proportion means the choice costs and grants nothing on its own -- whatever
state the last stage left you in is the state you fight the last boss in.

Nothing here draws a random number, so neither RNG stream is touched and a
seeded run still replays exactly.

Pure Python -- no pygame. The scene decides *when* to offer this; this decides
what it does.
"""

from __future__ import annotations

from . import skills
from .entities import EntityType

#: The first stage fought as an advanced class -- so the fork is offered on
#: clearing the one before it, which is the Sovereign at the end of act IV.
#:
#: One number rather than a condition spelled out in the scene, because three
#: places need to agree about it: the scene that opens the panel, the run that
#: answers "are we there yet", and the bot that has to promote at the same
#: moment a player would or it is measuring a different game.
#:
#: A stage number, 1-based, matching `Run.stage_number` and everything a player
#: reads. Moving it is a re-tune of everything after it, not a free choice: the
#: campaign either side of this line is balanced against a different hero.
PROMOTION_STAGE = 21


def offers_for(run) -> tuple[EntityType, ...]:
    """The advanced classes this run may promote into, in file order.

    Empty once a run has already promoted, and empty for any class with no
    promotions declared in `data/entities.json` -- which is the whole of the
    feature's off switch. Delete the advanced entries and this returns nothing,
    the panel never opens, and no code has to be removed.

    Order is content: it is the order the panel draws, and therefore which class
    is on key 1.
    """
    if run.job_id:
        return ()
    return run.bestiary.promotions_for(run.hero_type_id)


def can_promote(run) -> bool:
    """Whether there is a choice to offer at all.

    The same question `offers_for` answers, named for the way the scene asks it.
    """
    return bool(offers_for(run))


def promote(run, advanced: EntityType) -> bool:
    """Become `advanced`. Returns False if the run had already promoted.

    Assumes the hero is not mid-swing, which is true wherever this is called
    from -- a stage transition spawns a fresh, idle body. The weapon index and
    hit list are reset anyway, because the alternative if that assumption ever
    stops holding is a hero that winds up one attack and lands another, which is
    the exact failure the boss weapon ordering test exists to prevent elsewhere.
    """
    if run.job_id:
        # A second keypress on the same panel, not a programming error.
        return False

    if advanced.promotes_from != run.hero_type_id:
        # This one *is* a programming error: the panel can only offer what
        # `offers_for` returned, so reaching here means something else called in
        # with a class that does not descend from the one being played.
        raise ValueError(
            f"{advanced.id} promotes from '{advanced.promotes_from}', "
            f"but this run is playing '{run.hero_type_id}'"
        )

    hero = run.world.hero
    if hero is None:
        # A hero who died on the tick the stage was cleared cannot be promoted.
        # Not reachable today -- a cleared stage always leaves one alive -- but
        # `world.hero` is Optional and silently skipping is better than raising
        # at the moment a player pressed a key.
        return False

    # Read before the swap: it is a fraction of the *old* maximum.
    fraction = hero.health_fraction

    hero.type = advanced
    hero.hp = max(1, min(advanced.hp, round(fraction * advanced.hp)))

    # The heavy and ultimate at these indices are different attacks now, so a
    # cooldown left over from the old kit would gate a weapon that never fired.
    hero.skill_cooldowns.clear()
    hero.weapon_index = skills.LIGHT
    hero.hit_ids.clear()

    run.job_id = advanced.id
    return True
