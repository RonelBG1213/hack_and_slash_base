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

from hack_and_slash.core.vec2 import ZERO, Vec2
from hack_and_slash.game import actions, skills
from hack_and_slash.game.attributes import NEUTRAL
from hack_and_slash.game.entities import ActionState
from hack_and_slash.game.events import EventKind
from hack_and_slash.game.intent import Intent

from .helpers import BESTIARY, add_enemy, enemies_idle, make_world, run

RIGHT = Vec2(1, 0)

KNIGHT = BESTIARY["knight"]
#: The Knight's neutral, which is a buff rather than an attack -- the cooldown
#: tests below do not care which, and that is the point of them.
RESOLVE = KNIGHT.weapons[skills.NEUTRAL]
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
        run(world, RESOLVE.total_ticks + 2)
    assert hero.state is ActionState.IDLE
    assert hero.cooldown_on(skills.NEUTRAL) > 0

    assert not actions.begin_attack(hero, facing=3.0, weapon_index=skills.NEUTRAL)
    assert hero.facing == 0.0, "a refused skill turned the hero anyway"
    assert hero.state is ActionState.IDLE


def test_a_skill_comes_back_exactly_when_the_data_says() -> None:
    world, hero = knight_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)

    with enemies_idle():
        run(world, RESOLVE.cooldown - 1)
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
        run(world, RESOLVE.total_ticks + 2)
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
        for _ in range(RESOLVE.cooldown + RESOLVE.total_ticks + 4):
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


# --- the buff slot -----------------------------------------------------------
def test_the_neutral_slot_buffs_its_user_instead_of_hitting_anything() -> None:
    """The whole feature, end to end and through the sim.

    A hero casts Q with a brute at 18px -- inside the reach 20 the Shield Bash
    this replaces had, so an unchanged neutral would both damage it and shove
    it 9.5. Afterwards the brute must be untouched and the hero must be
    carrying the block.

    "Untouched" is checked on health and on `velocity`, deliberately not on
    `pos`: knockback is an impulse on `velocity`, while `sim._separate` moves
    `pos` every tick two bodies overlap. Asserting the position would fail on
    the crowd physics that a Shield Bash landing has nothing to do with.
    """
    world = make_world()
    hero = world.hero
    enemy = add_enemy(world, "brute", hero.pos + RIGHT * 18)
    before_hp = enemy.hp

    with enemies_idle():
        run(world, RESOLVE.windup + RESOLVE.active + 1,
            Intent(aim=RIGHT, attack=True, weapon=skills.NEUTRAL))

    assert enemy.hp == before_hp, "the buff dealt damage"
    assert enemy.velocity == ZERO, "the buff knocked something back"
    assert enemy.id not in hero.hit_ids, "the buff opened a hitbox"
    assert hero.buff == RESOLVE.buff
    assert hero.buff_ticks > 0


def test_the_buff_reaches_the_arithmetic_the_sim_reads() -> None:
    """`Entity.attrs` is the only attribute value the sim ever consults, so a
    buff that does not arrive there is a buff that does nothing at all."""
    world, hero = knight_world()
    assert hero.attrs.defense == 0

    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    with enemies_idle():
        run(world, RESOLVE.windup + 1)

    assert hero.attrs.defense == RESOLVE.buff.defense, (
        "the buff never reached `attrs`"
    )


def test_a_buff_expires_exactly_when_the_data_says() -> None:
    """And leaves the *shared* neutral block behind, not an equal copy.

    `Entity.attrs` tests `self.buff is NEUTRAL` by identity to keep the sum
    free for every unbuffed body on every tick. An expiry that assigned a fresh
    `Attributes()` would pass every equality test in this file and quietly put
    an eight-field construction on every tick of the rest of the run.
    """
    world, hero = knight_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    with enemies_idle():
        # The buff lands when the active window opens, which `_advance_state`
        # does at the *end* of a tick -- so by the time this reads it, phase 1
        # of the following tick has already spent one. Hence the -1, and it is
        # the same arithmetic every other timer in the game is read with.
        run(world, RESOLVE.windup + 1)
        live = hero.buff_ticks
        assert live == RESOLVE.buff_ticks - 1

        run(world, live - 1)
        assert hero.buff_ticks == 1
        assert hero.attrs.defense == RESOLVE.buff.defense, (
            "the buff stopped applying before its last tick"
        )

        run(world, 1)
    assert hero.buff_ticks == 0
    assert hero.buff is NEUTRAL, "expiry left a copy rather than the singleton"
    assert hero.attrs.defense == 0


