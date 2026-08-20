"""The traps in the arenas.

Most of this checks that a trap does what the floor says it should. Two tests do
something else and are the reason the file exists:

* `test_traps_do_not_disturb_the_damage_stream` -- the same negative
  `test_loot.py` and `test_attributes.py` each check from their own end. A
  hazard layer that rolled a die on a measured tick would move all 280 cells of
  the recorded grid with no balance number changing and nothing to report it.
* `test_switching_hazards_off_places_nothing` -- the rollback. `enabled: false`
  has to put the campaign back exactly, not approximately.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from hack_and_slash.core.level import EnemySpawn, Level, RoomKind
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import hazards
from hack_and_slash.game.hazards import Harms, Trap, TrapKind
from hack_and_slash.game.intent import Intent
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Purse, World

from .helpers import BESTIARY, open_room, run

TABLE = hazards.table()


def rng(seed: int = 7) -> random.Random:
    return random.Random(seed)


def arena(width: int = 30, height: int = 24) -> Level:
    """An open box that is an arena rather than an empty room.

    `open_room` has no enemies in it, and a level with nothing to fight is not a
    fight -- `place` refuses it, correctly, and every placement test would then
    be asserting on an empty tuple.
    """
    room = open_room(width, height)
    return replace(
        room,
        hero_spawn=(2, 2),
        enemy_spawns=(EnemySpawn("grunt", (width - 3, height - 3)),),
        kind=RoomKind.COMBAT,
    )


# --- the file itself ---------------------------------------------------------
def test_the_shipped_table_loads() -> None:
    assert TABLE.enabled
    assert TABLE.harms is Harms.HERO
    assert TABLE.rearm >= 1
    assert set(TABLE.kinds) == set(TrapKind)


def test_the_kinds_arrive_one_at_a_time_and_in_teaching_order() -> None:
    """The whole of what "based on floor level" means, stated as an ordering.

    Not pinned to particular floors -- those are tuning numbers and
    `data/hazards.json` says so. Pinned to being *distinct and increasing*,
    because three traps that unlock together is one trap that happens to have
    three sprites, and the campaign teaching one idea at a time is the point.
    """
    floors = [TABLE.kinds[kind].from_floor for kind in hazards.TEACHING_ORDER]
    assert floors == sorted(floors), "the kinds do not unlock in teaching order"
    assert len(set(floors)) == len(floors), "two kinds unlock on the same floor"


def test_a_bad_table_is_refused_at_load_naming_the_file(tmp_path) -> None:
    """A broken content file fails at startup, not in somebody's twentieth stage."""
    import json

    good = json.loads(hazards.config.HAZARDS_DATA.read_text(encoding="utf-8"))

    for broken, complaint in (
        ({"rearm": 0}, "rearm"),
        ({"harms": "everyone"}, "harms"),
    ):
        payload = {**good, **broken}
        path = tmp_path / "hazards.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=complaint):
            hazards.Table.load(path)

    # A window outside its own period is the subtle one: it builds a trap that
    # is either never live or always live, and neither reads as a bug.
    payload = {**good, "spike": {**good["spike"], "active": good["spike"]["period"] + 1}}
    path = tmp_path / "hazards.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="active"):
        hazards.Table.load(path)


# --- the floor decides -------------------------------------------------------
def test_the_first_floors_carry_nothing() -> None:
    """Floor 1 is the tutorial and teaches one creature. It teaches no traps."""
    assert hazards.place(arena(), 1, rng()) == ()


def test_each_kind_first_appears_exactly_on_its_own_floor() -> None:
    for kind in TrapKind:
        opens = TABLE.kinds[kind].from_floor
        assert kind not in TABLE.unlocked_on(opens - 1)
        assert kind in TABLE.unlocked_on(opens)


def test_a_deeper_floor_carries_at_least_as_many_traps() -> None:
    """Monotonic, and capped. Neither is a tuning number worth pinning; that the
    curve never goes *backwards* with depth is."""
    counts = [TABLE.count_on(floor) for floor in range(1, 41)]
    assert counts == sorted(counts), "an arena got safer as the run went deeper"
    assert max(counts) == TABLE.count_cap


def test_a_deeper_floor_hits_harder() -> None:
    assert TABLE.damage_on(40) > TABLE.damage_on(3) >= 1


def test_the_damage_curve_draws_no_dice() -> None:
    """Read twice, same answer, and no generator was involved at all.

    This is the property the whole layer rests on: what a trap costs is a
    function of the floor and nothing else, so tuning `damage` cannot move a
    single damage roll anywhere in the game.
    """
    assert TABLE.damage_on(17) == TABLE.damage_on(17)


