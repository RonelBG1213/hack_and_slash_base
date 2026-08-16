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

from dataclasses import dataclass, field, replace

from ..core.collision import path_is_clear
from ..core.vec2 import Vec2
from . import actions, jobs, skills
from .entities import ActionState, Entity
from .intent import NOTHING, Intent
from .sim import step
from .world import Outcome

#: Below this fraction of health the policy stops trading and backs off.
CAUTIOUS_BELOW = 0.45

#: Struck off the nearest enemy's reach so the policy commits from inside its
#: range rather than at the exact edge, where any drift is a whiff.
REACH_MARGIN = 4.0

#: Where a ranged class wants to stand, and how close it lets something get
#: before giving ground. A projectile weapon has `reach: 0` -- the number the
#: melee branch engages at -- so without these a bow hero would walk to a pixel
#: from a grunt before firing, and every measurement of the Archer and the
#: Magician would be a measurement of how badly they melee.
#:
#: 120 sits inside the enemy bowman's preferred 140, so the bot wins that trade
#: by standing where it can shoot and be shot at rather than by out-ranging
#: anything. Deliberately not the maximum range: a policy that snipes from the
#: far corner would measure the arena's sightlines instead of the class.
RANGED_PREFERRED = 120.0
RANGED_TOO_CLOSE = 70.0

#: Rough human reference points, in ticks at 60/sec. Used by tools/balance.py.
#: These are anchors for comparison, not claims about any particular person --
#: what matters is that the fight gets harder as the number rises.
REACTION_PERFECT = 0  # reacts on the tick a telegraph opens
REACTION_SHARP = 12  # ~200ms, a decent reaction to a clear tell
REACTION_SLOPPY = 24  # ~400ms, distracted or reading the wrong enemy


