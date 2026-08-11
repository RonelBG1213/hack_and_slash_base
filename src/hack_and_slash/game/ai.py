"""Enemy brains. Each one reads the world and returns an `Intent` -- nothing more.

A brain never moves anything, never deals damage, and never touches a timer. It
answers one question: *what would this thing like to do this tick?* The sim then
puts that request through exactly the same code the player's input goes through,
so an enemy can never do something the hero physically could not -- no gliding
through walls, no attacking during its own recovery.

Three brains, three questions they ask the player:

* **chaser** -- can you make space? Straightforward pressure, walks in and swings.
* **charger** -- are you standing in a line with it? Long telegraph, committed
  dash, sidestep or eat it.
* **archer** -- are you standing still in the open? Keeps its distance, needs
  line of sight, so cover is the answer.
"""

from __future__ import annotations

from ..core.collision import line_of_sight
from ..core.vec2 import Vec2
from . import actions
from .entities import Entity
from .intent import NOTHING, Intent

#: Extra ticks of pause after a full attack cycle, on top of the weapon's own
#: recovery. This is the difference between an enemy that pressures you and one
#: that never stops swinging.
PAUSE_AFTER_ATTACK = {
    "chaser": 20,
    "charger": 45,
    "archer": 34,
    "boss": 40,
}

#: Which of the boss's weapons is which. Positional in `data/entities.json`, so
#: named here rather than scattered as bare indices through the brain.
BOSS_SWEEP, BOSS_CRUSH, BOSS_VOLLEY = 0, 1, 2

#: Health fraction below which the boss stops pausing between attacks. The whole
#: phase system: no new moves to learn at the moment the player is least able to
#: learn them, just less room to breathe.
BOSS_ENRAGE_BELOW = 0.5

#: How much of its pause the boss keeps once enraged.
BOSS_ENRAGE_PAUSE_SCALE = 0.35

#: How much closer than its maximum reach an enemy wants to be before swinging.
#: Attacking at the exact edge of reach means any drift at all is a whiff.
REACH_MARGIN = 3.0


def decide(world, entity: Entity) -> Intent:
    """What this enemy wants to do this tick."""
    hero = world.hero
    if hero is None or not hero.is_alive or not entity.is_alive:
        return NOTHING

    to_hero = hero.pos - entity.pos
    distance = to_hero.length()
    if distance > entity.type.aggro:
        return NOTHING

    match entity.type.brain:
        case "charger":
            return _charger(world, entity, hero, to_hero, distance)
        case "archer":
            return _archer(world, entity, hero, to_hero, distance)
        case "boss":
            return _boss(world, entity, hero, to_hero, distance)
        case _:
            return _chaser(world, entity, hero, to_hero, distance)


def _chaser(world, entity: Entity, hero: Entity, to_hero: Vec2, distance: float) -> Intent:
    heading = to_hero.normalized()
    strike_range = entity.weapon.reach + hero.radius - REACH_MARGIN

    if distance <= strike_range and _may_attack(entity):
        return Intent(aim=heading, attack=True)

    # Keep walking during your own windup. A chaser that stops dead the instant
    # it decides to swing is trivially backed away from.
    return Intent(move=heading, aim=heading)


def _charger(world, entity: Entity, hero: Entity, to_hero: Vec2, distance: float) -> Intent:
    heading = to_hero.normalized()

    # Committing to a charge means committing to a straight line, so it is only
    # worth starting if the line is actually clear.
    in_range = distance <= entity.type.charge_range
    can_see = line_of_sight(entity.pos, hero.pos, world.is_solid, world.level.tile)

    if in_range and can_see and _may_attack(entity):
        return Intent(aim=heading, attack=True)

    if distance > entity.type.charge_range:
        return Intent(move=heading, aim=heading)

    # Inside charge range but not ready: hold the line and stare, which reads as
    # a threat and lets the player see the next charge coming.
    return Intent(aim=heading)


def _archer(world, entity: Entity, hero: Entity, to_hero: Vec2, distance: float) -> Intent:
    heading = to_hero.normalized()
    can_see = line_of_sight(entity.pos, hero.pos, world.is_solid, world.level.tile)

    if not can_see:
        # No shot from here. Close in until the pillar is no longer in the way --
        # which is what turns cover into a temporary advantage rather than a
        # permanent one.
        return Intent(move=heading, aim=heading)

    if distance < entity.type.retreat_range:
        return Intent(move=-heading, aim=heading)

    if distance > entity.type.preferred_range:
        return Intent(move=heading, aim=heading)

    if _may_attack(entity):
        return Intent(aim=heading, attack=True)

    # At a comfortable distance with nothing to do: sidestep. Which way is fixed
    # per enemy rather than random, so a seeded run replays exactly.
    drift = heading.perpendicular() * (1.0 if entity.id % 2 == 0 else -1.0)
    return Intent(move=drift * 0.6, aim=heading)


def _boss(world, entity: Entity, hero: Entity, to_hero: Vec2, distance: float) -> Intent:
    """Three attacks, each answering a different distance.

    The choice is made from range alone, and deliberately so: a boss that picks
    at random is noise, and a player cannot learn noise. Standing close means the
    sweep, standing in a line at mid range means the crush, hanging back means
    the volley -- so every position has a known answer, and the fight becomes
    about moving between them.

    It has no separate 'phase two' moveset. Below half health it simply stops
    pausing, which raises the pressure without asking the player to learn
    something new at the worst possible moment.
    """
    heading = to_hero.normalized()

    if not _may_attack(entity):
        # Between attacks it closes, slowly. Its speed is the reason there is
        # any breathing room at all, so it never needs to hurry.
        if distance > entity.type.retreat_range:
            return Intent(move=heading, aim=heading)
        return Intent(aim=heading)

    sweep = entity.type.weapons[BOSS_SWEEP]
    sweep_range = sweep.reach + hero.radius - REACH_MARGIN
    can_see = line_of_sight(entity.pos, hero.pos, world.is_solid, world.level.tile)

    if distance <= sweep_range:
        return Intent(aim=heading, attack=True, weapon=BOSS_SWEEP)

    if distance <= entity.type.charge_range and can_see:
        return Intent(aim=heading, attack=True, weapon=BOSS_CRUSH)

    if can_see:
        return Intent(aim=heading, attack=True, weapon=BOSS_VOLLEY)

    # Nothing to shoot through a wall at; walk until there is.
    return Intent(move=heading, aim=heading)


def _may_attack(entity: Entity) -> bool:
    return actions.can_act(entity) and entity.attack_cooldown <= 0


def cooldown_for(entity: Entity) -> int:
    """Ticks before this enemy may swing again, counted from the swing starting.

    Includes the attack's own length, so the pause is time spent *idle* rather
    than time the animation was already using.

    A wounded boss pauses less. That is the entire phase change -- the moveset
    and the telegraphs are untouched, so everything the player learned in the
    first half still holds, there is just less room between attacks.
    """
    pause = PAUSE_AFTER_ATTACK.get(entity.type.brain, 20)
    if entity.type.brain == "boss" and entity.health_fraction < BOSS_ENRAGE_BELOW:
        pause = int(pause * BOSS_ENRAGE_PAUSE_SCALE)
    return entity.weapon.total_ticks + pause
