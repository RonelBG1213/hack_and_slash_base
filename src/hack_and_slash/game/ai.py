"""Enemy brains. Each one reads the world and returns an `Intent` -- nothing more.

A brain never moves anything, never deals damage, and never touches a timer. It
answers one question: *what would this thing like to do this tick?* The sim then
puts that request through exactly the same code the player's input goes through,
so an enemy can never do something the hero physically could not -- no gliding
through walls, no attacking during its own recovery.

Five brains, five questions they ask the player:

* **chaser** -- can you make space? Straightforward pressure, walks in and swings.
* **charger** -- are you standing in a line with it? Long telegraph, committed
  dash, sidestep or eat it.
* **archer** -- are you standing still in the open? Keeps its distance, needs
  line of sight, so cover is the answer.
* **flanker** -- is your way out as clear as you think? Closes on an arc rather
  than a line, so backing straight away no longer answers everything in the room.
* **boss** -- all three of the above, chosen by distance, one to an act.
"""

from __future__ import annotations

import math

from ..core.collision import line_of_sight
from ..core.vec2 import Vec2
from . import actions
from .entities import Entity
from .difficulty import NORMAL as NORMAL_DIFFICULTY, Difficulty
from .intent import NOTHING, Intent

#: Extra ticks of pause after a full attack cycle, on top of the weapon's own
#: recovery. This is the difference between an enemy that pressures you and one
#: that never stops swinging.
PAUSE_AFTER_ATTACK = {
    "chaser": 20,
    "charger": 45,
    "archer": 34,
    # A chaser's, and left there deliberately. Cadence was tried as the fix when
    # the demon first broke acts VII-VIII -- 20 to 38, which is most of the way
    # to the charger's -- and it moved not one seed of eight on three separate
    # stages. The dial that mattered was the arc itself; see `flank_degrees`.
    "flanker": 20,
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


def aggro_of(world, entity: Entity) -> float:
    """How far this creature notices the hero from, on this tier.

    One function because two callers need the same answer: the cutoff in
    `decide` that decides whether a creature is awake at all, and the span
    `_flanker` measures its arc against. Read from two places and they can
    disagree -- an arc tapering against the type's radius while the creature
    woke at a scaled one would open its widest offset somewhere other than the
    edge of its own aggro, which is precisely the shape the flanker's recorded
    sweep was tuned around.

    Takes `world` because that is where the tier is, and `decide` already has
    it -- so this costs no signature anywhere.
    """
    return world.difficulty.enemies.scaled_aggro(entity.type.aggro)


def decide(world, entity: Entity) -> Intent:
    """What this enemy wants to do this tick."""
    hero = world.hero
    if hero is None or not hero.is_alive or not entity.is_alive:
        return NOTHING

    to_hero = hero.pos - entity.pos
    distance = to_hero.length()
    if distance > aggro_of(world, entity):
        return NOTHING

    match entity.type.brain:
        case "charger":
            return _charger(world, entity, hero, to_hero, distance)
        case "archer":
            return _archer(world, entity, hero, to_hero, distance)
        case "flanker":
            return _flanker(world, entity, hero, to_hero, distance)
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


def _flanker(world, entity: Entity, hero: Entity, to_hero: Vec2, distance: float) -> Intent:
    """A chaser that will not come at you down a straight line.

    Every other brain in the game approaches on the vector to the hero, which
    means one retreat -- straight backwards -- answers all four at once. The
    measurement is blunt about what that is worth: across the reaction ladder
    what separates a won run from a lost one is *disengaging when hurt*, not
    reflexes. So the only thing in the game that costs the player anything is
    the walk away, and nothing has ever contested it.

    A flanker contests it, and does so without breaking the deal the whole fight
    rests on. It is still slower than every class, so the retreat still works --
    it just stops being free, because the thing following you is arriving from
    somewhere other than where you left it. In a game with no pathing, where kill
    order is already decided by geometry, that is the cheapest way to ask a new
    question: no new verb for the player to learn, just a worse assumption.

    The arc closes as it gets near. At the edge of aggro it is walking almost
    sideways; by the time it is in reach it is coming straight in. A *constant*
    offset would orbit forever and never land a hit, which is why the taper is
    the shape of the thing rather than a refinement of it.

    **The width of the arc is the whole creature**, and it is not a gentle dial.
    Swept on `dark_knight` / stage 36 over eight seeds, 35 degrees clears 8/8 and
    55 clears 3/8; durability and cadence, the two levers the project's recorded
    order reaches for first, moved almost nothing between them. That order is
    right for a creature fighting on the existing axes and says little about one
    that adds an axis -- there, the new axis is the dial.

    See `demon` in `data/entities.json` for why nothing spawns one yet.
    """
    heading = to_hero.normalized()
    strike_range = entity.weapon.reach + hero.radius - REACH_MARGIN

    if distance <= strike_range and _may_attack(entity):
        return Intent(aim=heading, attack=True)

    # 1 at the edge of aggro, 0 at the point it can swing. Through `aggro_of`
    # and not `type.aggro`, so the arc opens widest at the distance the
    # creature actually woke up at -- on a tier that widens aggro the two would
    # otherwise disagree, and the widest offset would land somewhere inside the
    # radius rather than at its edge.
    span = max(1.0, aggro_of(world, entity) - strike_range)
    openness = min(1.0, max(0.0, (distance - strike_range) / span))

    # Which side it comes round is fixed per body, exactly as the archer's drift
    # is (`_archer` above), and for the same reason: anything drawn from `random`
    # here would break seeded replay, and every recorded number in the project
    # rests on a run replaying exactly.
    side = 1.0 if entity.id % 2 == 0 else -1.0
    offset = math.radians(entity.type.flank_degrees) * openness * side

    # Aim stays on the hero even while the feet go elsewhere -- it is a body
    # circling you, not one looking away.
    return Intent(move=heading.rotated(offset), aim=heading)


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


def cooldown_for(entity: Entity, difficulty: Difficulty = NORMAL_DIFFICULTY) -> int:
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
    # The tier scales the *pause* and never `total_ticks`. The telegraph is
    # what makes an attack readable and therefore dodgeable, so shortening it
    # is a different and much harsher change than attacking more often -- and
    # it is the one number `docs/design.md` promises a player can learn.
    #
    # Defaulted rather than required, so every caller and test that predates
    # the monster dials asks the question it always asked and gets the answer
    # it always got.
    return entity.weapon.total_ticks + difficulty.enemies.scaled_pause(pause)
