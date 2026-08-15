"""The four attack slots, and the cooldowns that keep them apart.

The mechanism is small -- an index into `type.weapons` and a dict of timers --
and almost all of it already existed for the bosses. What is new is that an
attack can be *refused* for a reason other than the state machine, so most of
what is worth testing is the shape of that refusal: it costs nothing, it lands
on the right slot, and it ends exactly when the data says.

The other half of this file is about what did *not* change. Skills are additive,
and the evidence that they are additive is that every enemy and every light
attack behaves precisely as it did before.
"""

from __future__ import annotations

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import actions, skills
from hack_and_slash.game.entities import ActionState
from hack_and_slash.game.intent import Intent

from .helpers import BESTIARY, add_enemy, enemies_idle, make_world, run

RIGHT = Vec2(1, 0)

KNIGHT = BESTIARY["knight"]
BASH = KNIGHT.weapons[skills.NEUTRAL]
CLEAVE = KNIGHT.weapons[skills.HEAVY]


def knight_world():
    world = make_world()
    return world, world.hero


# --- the gate ----------------------------------------------------------------
def test_a_skill_goes_on_cooldown_the_moment_it_starts() -> None:
    """Stamped at the start of the swing, not at the end of the recovery.

    Which means the number in the data is the gap between one use and the next
    -- what a player actually counts -- rather than a pause bolted onto however
    long the attack happened to take.
    """
    world, hero = knight_world()
    assert hero.cooldown_on(skills.HEAVY) == 0

    assert actions.begin_attack(hero, facing=0.0, weapon_index=skills.HEAVY)
    assert hero.cooldown_on(skills.HEAVY) == CLEAVE.cooldown
    assert hero.weapon.id == CLEAVE.id, "the swing is not on the slot that was asked for"


def test_a_cooling_skill_is_refused_and_costs_nothing() -> None:
    """The refusal has to be free.

    `begin_attack` commits facing before it does anything else, so a version
    that checked the cooldown afterwards would leave the hero turned to face
    whatever the refused skill was aimed at -- a button that does nothing except
    spin you round, which is worse than one that does nothing at all.
    """
    world, hero = knight_world()
    hero.facing = 0.0
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)

    # Let the whole attack finish, so only the cooldown can be refusing it.
    with enemies_idle():
        run(world, BASH.total_ticks + 2)
    assert hero.state is ActionState.IDLE
    assert hero.cooldown_on(skills.NEUTRAL) > 0

    assert not actions.begin_attack(hero, facing=3.0, weapon_index=skills.NEUTRAL)
    assert hero.facing == 0.0, "a refused skill turned the hero anyway"
    assert hero.state is ActionState.IDLE


def test_a_skill_comes_back_exactly_when_the_data_says() -> None:
    world, hero = knight_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)

    with enemies_idle():
        run(world, BASH.cooldown - 1)
        assert hero.cooldown_on(skills.NEUTRAL) == 1
        assert not actions.can_use(hero, skills.NEUTRAL)

        run(world, 1)
        assert hero.cooldown_on(skills.NEUTRAL) == 0
        assert actions.can_use(hero, skills.NEUTRAL)


def test_the_slots_cool_down_independently() -> None:
    """One shared timer would make the four slots one attack with four skins."""
    world, hero = knight_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)

    assert hero.cooldown_on(skills.HEAVY) == 0
    assert hero.cooldown_on(skills.ULTIMATE) == 0
    assert actions.can_use(hero, skills.LIGHT) is False, "mid-swing, so nothing is free"

    with enemies_idle():
        run(world, BASH.total_ticks + 2)
    assert actions.can_use(hero, skills.HEAVY)
    assert not actions.can_use(hero, skills.NEUTRAL)


def test_a_busy_hero_cannot_start_a_skill_even_off_cooldown() -> None:
    """Being free to act and having the skill available are separate questions,
    and both have to be yes. Conflating them is how "I pressed it during my own
    recovery and it came out three frames later" happens."""
    world, hero = knight_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.LIGHT)

    assert hero.cooldown_on(skills.ULTIMATE) == 0
    assert not actions.can_use(hero, skills.ULTIMATE)
    assert not actions.begin_attack(hero, weapon_index=skills.ULTIMATE)


def test_the_light_attack_is_never_gated() -> None:
    """Index 0 has no cooldown, so it is available whenever the state machine
    is -- which is what makes every recorded balance number still valid."""
    world, hero = knight_world()
    for _ in range(4):
        assert actions.begin_attack(hero, facing=0.0, weapon_index=skills.LIGHT)
        with enemies_idle():
            run(world, hero.type.weapons[skills.LIGHT].total_ticks + 1)
    assert hero.skill_cooldowns == {}, "the light attack wrote a cooldown"