# --- where they end up -------------------------------------------------------
def test_the_same_seed_and_floor_places_the_same_traps() -> None:
    """Stateless, exactly as `rooms.offer` is, and for the same reason: a run
    loaded from disk has to be standing in the traps it was standing in."""
    first = hazards.place(arena(), 20, random.Random(99))
    second = hazards.place(arena(), 20, random.Random(99))

    assert first, "floor 20 placed nothing, so this proves nothing"
    assert [(t.kind, t.a, t.b, t.phase) for t in first] == [
        (t.kind, t.a, t.b, t.phase) for t in second
    ]


def test_nothing_is_placed_in_a_wall() -> None:
    level = arena()
    for trap in hazards.place(level, 40, rng()):
        for point in (trap.a, trap.b):
            assert not level.is_solid(*level.tile_at(point)), f"a {trap.kind} is in a wall"


def test_nothing_is_placed_on_top_of_the_hero() -> None:
    """A hero who materialises already inside a spike was given no decision.

    Measured in pixels against the trap's own reach rather than in tiles, so
    this keeps meaning what it means if `SAFE_TILES` is ever tuned.
    """
    level = arena()
    origin = level.tile_center(*level.hero_spawn)

    for trap in hazards.place(level, 40, rng()):
        assert not trap.touches(0, origin, 6.0), f"the hero spawns inside a {trap.kind}"


def test_two_traps_never_share_the_same_floor() -> None:
    level = arena()
    traps = hazards.place(level, 40, rng())
    assert len(traps) > 1, "floor 40 placed fewer than two traps"

    for i, first in enumerate(traps):
        for second in traps[i + 1 :]:
            assert first.a.distance_to(second.a) > first.radius, "two traps are stacked"


def test_a_reward_room_is_somewhere_you_are_safe() -> None:
    """A trap in a fountain room would punish the player for taking the door the
    game offered them."""
    room = replace(arena(), kind=RoomKind.FOUNTAIN, enemy_spawns=())
    assert hazards.place(room, 40, rng()) == ()


def test_the_act_enders_are_left_alone_by_default() -> None:
    """Eight of the most tuned cells in the game, and the boss brain is
    positional. Changing them should be a decision, not a side effect."""
    boss = replace(arena(), kind=RoomKind.BOSS)
    assert not TABLE.bosses
    assert hazards.place(boss, 40, rng()) == ()


def test_switching_hazards_off_places_nothing() -> None:
    """The rollback, and it has to be exact rather than approximate."""
    off = replace(TABLE, enabled=False)
    assert off.is_off
    assert hazards.place(arena(), 40, rng(), off) == ()


# --- the cycle ---------------------------------------------------------------
def _trap(kind: TrapKind = TrapKind.SPIKE, **kwargs) -> Trap:
    base = dict(
        kind=kind,
        a=Vec2(100.0, 100.0),
        b=Vec2(100.0, 100.0),
        radius=7.0,
        damage=5,
        period=100,
        active=20,
        phase=0,
    )
    return Trap(**{**base, **kwargs})


def test_a_blinking_trap_is_live_for_its_window_and_no_longer() -> None:
    trap = _trap(period=100, active=20)
    live = [tick for tick in range(100) if trap.is_live(tick)]
    assert live == list(range(20))


def test_the_phase_offset_moves_the_window_without_resizing_it() -> None:
    """Without a phase, every trap in an arena fires in unison -- which makes a
    floor with three of them strictly easier than a floor with one."""
    plain, shifted = _trap(phase=0), _trap(phase=50)
    assert sum(plain.is_live(t) for t in range(100)) == sum(
        shifted.is_live(t) for t in range(100)
    )
    assert plain.is_live(0) and not shifted.is_live(0)


def test_a_blade_is_dangerous_on_every_tick_and_moves_instead() -> None:
    blade = _trap(TrapKind.BLADE, b=Vec2(300.0, 100.0), period=120, active=120)

    assert all(blade.is_live(tick) for tick in range(120))
    positions = {blade.at(tick).rounded() for tick in range(120)}
    assert len(positions) > 10, "the blade did not travel"


def test_a_blade_returns_to_where_it_started() -> None:
    """A triangle wave, computed from the tick rather than accumulated.

    Stepped by addition it would drift over the 240,000 ticks of a run, and a
    seeded run has to replay exactly.
    """
    blade = _trap(TrapKind.BLADE, b=Vec2(300.0, 100.0), period=120, active=120)
    assert blade.at(0).distance_to(blade.at(120)) == pytest.approx(0.0)
    assert blade.at(60).distance_to(blade.b) == pytest.approx(0.0)