def test_a_buff_interrupted_during_its_windup_is_lost() -> None:
    """Being hit out of a cast costs you the cast and the cooldown both.

    That is what makes the commitment real, and it is not a special case: the
    buff lands when the active window opens, and `actions.interrupt` cancels a
    WINDUP, so this falls out of the state machine rather than being coded for.
    """
    world, hero = knight_world()
    assert actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    assert hero.state is ActionState.WINDUP

    actions.interrupt(hero)

    assert hero.state is ActionState.IDLE
    assert hero.buff is NEUTRAL and hero.buff_ticks == 0
    assert hero.cooldown_on(skills.NEUTRAL) > 0, (
        "an interrupted cast refunded its cooldown"
    )


def test_casting_a_buff_emits_its_own_event_and_no_swing() -> None:
    """A cast that landed and an attack that missed are opposite events, so
    they are different kinds. The renderer has no case for either yet; what
    matters is that anything counting swings does not count this one."""
    world, hero = knight_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)

    kinds = []
    with enemies_idle():
        for _ in range(RESOLVE.windup + RESOLVE.active + 1):
            run(world, 1)
            kinds.extend(e.kind for e in world.events)

    assert EventKind.BUFF in kinds
    assert EventKind.SWING not in kinds
    assert EventKind.SHOOT not in kinds


def test_re_casting_replaces_the_window_rather_than_extending_it() -> None:
    """Documented behaviour rather than reachable behaviour.

    Every buff in the game is shorter than the cooldown gating it -- pinned by
    `test_a_buff_cannot_still_be_live_when_its_slot_comes_back` -- so a player
    cannot get here. Pinned anyway, because "replace" is the reading that stays
    correct if that ever changes, and the alternative is a slot that ratchets
    itself upwards for anybody who presses it on time.
    """
    world, hero = knight_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    with enemies_idle():
        run(world, RESOLVE.windup + 1)
        live = hero.buff_ticks
        run(world, 30)
    assert hero.buff_ticks == live - 30, "the window did not run down"

    actions.apply_buff(hero)
    assert hero.buff_ticks == RESOLVE.buff_ticks, "a re-cast stacked"


# --- haste, which the Priest's buff carries ----------------------------------
PRIEST = BESTIARY["priest"]
BENEDICTION = PRIEST.weapons[skills.NEUTRAL]
SMITE = PRIEST.weapons[skills.HEAVY]


def priest_world():
    world = make_world()
    world.hero.type = PRIEST
    return world, world.hero


def test_a_haste_buff_shortens_what_the_other_slots_are_stamped_at() -> None:
    """The Priest's whole idea: press Q first and the rest of the kit runs
    faster. Measured on what lands in `skill_cooldowns`, because that is the
    number the player actually waits out."""
    world, hero = priest_world()
    assert BENEDICTION.buff_haste > 0, "the Priest stopped hasting; rewrite this"

    # Unhasted, for the baseline.
    assert actions.begin_attack(hero, facing=0.0, weapon_index=skills.HEAVY)
    assert hero.cooldown_on(skills.HEAVY) == SMITE.cooldown

    world, hero = priest_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    with enemies_idle():
        run(world, BENEDICTION.windup + BENEDICTION.active + BENEDICTION.recovery + 2)
    assert hero.buff_haste == BENEDICTION.buff_haste

    assert actions.begin_attack(hero, facing=0.0, weapon_index=skills.HEAVY)
    expected = SMITE.cooldown * (1000 - BENEDICTION.buff_haste) // 1000
    assert hero.cooldown_on(skills.HEAVY) == expected, (
        f"smite stamped at {hero.cooldown_on(skills.HEAVY)}, wanted {expected}"
    )
    assert expected < SMITE.cooldown