@dataclass(frozen=True)
class Autoplay:
    """Close in, swing when in range, roll away from anything about to land.

    Or, for a class that shoots: hold a distance, need a clear line, give ground
    when closed down. Which of the two it plays is read off the weapon, not
    configured -- `see _ranged`.

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

        if hero.weapon.projectile:
            # Strictly separate from the melee branch below, which is left
            # exactly as it was. The recorded numbers for the melee classes must
            # not move because a ranged class was added.
            return self._ranged(world, hero, target, toward, distance)

        strike_range = hero.weapon.reach + target.radius - REACH_MARGIN

        if self._should_give_ground(hero, distance < strike_range * 1.6):
            # Hurt: back off and let the dodge come off cooldown rather than trade.
            return Intent(move=self._away_from(world, hero, toward), aim=toward)

        if distance <= strike_range:
            return Intent(aim=toward, attack=True)

        return Intent(move=self._approach(world, hero, target), aim=toward)

    def _should_give_ground(self, hero: Entity, too_close: bool) -> bool:
        """Whether a hurt hero should be backing away instead of trading.

        The health check alone is not enough, and the bug it hid took a
        twenty-stage campaign to expose. Backing away from something that
        follows you keeps you inside its range forever, so the condition stayed
        true, so the hero retreated again -- for the rest of the fight. Against
        four short stages nothing lived long enough for that to matter. Against
        a boss with 175 health it is a death spiral: the measured runs ended with
        the hero pinned in a corner at 20hp having not swung in four hundred
        ticks, and the boss still on two thirds of its bar.

        The dodge cooldown is what ends it, which is what the comment at the
        call site always claimed this was for -- *let the dodge come off
        cooldown* is a thing that finishes, and "retreat while hurt" is not. Once
        the roll is available the hero re-engages, which is both what a person
        does and what makes the retreat a tactic rather than a surrender.
        """
        return (
            hero.health_fraction < CAUTIOUS_BELOW
            and hero.dodge_cooldown > 0
            and too_close
        )

    def _away_from(self, world, hero: Entity, toward: Vec2) -> Vec2:
        """A retreat that does not end in a corner.

        The counterpart to `_approach`, and needed for the same reason: this
        policy has no idea walls exist. Backing straight away from something
        that follows you works in the open and is suicide in a room -- and every
        boss in the game pushes you backwards, so every boss fight ended with
        the hero flattened against the far wall taking free hits.

        It is not pathfinding, and like `_approach` it is not trying to be. Probe
        straight back; if that is wall, slide along it. A player would do the
        same thing without thinking about it, which is rather the point -- what
        was being measured before was the bot's inability to do it, not the
        arena's difficulty.
        """
        away = -toward
        tile = world.level.tile
        reach = tile * 1.5

        if path_is_clear(hero.pos, hero.pos + away * reach, world.is_solid, tile):
            return away

        sideways = away.perpendicular()
        for side in (1.0, -1.0):
            candidate = sideways * side
            if path_is_clear(
                hero.pos, hero.pos + candidate * reach, world.is_solid, tile
            ):
                return candidate

        # Boxed in on three sides. Keep pushing back rather than standing still:
        # something is about to land either way, and the wall does not hit back.
        return away

    def _ranged(
        self, world, hero: Entity, target: Entity, toward: Vec2, distance: float
    ) -> Intent:
        """The same policy, for a class whose damage does not need to touch.

        Structurally this is the enemy archer brain in `ai.py` played from the
        other side: hold a distance, need a clear line, give ground when closed
        down. The differences are both deliberate.

        It keeps shooting while retreating. A projectile spawns on the body, so
        a bow works perfectly well point blank -- being close is a bad *place*
        for the class, not a broken one. Holding fire while backing away would
        invent a weakness the game does not have, and worse, it would stall: a
        hero reversing into a corner with a rat on it would never fire again and
        the stage would end on the tick limit rather than on the balance.

        It requires `path_is_clear` before committing. A shot spends itself on
        the first wall it meets, so firing through a pillar is not a wasted
        opportunity, it is no attack at all -- and a policy that cannot tell the
        difference would report a pillared arena as unclearable for the Archer
        while a player walks two steps and shoots.
        """
        clear = path_is_clear(hero.pos, target.pos, world.is_solid, world.level.tile)

        if distance < RANGED_TOO_CLOSE:
            return Intent(
                move=self._away_from(world, hero, toward), aim=toward, attack=clear
            )

        if self._should_give_ground(hero, distance < RANGED_PREFERRED):
            # Hurt and inside its own comfortable range: give ground rather than
            # stand and trade, which is the melee branch's rule as well.
            return Intent(
                move=self._away_from(world, hero, toward), aim=toward, attack=clear
            )

        if distance > RANGED_PREFERRED or not clear:
            return Intent(move=self._approach(world, hero, target), aim=toward)

        return Intent(aim=toward, attack=True)

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

    A charge threatens the whole line it is about to cover -- for a charger that
    is 127px, near enough eight tiles -- and answering all of it is deliberate
    rather than an oversight.

    That is worth stating because the code used to say otherwise. This returned
    `min(reach, DANGER_RADIUS + reach)`, next to a `DANGER_RADIUS = 46.0`
    documented as "how close an incoming attack has to be before it is worth
    rolling away from". The expression can never fire -- the right-hand side
    exceeds the left for any positive constant -- so the cap described in that
    comment had never once been applied, and the full line was always used.

    Implementing it was tried and is worse. Capping the charge extension at 46
    costs the Archer a run it otherwise completes (3/3 -> 2/3 on `CLASS_SEEDS`)
    and costs the Magician stages 13 and 17, while fixing nothing: this policy
    has no pathfinding and cannot sidestep late, so it has to answer a charge
    while there is still room to. The dead constant is therefore deleted rather
    than honoured, and the behaviour is exactly what it has always been.
    """
    weapon = enemy.weapon
    if weapon.projectile:
        return 0.0

    reach = weapon.reach + hero.radius + enemy.radius
    if weapon.is_charge:
        reach += weapon.charge_speed * weapon.active
    return reach


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