def test_a_blade_is_tested_against_the_arc_it_swept() -> None:
    """A point test would let a fast blade pass clean through a body -- the same
    tunnelling `_step_projectiles` sweeps to avoid."""
    blade = _trap(TrapKind.BLADE, b=Vec2(1000.0, 100.0), period=20, active=20)

    swept = any(
        blade.touches(tick, Vec2(500.0, 100.0), 6.0) for tick in range(1, 20)
    )
    assert swept, "the blade crossed the body without the hit test noticing"


def _crowded_level() -> Level:
    """An arena with something to fight, for the policy tests below.

    The bot returns `NOTHING` in a room with no enemies, so an empty box would
    make every assertion about how it moves an assertion about nothing.
    """
    room = open_room(24, 24)
    return replace(
        room,
        hero_spawn=(8, 12),
        enemy_spawns=tuple(EnemySpawn("grunt", (14 + i, 12)) for i in range(3)),
        kind=RoomKind.COMBAT,
    )


# --- what it costs -----------------------------------------------------------
def _hero_on_a_trap(kind: TrapKind = TrapKind.SPIKE, **kwargs) -> World:
    """A world whose hero is standing exactly on one live trap."""
    world = World(open_room(), BESTIARY, seed=3, purse=Purse(floor=10))
    hero = world.hero
    assert hero is not None
    world.traps = (_trap(kind, a=hero.pos, b=kwargs.pop("b", hero.pos), **kwargs),)
    return world


def test_standing_on_a_live_trap_costs_exactly_the_floor_number() -> None:
    world = _hero_on_a_trap(damage=9)
    hero = world.hero
    before = hero.hp

    step(world)
    assert hero.hp == before - 9


def test_a_trap_does_not_hit_again_until_it_re_arms() -> None:
    """Without this a flame lane costs sixty hits a second and no number in
    `data/hazards.json` means anything."""
    world = _hero_on_a_trap(damage=4, period=1000, active=1000)
    hero = world.hero
    before = hero.hp

    run(world, 30)
    assert hero.hp == before - 4, "the trap hit more than once inside its re-arm"


def test_rolling_passes_straight_through_a_trap() -> None:
    """The roll is the answer to every trap, exactly as it is to every sword."""
    from hack_and_slash.game import actions

    world = _hero_on_a_trap(damage=9, period=1000, active=1000)
    hero = world.hero
    before = hero.hp

    actions.begin_dodge(hero, Vec2(0.0, -1.0))
    assert hero.is_invulnerable
    step(world)

    assert hero.hp == before, "i-frames did not carry the hero through a trap"


def test_a_trap_never_touches_an_enemy_while_it_harms_the_hero_alone() -> None:
    """The deliberate asymmetry. See `data/hazards.json` under `harms`: nothing
    in this game paths, so faction-neutral traps would make a deeper floor
    easier than a shallow one."""
    from .helpers import add_enemy

    world = World(open_room(), BESTIARY, seed=3, purse=Purse(floor=10))
    enemy = add_enemy(world, "grunt", Vec2(200.0, 200.0))
    world.traps = (_trap(a=enemy.pos, b=enemy.pos, damage=9, period=1000, active=1000),)
    before = enemy.hp

    run(world, 20)
    assert enemy.hp == before, "a trap damaged an enemy while harms is 'hero'"


def test_a_trap_does_not_interrupt_the_swing_it_lands_on() -> None:
    """A mistimed step should cost health, not health *and* the attack. The two
    together is more than the mistake was worth."""
    from hack_and_slash.game import actions
    from hack_and_slash.game.entities import ActionState

    world = _hero_on_a_trap(damage=4, period=1000, active=1000)
    hero = world.hero

    actions.begin_attack(hero, weapon_index=0)
    step(world)

    assert hero.state is not ActionState.IDLE, "the trap cancelled the swing"
    assert hero.stagger == 0


# --- the instrument ----------------------------------------------------------
def test_the_policy_is_untouched_when_the_layer_is_off() -> None:
    """The reference bot learned to step off a trap. This is what makes that safe.

    Teaching an instrument to answer the thing it measures is a serious change,
    and it is argued in `autoplay._trap_underfoot`. What that argument rests on
    is this: the new branch reads `world.traps`, which is empty in every arena
    the grid measured before traps existed and in every arena today with
    `data/hazards.json` switched off. So the policy is not *approximately* the
    policy that recorded those numbers -- it is the same one, tick for tick.

    Asserted by playing a whole stage twice, once through each code path, and
    demanding every position the hero visited matches.
    """
    from hack_and_slash.game.autoplay import Autoplay

    def walk() -> list[tuple[float, float]]:
        world = World(
            _crowded_level(), BESTIARY, seed=808, purse=Purse(floor=30)
        )
        world.traps = ()  # the layer off, whatever the shipped file says
        policy = Autoplay()
        path = []
        for _ in range(400):
            step(world, policy(world))
            hero = world.hero
            if hero is None:
                break
            path.append((hero.pos.x, hero.pos.y))
        return path

    assert walk() == walk()

    # And the branch really is inert rather than merely deterministic: with no
    # traps, `_trap_underfoot` never has anything to return.
    world = World(_crowded_level(), BESTIARY, seed=808, purse=Purse(floor=30))
    world.traps = ()
    assert Autoplay()._trap_underfoot(world, world.hero) is None


