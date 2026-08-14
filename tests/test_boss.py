"""The Warden: three attacks, chosen by distance, and one phase change.

The design claim these protect is that the boss is *legible*. It picks its
attack from range alone, so every position has a known answer and the fight
becomes about moving between them. A boss that picked at random would be noise,
and a player cannot learn noise.
"""

from __future__ import annotations

import pytest

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import actions, ai
from hack_and_slash.game.entities import ActionState
from hack_and_slash.game.events import EventKind
from hack_and_slash.game.sim import step

from .helpers import BESTIARY, HERO, add_enemy, enemies_idle, make_world, open_room, run

BOSS = BESTIARY["boss"]
SWEEP = BOSS.weapons[ai.BOSS_SWEEP]
CRUSH = BOSS.weapons[ai.BOSS_CRUSH]
VOLLEY = BOSS.weapons[ai.BOSS_VOLLEY]

#: All four act bosses, and everything that is not one. Derived from the brain
#: rather than listed, so a fifth boss is covered by these tests the moment it
#: exists rather than the moment somebody remembers to add it here.
BOSSES = tuple(t for t in BESTIARY.types.values() if t.brain == "boss")
ORDINARY = tuple(
    t
    for t in BESTIARY.types.values()
    if t.faction.value == "enemy" and t.brain != "boss"
)


def arena_with_boss(distance: float):
    """A boss that far to the hero's right, in a room big enough for its range."""
    world = make_world(open_room(50, 24))
    boss = add_enemy(world, "boss", world.hero.pos + Vec2(distance, 0))
    return world, world.hero, boss


def chosen_attack(distance: float) -> int:
    """Which weapon the brain reaches for at this range."""
    world, hero, boss = arena_with_boss(distance)
    intent = ai.decide(world, boss)
    assert intent.attack, f"chose not to attack at {distance}px"
    return intent.weapon


# --- choosing an attack ------------------------------------------------------
def test_standing_next_to_it_gets_the_sweep() -> None:
    assert chosen_attack(SWEEP.reach + HERO.radius - 10) == ai.BOSS_SWEEP


def test_standing_at_mid_range_gets_the_crush() -> None:
    assert chosen_attack(BOSS.charge_range - 30) == ai.BOSS_CRUSH


def test_hanging_back_gets_the_volley() -> None:
    assert chosen_attack(BOSS.charge_range + 60) == ai.BOSS_VOLLEY


def test_the_choice_is_range_alone_and_therefore_repeatable() -> None:
    """A player can learn a rule. They cannot learn a dice roll."""
    for _ in range(5):
        assert chosen_attack(BOSS.charge_range - 30) == ai.BOSS_CRUSH


def test_it_will_not_shoot_through_a_wall() -> None:
    from hack_and_slash.core.level import Level

    room = open_room(40, 14)
    rows = list(room.rows)
    for y in (5, 6, 7):
        rows[y] = rows[y][:14] + "###" + rows[y][17:]
    level = Level(
        name="cover", rows=tuple(rows), hero_spawn=(4, 6), enemy_spawns=(), tile=16
    )

    world = make_world(level)
    boss = add_enemy(world, "boss", level.tile_center(30, 6))
    intent = ai.decide(world, boss)
    assert not intent.attack, "lined up a shot through three tiles of wall"
    assert not intent.move.is_zero(), "should be closing until it has a shot"


# --- the attacks themselves --------------------------------------------------
def test_the_volley_fires_the_whole_fan() -> None:
    world, hero, boss = arena_with_boss(BOSS.charge_range + 60)
    boss.facing = 0.0
    actions.begin_attack(boss, weapon_index=ai.BOSS_VOLLEY)

    with enemies_idle():
        run(world, VOLLEY.windup + 1)

    assert len(world.projectiles) == VOLLEY.projectile_count


def test_the_volley_fans_out_rather_than_stacking() -> None:
    # Five shots along one line is one shot with extra steps.
    world, hero, boss = arena_with_boss(BOSS.charge_range + 60)
    boss.facing = 0.0
    actions.begin_attack(boss, weapon_index=ai.BOSS_VOLLEY)

    with enemies_idle():
        run(world, VOLLEY.windup + 1)

    headings = sorted(shot.velocity.angle() for shot in world.projectiles)
    assert len(set(headings)) == VOLLEY.projectile_count
    spread = headings[-1] - headings[0]
    assert spread == pytest.approx(VOLLEY.spread, abs=1e-6)