@dataclass(frozen=True)
class Skilful:
    """`Autoplay`, plus it spends every skill the moment one is available.

    A separate instrument rather than a change to `Autoplay`, and that is the
    whole point of it. The reference policy presses one button, which is why
    every recorded number in this project still means what it meant before the
    other three slots existed. Teaching it to use them would move all hundred
    cells of the class-by-stage grid at once, and there would be no way to tell
    which of the two changes did it.

    So this measures the *ceiling* instead: how much easier the game gets for a
    hero that never once holds a skill back. It is not how a person plays -- a
    person saves an ultimate for the boss -- and it is not meant to be. It is
    the upper bound, and the question it answers is whether four buttons broke
    the difficulty curve, not whether they are fun.

    The one piece of judgement in it is refusing a melee skill that cannot
    reach. Otherwise the ranged classes would spend the run kicking at things
    forty pixels away, and the measurement would be of that rather than of the
    skills.

    **Read its losses carefully -- some of them are not about skills.** Measured
    over the twenty stages against all five classes, eight of a hundred cells
    moved when the skills were switched on and every one moved downward. Six are
    real deaths, and the reason is worth having: a heavy commits for 41-57 ticks
    and an ultimate for 46-74, and the hero cannot dodge during any of them, so
    spending one at the wrong moment is most of a second of standing still with
    the room still moving.

    The other two -- the Knight and the Archer on stage 9 -- are not deaths at
    all. Both hit the tick limit with the hero on most of its health and every
    remaining enemy at full health, three hundred pixels away, behind a wall and
    outside its own aggro radius. Nothing in this game paths around walls, and
    this policy's `_approach` is two probes and a shrug; the skills simply moved
    the fight somewhere that limitation bites. That is a measurement of the
    missing pathfinding, not of a skill, and reading it as balance would be
    reading it wrong.
    """

    base: Autoplay = field(default_factory=lambda: Autoplay(reaction_ticks=REACTION_SHARP))

    def __call__(self, world) -> Intent:
        intent = self.base(world)
        if not intent.attack:
            return intent

        hero = world.hero
        enemies = world.enemies()
        if hero is None or not enemies:
            return intent

        target = min(enemies, key=lambda e: e.pos.distance_sq_to(hero.pos))
        slot = self._best_available(hero, hero.pos.distance_to(target.pos), target.radius)
        return intent if slot == intent.weapon else replace(intent, weapon=slot)

    def _best_available(self, hero: Entity, distance: float, target_radius: float) -> int:
        """The most expensive attack that is off cooldown and can connect.

        Highest first, so an ultimate is never passed over for a heavy. Falls
        through to light, which has no cooldown and is always available -- the
        method therefore always returns something, and the caller never has to
        cope with "no attack".
        """
        for slot in reversed(skills.SLOTS):
            if slot >= len(hero.type.weapons):
                continue
            weapon = hero.type.weapons[slot]
            if hero.cooldown_on(slot) > 0:
                continue
            # A projectile carries its own distance; a swing has to be next to
            # the thing. Reach 0 on a non-projectile is not a real attack.
            if not weapon.projectile and distance > weapon.reach + target_radius:
                continue
            return slot
        return skills.LIGHT


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

#: The same competent player with all four buttons. Not the reference and never
#: the default -- it exists to be compared against `autoplay`, so that "how much
#: did skills change the game" is a question with a number attached.
skilful = Skilful()


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


def play_run_out(run, policy=autoplay, limit: int = 240000, job: str = "") -> int:
    """Run a whole campaign to its conclusion. Returns the tick it ended on.

    `play_out` is one arena; this is the layer above it, and it exists because
    a run is no longer a loop anybody can write correctly in three lines. There
    is a decision in the middle of one now, and both callers that drive a run
    without a keyboard -- `tools/balance.py` and the playthrough suite -- have
    to take it at the same moment and in the same way `scenes/play.py` does, or
    they are measuring a game nobody plays.

    `job` names the branch to take at `jobs.PROMOTION_STAGE`. Left empty, this
    promotes into nothing and the run carries on as its base class: that is the
    right default and not a lazy one, because it is what keeps the recorded
    class x stage grid for the first half measuring the same game it always
    measured. A caller that wants the second half has to ask for a branch by
    name, which is also how the advanced grid gets one cell per class.

    A branch that does not descend from the class being played raises out of
    `jobs.promote` rather than being ignored -- a sweep quietly measuring the
    wrong class is the failure worth being loud about.
    """
    for tick in range(limit):
        if run.is_over:
            return tick
        step(run.world, policy(run.world))
        run.settle()
        # Mirrors the scene: the panel opens on the transition into the
        # promotion stage, and `can_promote` is what makes an empty roster of
        # advanced classes turn the whole thing off.
        if run.just_advanced and job and run.at_promotion_point and jobs.can_promote(run):
            jobs.promote(run, run.bestiary[job])
    return limit