def test_a_buff_never_hastes_its_own_gate() -> None:
    """The ratchet, refused. If a haste buff shortened the cooldown on the slot
    that granted it, pressing it on time would shorten the next wait, and the
    next, until it was permanently live -- and `buff_ticks < cooldown` would
    stop being a fact about the content files.

    Checked by hasting the hero far harder than any content does and asserting
    the neutral is stamped at its full, unhasted number anyway.
    """
    world, hero = priest_world()
    hero.buff_haste = 900

    assert actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    assert hero.cooldown_on(skills.NEUTRAL) == BENEDICTION.cooldown, (
        "the buff shortened its own cooldown"
    )
    assert hero.cooldown_on(skills.NEUTRAL) > BENEDICTION.buff_ticks, (
        "the buff can now outlast its own gate"
    )


def test_haste_expires_with_the_buff_that_brought_it() -> None:
    world, hero = priest_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    with enemies_idle():
        run(world, BENEDICTION.windup + 1)
        live = hero.buff_ticks
        assert hero.buff_haste == BENEDICTION.buff_haste
        run(world, live)

    assert hero.buff_ticks == 0
    assert hero.buff_haste == 0, "haste outlived the buff"
    assert hero.buff is NEUTRAL


def test_haste_leaves_a_cooldown_already_running_alone() -> None:
    """It is stamped, not a rate. A skill spent before the buff went up waits
    the whole time it was told to -- so casting Q is a decision about the
    *next* few presses, not a refund on the last one."""
    world, hero = priest_world()
    actions.begin_attack(hero, facing=0.0, weapon_index=skills.HEAVY)
    with enemies_idle():
        run(world, SMITE.total_ticks + 2)
    before = hero.cooldown_on(skills.HEAVY)

    actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
    with enemies_idle():
        run(world, BENEDICTION.windup + 1)
    assert hero.buff_haste > 0

    # One tick of countdown happened for each tick run; nothing else moved it.
    spent = BENEDICTION.windup + 1
    assert hero.cooldown_on(skills.HEAVY) == before - spent, (
        "haste reached back and shortened a cooldown already running"
    )


def test_a_class_with_no_haste_stamps_exactly_what_the_data_says() -> None:
    """Four of the five buffs carry no haste at all, so `actions.hasted` takes
    an early return and the arithmetic is the arithmetic that was there before
    the field existed -- the same shape as every other zero-is-the-identity
    dial in this project."""
    for class_id in ("knight", "rogue", "archer", "magician"):
        world = make_world()
        hero = world.hero
        hero.type = BESTIARY[class_id]
        actions.begin_attack(hero, facing=0.0, weapon_index=skills.NEUTRAL)
        with enemies_idle():
            run(world, hero.type.weapons[skills.NEUTRAL].windup + 2)
        assert hero.buff_haste == 0

        heavy = hero.type.weapons[skills.HEAVY]
        world2 = make_world()
        world2.hero.type = BESTIARY[class_id]
        actions.begin_attack(world2.hero, facing=0.0, weapon_index=skills.HEAVY)
        assert world2.hero.cooldown_on(skills.HEAVY) == heavy.cooldown


def test_no_enemy_ever_carries_a_buff() -> None:
    """The counterpart to `test_no_enemy_ever_records_a_cooldown`, and the same
    claim: this layer costs nothing for a body that has none. Every branch
    added for buffs is guarded on `is_buff` or on `buff_ticks`, and both are
    falsy on every enemy attack in the game."""
    world = make_world()
    hero = world.hero
    for offset, type_id in enumerate(("grunt", "rat", "charger", "bowman")):
        add_enemy(world, type_id, hero.pos + Vec2(30 + offset * 14, 0))

    run(world, 240, Intent(aim=RIGHT, attack=True))

    for entity in world.entities:
        if entity.is_hero:
            continue
        assert entity.buff is NEUTRAL and entity.buff_ticks == 0, (
            f"{entity.type.id} is carrying {entity.buff}"
        )