def test_only_the_crush_carries_a_dash() -> None:
    """The bug this forbids: a boss sliding forward during its ranged attack.

    Before the dash moved onto the weapon it was a property of the creature, so
    anything that could charge charged on everything it did.
    """
    for index, weapon in ((ai.BOSS_SWEEP, SWEEP), (ai.BOSS_VOLLEY, VOLLEY)):
        world, hero, boss = arena_with_boss(200)
        boss.facing = 0.0
        actions.begin_attack(boss, weapon_index=index)
        start = boss.pos

        with enemies_idle():
            run(world, weapon.windup + max(1, weapon.active))

        assert boss.pos.distance_to(start) < 2.0, f"{weapon.id} moved the boss"

    world, hero, boss = arena_with_boss(200)
    boss.facing = 0.0
    actions.begin_attack(boss, weapon_index=ai.BOSS_CRUSH)
    start = boss.pos
    with enemies_idle():
        run(world, CRUSH.windup + 8)
    assert boss.pos.distance_to(start) > 10.0, "the crush did not charge"


def test_every_attack_telegraphs_for_its_full_windup() -> None:
    # The boss is meant to be hard because it asks you to be somewhere else,
    # not because it is fast.
    for index in (ai.BOSS_SWEEP, ai.BOSS_CRUSH, ai.BOSS_VOLLEY):
        world, hero, boss = arena_with_boss(60)
        weapon = BOSS.weapons[index]
        actions.begin_attack(boss, facing=0.0, weapon_index=index)

        with enemies_idle():
            run(world, weapon.windup - 1)
            assert boss.state is ActionState.WINDUP, f"{weapon.id} opened early"
            assert hero.hp == hero.type.hp, f"{weapon.id} dealt damage during its tell"


def test_an_attack_keeps_the_weapon_it_started_with() -> None:
    """Wind up with one attack and land another and the tell means nothing."""
    world, hero, boss = arena_with_boss(60)
    actions.begin_attack(boss, facing=0.0, weapon_index=ai.BOSS_CRUSH)

    with enemies_idle():
        for _ in range(CRUSH.windup + CRUSH.active):
            step(world)
            if boss.state in (ActionState.WINDUP, ActionState.ACTIVE):
                assert boss.weapon.id == CRUSH.id


def test_the_boss_cannot_dodge() -> None:
    world, hero, boss = arena_with_boss(80)
    assert not actions.begin_dodge(boss, Vec2(1, 0))


# --- the phase change --------------------------------------------------------
def test_a_wounded_boss_pauses_less_between_attacks() -> None:
    world, hero, boss = arena_with_boss(80)
    healthy = ai.cooldown_for(boss)

    boss.hp = int(BOSS.hp * (ai.BOSS_ENRAGE_BELOW - 0.1))
    assert ai.cooldown_for(boss) < healthy


def test_the_phase_change_adds_no_new_moves() -> None:
    """Deliberate: nothing new to learn at the moment the player can least
    afford to learn it. The pressure rises, the vocabulary does not."""
    world, hero, boss = arena_with_boss(BOSS.charge_range - 30)
    healthy_choice = ai.decide(world, boss).weapon

    boss.hp = 1
    assert ai.decide(world, boss).weapon == healthy_choice


def test_enrage_does_not_shorten_the_telegraphs() -> None:
    # It is the gap between attacks that closes, never the tell itself.
    world, hero, boss = arena_with_boss(60)
    boss.hp = 1
    actions.begin_attack(boss, facing=0.0, weapon_index=ai.BOSS_SWEEP)

    with enemies_idle():
        run(world, SWEEP.windup - 1)
        assert boss.state is ActionState.WINDUP


# --- it is a real fight ------------------------------------------------------
def test_every_boss_is_tougher_than_any_ordinary_enemy() -> None:
    """What makes an act's ending feel like one.

    Checked across all four rather than for the Warden alone: a later boss with
    less health than a brute would end its act on an anticlimax, and the number
    that would have caused it lives in a JSON file nobody rereads.
    """
    toughest_ordinary = max(e.hp for e in ORDINARY)
    for boss in BOSSES:
        assert boss.hp > toughest_ordinary, f"{boss.id} is not tougher than the field"


def test_every_boss_is_slower_than_every_class() -> None:
    """The deal the whole game rests on, at the one place it would hurt most.

    Note what is *not* claimed any more. The Warden is slower than everything in
    the game, which is why its own fight has so much breathing room -- but the
    Houndmaster is deliberately faster than a brute, and asserting that no boss
    outpaces any enemy would forbid that. What has to hold everywhere is that
    you can walk away from a boss, on any class, including the slowest.
    """
    slowest_class = min(c.speed for c in BESTIARY.hero_classes)
    for boss in BOSSES:
        assert boss.speed < slowest_class, f"{boss.id} can run down the slowest class"


def test_a_boss_fight_runs_without_raising() -> None:
    from hack_and_slash.game.autoplay import autoplay

    world, hero, boss = arena_with_boss(200)
    for _ in range(900):
        step(world, autoplay(world))
    # No assertion on who won -- that is the balance harness's job. This is
    # about the three attacks, the dash and the volley coexisting for a whole
    # fight without tripping over each other.
    assert world.tick == 900