# --- through the sim, not just the helpers -----------------------------------
def test_an_intent_reaches_the_slot_it_names() -> None:
    """The end-to-end path: `Intent.weapon` -> `begin_attack` -> the hitbox that
    opens. A skill that telegraphed on one weapon and landed another would read
    as a physics bug, which is the same failure the boss ordering test exists
    for."""
    world = make_world()
    hero = world.hero
    # A brute, because a grunt has 18 health and the cleave kills it outright --
    # which would cap the measured damage at the target's health and hide the
    # very difference the test is looking for.
    enemy = add_enemy(world, "brute", hero.pos + RIGHT * 24)
    before = enemy.hp

    with enemies_idle():
        run(world, CLEAVE.windup + CLEAVE.active + 1,
            Intent(aim=RIGHT, attack=True, weapon=skills.HEAVY))

    dealt = before - enemy.hp
    light = KNIGHT.weapons[skills.LIGHT]
    assert dealt > light.damage + light.variance, (
        f"the heavy dealt {dealt}, which is within light-attack range"
    )


def test_holding_a_skill_down_does_not_re_fire_it_off_cooldown() -> None:
    """Held for longer than the cooldown, and it comes out twice -- once at the
    start and once when the timer expires.

    That is correct for the *sim*, which has no notion of a key being held; it
    is the scene that edge-triggers the press. Pinned here so that the sim's
    behaviour is a decision on record rather than something the input layer is
    silently relied upon to hide.
    """
    world = make_world()
    hero = world.hero
    add_enemy(world, "grunt", hero.pos + RIGHT * 24)
    held = Intent(aim=RIGHT, attack=True, weapon=skills.NEUTRAL)

    starts = 0
    with enemies_idle():
        for _ in range(BASH.cooldown + BASH.total_ticks + 4):
            was_idle = hero.state is ActionState.IDLE
            run(world, 1, held)
            if was_idle and hero.state is ActionState.WINDUP:
                starts += 1
    assert starts == 2, f"the neutral started {starts} times over one cooldown"


# --- what did not change -----------------------------------------------------
def test_no_enemy_ever_records_a_cooldown() -> None:
    """Every enemy attack has `cooldown: 0`, so the dict stays empty for the
    whole of a fight. This is what "skills cost nothing for a body that has
    none" means in practice -- there is no branch anywhere asking whether a
    thing is a hero."""
    world = make_world()
    hero = world.hero
    for offset, type_id in enumerate(("grunt", "rat", "charger", "bowman")):
        add_enemy(world, type_id, hero.pos + Vec2(30 + offset * 14, 0))

    run(world, 240, Intent(aim=RIGHT, attack=True))

    for entity in world.entities:
        if entity.is_hero:
            continue
        assert entity.skill_cooldowns == {}, (
            f"{entity.type.id} recorded {entity.skill_cooldowns}"
        )


def test_a_boss_still_switches_freely_between_its_three_attacks() -> None:
    """The boss brain picks a weapon by range and expects to be able to use it.

    Its three attacks carry no cooldown, so the gate added for skills has to be
    invisible to it -- a boss that could only sweep once every three seconds
    would be a different fight entirely.
    """
    boss = BESTIARY["boss"]
    world = make_world()
    hero = world.hero
    enemy = add_enemy(world, "boss", hero.pos + Vec2(200, 0))

    with enemies_idle():
        for index in range(len(boss.weapons)):
            enemy.state = ActionState.IDLE
            enemy.state_ticks = 0
            assert actions.begin_attack(enemy, facing=0.0, weapon_index=index)
            assert enemy.weapon_index == index
    assert enemy.skill_cooldowns == {}


def test_an_out_of_range_slot_wraps_rather_than_raising() -> None:
    """A brain asking for weapon 7 on a body with four is a bug in the brain,
    and it should surface as the wrong attack rather than as an IndexError from
    somewhere inside the state machine two phases later. The wrap has to happen
    before the cooldown is read, or the timer lands on a slot that does not
    exist."""
    world, hero = knight_world()
    assert actions.begin_attack(hero, facing=0.0, weapon_index=len(skills.SLOTS) + skills.HEAVY)
    assert hero.weapon_index == skills.HEAVY
    assert set(hero.skill_cooldowns) == {skills.HEAVY}