def test_the_policy_steps_out_of_a_trap_it_is_standing_in() -> None:
    """The other half: when there *is* a trap, the bot does something about it.

    Without this the test above passes trivially forever, including on the day
    somebody deletes the branch it is guarding.
    """
    from hack_and_slash.game.autoplay import Autoplay

    world = World(_crowded_level(), BESTIARY, seed=808, purse=Purse(floor=30))
    hero = world.hero
    lane_y = hero.pos.y
    world.traps = (
        Trap(
            kind=TrapKind.FLAME,
            a=Vec2(hero.pos.x - 100.0, lane_y),
            b=Vec2(hero.pos.x + 100.0, lane_y),
            radius=8.0,
            damage=9,
            period=1000,
            active=1000,
            phase=0,
        ),
    )

    escape = Autoplay()._trap_underfoot(world, hero)
    assert escape is not None, "the bot stood in a burning lane and did not notice"
    # Out of the lane, not along it: a jet is escaped across, never lengthwise.
    assert abs(escape.y) > abs(escape.x), f"the bot ran down the lane instead of off it: {escape}"


# --- the load-bearing negative -----------------------------------------------
def _damage_taken_over_a_fight(traps_on: bool) -> list[int]:
    """Run one seeded fight and record every damage number the hero dealt.

    The traps are made lethal rather than merely present when they are on: a
    layer that disturbs the stream disturbs it by *drawing*, so the test wants
    as many trap events as it can get.
    """
    from hack_and_slash.core.level import EnemySpawn
    from hack_and_slash.game.events import EventKind

    level = replace(
        open_room(24, 24),
        hero_spawn=(6, 12),
        enemy_spawns=tuple(
            EnemySpawn("grunt", (12 + i, 12)) for i in range(3)
        ),
        kind=RoomKind.COMBAT,
    )
    world = World(level, BESTIARY, seed=4321, purse=Purse(floor=10))

    if traps_on:
        # Straight through the middle of the fight, always live, and re-arming
        # constantly. Nothing subtle -- the point is to make it hit often.
        world.traps = (
            Trap(
                kind=TrapKind.SPIKE,
                a=level.tile_center(10, 12),
                b=level.tile_center(10, 12),
                radius=40.0,
                damage=3,
                period=10,
                active=10,
                phase=0,
            ),
        )
    else:
        world.traps = ()

    dealt: list[int] = []
    attack = Intent(move=Vec2(1.0, 0.0), aim=Vec2(1.0, 0.0), attack=True)
    for _ in range(600):
        step(world, attack)
        for event in world.events:
            if event.kind is EventKind.HIT and not event.is_hero:
                dealt.append(event.amount)
    return dealt


def test_traps_do_not_disturb_the_damage_stream() -> None:
    """The load-bearing test in this file.

    `combat.roll_damage` draws from `world.rng` on every hit, and
    `resolve_damage` draws from `world.attr_rng`. If anything in the hazard
    layer ever drew from either, every damage roll after the first trap hit
    would shift -- moving all 280 cells of the recorded class-by-stage grids
    without one balance number changing, and with nothing else in the suite to
    catch it.

    So: run the same seeded fight twice, once with a trap chewing on the hero
    the whole time and once with none at all, and assert the damage the hero
    *dealt* came out identical. It is the only way to check a negative like this.

    Note what this does and does not claim. Traps change how a fight goes -- the
    hero is poorer in health and gets shoved around, and that is the feature.
    What it claims is that they do not change the *sequence of dice*, which is
    what `data/hazards.json` promises and what makes `enabled: false` an exact
    rollback rather than an approximate one.
    """
    with_traps = _damage_taken_over_a_fight(traps_on=True)
    without = _damage_taken_over_a_fight(traps_on=False)

    assert with_traps == without, (
        "the damage rolls changed when the traps did -- something in the hazard "
        "layer is drawing from world.rng or world.attr_rng"
    )
    assert with_traps, "the fight did no damage at all, so it proves nothing"
