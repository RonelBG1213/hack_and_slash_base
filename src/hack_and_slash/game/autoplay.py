"""A reference hero: plays the game badly, but plays it.

Two jobs. It is the regression net -- if a policy this crude can no longer clear
the arena, something in the numbers drifted. And it is the measuring instrument
behind `tools/balance.py`, which is why it lives here in the package rather than
in the test that first needed it.

**On reading its results.** A bot is not a person. This one has perfect
information and, at `reaction_ticks=0`, perfect reflexes -- it answers a telegraph
on the tick it opens. It is also far worse than a person at positioning: it walks
at the nearest enemy and has no idea a pillar exists. So a comfortable win here
does not mean the fight is easy, and that ambiguity is exactly what
`reaction_ticks` is for. Degrading the one superhuman thing about it turns "is
this too hard?" into a question with a number attached.

Pure logic, like everything else in `game/` -- no pygame, so the whole thing runs
headless.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.collision import path_is_clear
from ..core.vec2 import Vec2
from . import actions
from .entities import ActionState, Entity
from .intent import NOTHING, Intent
from .sim import step
from .world import Outcome

#: Below this fraction of health the policy stops trading and backs off.
CAUTIOUS_BELOW = 0.45

#: How close an incoming attack has to be before it is worth rolling away from.
DANGER_RADIUS = 46.0

#: Struck off the nearest enemy's reach so the policy commits from inside its
#: range rather than at the exact edge, where any drift is a whiff.
REACH_MARGIN = 4.0

#: Rough human reference points, in ticks at 60/sec. Used by tools/balance.py.
#: These are anchors for comparison, not claims about any particular person --
#: what matters is that the fight gets harder as the number rises.
REACTION_PERFECT = 0  # reacts on the tick a telegraph opens
REACTION_SHARP = 12  # ~200ms, a decent reaction to a clear tell
REACTION_SLOPPY = 24  # ~400ms, distracted or reading the wrong enemy


@dataclass(frozen=True)
class Autoplay:
    """Close in, swing when in range, roll away from anything about to land.

    `reaction_ticks` is how long after an attack *begins* this hero notices it.
    Modelled as elapsed time since the telegraph opened rather than as a delayed
    world snapshot: no buffers, no randomness, and the sim stays reproducible.

    A reaction slower than an attack's windup means that attack cannot be dodged
    at all, which is the correct consequence rather than a flaw in the model --
    short tells are supposed to punish slow reactions.
    """

    reaction_ticks: int = REACTION_PERFECT

    def __call__(self, world) -> Intent:
        hero = world.hero
        if hero is None or not hero.is_alive:
            return NOTHING

        enemies = world.enemies()
        if not enemies:
            return NOTHING

        threat = self._noticed_threat(hero, enemies)
        if threat is not None and hero.dodge_cooldown <= 0 and actions.can_act(hero):
            away = (hero.pos - threat.pos).normalized()
            return Intent(
                move=away, aim=(threat.pos - hero.pos).normalized(), dodge=True
            )

        target = min(enemies, key=lambda e: e.pos.distance_sq_to(hero.pos))
        toward = (target.pos - hero.pos).normalized()
        distance = hero.pos.distance_to(target.pos)
        strike_range = hero.weapon.reach + target.radius - REACH_MARGIN

        if hero.health_fraction < CAUTIOUS_BELOW and distance < strike_range * 1.6:
            # Hurt: back off and let the dodge come off cooldown rather than trade.
            return Intent(move=-toward, aim=toward)

        if distance <= strike_range:
            return Intent(aim=toward, attack=True)

        return Intent(move=self._approach(world, hero, target), aim=toward)

    def _approach(self, world, hero: Entity, target: Entity) -> Vec2:
        """A direction that actually gets closer, pillars included.

        Walking straight at the target is right in the open and wrong the moment
        anything is in the way: nothing in this game paths around walls, so a
        hero and an enemy on opposite sides of a pillar will stand there pushing
        into it until the tick limit. A person walks round. Without this the bot
        cannot finish a stage that a player finds trivial, and the difficulty
        bracket ends up measuring the bot rather than the game.

        Deliberately the cheapest thing that works -- probe each way round and
        take the side that opens a clear line. It is not pathfinding and is not
        trying to be; a U-shaped wall would still defeat it.
        """
        toward = (target.pos - hero.pos).normalized()
        tile = world.level.tile

        if path_is_clear(hero.pos, target.pos, world.is_solid, tile):
            return toward

        sideways = toward.perpendicular()
        for side in (1.0, -1.0):
            probe = hero.pos + sideways * (side * tile * 2.0)
            if path_is_clear(probe, target.pos, world.is_solid, tile):
                # Angled rather than straight sideways, so it keeps closing
                # while it clears the obstacle.
                return (toward + sideways * (side * 1.5)).normalized()

        # Neither way round helps from here. Slide one way -- fixed, not random,
        # so a seeded run still replays exactly.
        return sideways

    def _noticed_threat(self, hero: Entity, enemies: list[Entity]) -> Entity | None:
        """The nearest attack that is close enough to land, and old enough to see.

        "Close enough to land" is measured against the attack in progress, not a
        flat radius. That distinction stops a pathology rather than shaving a
        number: a boss is winding up or swinging roughly half the time, so a hero
        that rolls at any nearby attack rolls forever and never swings back. It
        would dodge a volley it is standing on top of, which is not a danger, and
        die having never attacked.
        """
        for enemy in enemies:
            elapsed = _ticks_since_attack_began(enemy)
            if elapsed < 0 or elapsed < self.reaction_ticks:
                continue
            if enemy.pos.distance_to(hero.pos) <= _threat_range(enemy, hero):
                return enemy
        return None


def _threat_range(enemy: Entity, hero: Entity) -> float:
    """How far the attack this enemy is mid-way through can actually reach.

    A projectile attack returns zero: rolling is not how you avoid an arrow, and
    treating one as a dodge trigger is what makes a hero stand in front of an
    archer rolling until the cooldown runs out. You move instead, which the rest
    of the policy already does.
    """
    weapon = enemy.weapon
    if weapon.projectile:
        return 0.0

    reach = weapon.reach + hero.radius + enemy.radius
    if weapon.is_charge:
        # A charge threatens the whole line it is about to cover, not just the
        # length of the horns.
        reach += weapon.charge_speed * weapon.active
    return min(reach, DANGER_RADIUS + reach)


def _ticks_since_attack_began(enemy: Entity) -> int:
    """How long this enemy has been attacking, or -1 if it is not.

    Measured from the start of the telegraph, so the delay covers the whole
    attack rather than restarting when the hitbox opens. Counting from the
    active window instead would make a long swing easier to react to than a
    short one, which is backwards.
    """
    if enemy.state is ActionState.WINDUP:
        return enemy.state_ticks
    if enemy.state is ActionState.ACTIVE:
        return enemy.weapon.windup + enemy.state_ticks
    return -1


@dataclass(frozen=True)
class Reckless:
    """Walks at the nearest enemy swinging, and never does anything else.

    No dodging, no retreating, no respect for a telegraph. It exists to answer
    one question -- *does the arena punish playing badly?* -- and it turns out to
    be a far better instrument for that than a slow reaction time is.

    The reason is worth recording. `Autoplay(reaction_ticks=40)` was the obvious
    way to model a bad player, but measurement showed reaction time barely moves
    this fight: a hero that never dodges finishes *healthier* than one with
    perfect reflexes, because rolling costs uptime and lengthens the fight. What
    actually separates winning from losing here is disengaging when hurt. So the
    difficulty ceiling is defined by refusing to disengage, not by reacting late.
    """

    def __call__(self, world) -> Intent:
        hero = world.hero
        if hero is None or not hero.is_alive:
            return NOTHING

        enemies = world.enemies()
        if not enemies:
            return NOTHING

        target = min(enemies, key=lambda e: e.pos.distance_sq_to(hero.pos))
        toward = (target.pos - hero.pos).normalized()
        return Intent(move=toward, aim=toward, attack=True)


#: The reference for "a competent player", and deliberately *not* the
#: zero-latency one.
#:
#: A hero that answers every telegraph on the tick it opens is not skilled, it is
#: twitchy, and against something that is winding up or swinging half the time --
#: a boss -- it rolls perpetually and never swings back. That is an artifact of
#: the instrument rather than a fact about the game, and it stayed invisible
#: while every fight was ordinary enemies with gaps between their attacks.
#:
#: Twelve ticks is about two hundred milliseconds: a real reaction to a clear
#: tell, and enough of one that dodging is a decision rather than a reflex.
autoplay = Autoplay(reaction_ticks=REACTION_SHARP)

#: The twitchy end, kept for the reaction ladder. Useful as a comparison, and a
#: standing reminder of why it is not the default.
twitchy = Autoplay(reaction_ticks=REACTION_PERFECT)

#: The other end of the bracket.
reckless = Reckless()


def play_out(world, policy=autoplay, limit: int = 9000) -> int:
    """Run a world to its conclusion. Returns the tick it ended on.

    The limit is a guard, not a timeout with meaning: a hero that can no longer
    reach anything should fail a test rather than hang the suite.
    """
    for tick in range(limit):
        if world.outcome is not Outcome.RUNNING:
            return tick
        step(world, policy(world))
    return limit
