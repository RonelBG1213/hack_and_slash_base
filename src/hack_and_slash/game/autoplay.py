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
        strike_range = hero.type.weapon.reach + target.radius - REACH_MARGIN

        if hero.health_fraction < CAUTIOUS_BELOW and distance < strike_range * 1.6:
            # Hurt: back off and let the dodge come off cooldown rather than trade.
            return Intent(move=-toward, aim=toward)

        if distance <= strike_range:
            return Intent(aim=toward, attack=True)

        return Intent(move=toward, aim=toward)

    def _noticed_threat(self, hero: Entity, enemies: list[Entity]) -> Entity | None:
        """The nearest attack close enough to matter and old enough to have seen."""
        for enemy in enemies:
            if enemy.pos.distance_to(hero.pos) > DANGER_RADIUS:
                continue
            elapsed = _ticks_since_attack_began(enemy)
            if elapsed >= 0 and elapsed >= self.reaction_ticks:
                return enemy
        return None


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
        return enemy.type.weapon.windup + enemy.state_ticks
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


#: The default instrument: perfect reflexes, no positioning sense. Matches the
#: behaviour these tests were written against before latency existed.
autoplay = Autoplay()

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
