"""The rooms between the arenas: the offer, the fixtures, and what a run does.

Three things this file is protecting, in descending order of how expensive they
would be to find out about later:

1. **The map stream touches none of the other three.** One draw from `world.rng`
   here shifts every damage roll for the rest of the run and moves all 280 cells
   of the recorded class-by-stage grid, with no balance number changing and
   nothing else in the suite to report it.
2. **A reward room is never a room nobody leaves.** There is nothing in one to
   kill, so the only way out is a door -- and nothing in this game paths around
   a wall.
3. **`Run.index` counts arenas and nothing else.** Every recorded number in the
   project is indexed by it.
"""

from __future__ import annotations

import json

import pytest

from hack_and_slash import config
from hack_and_slash.core import campaign_io
from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.level import (
    REWARD_KINDS,
    REWARD_PROP,
    Direction,
    EnemySpawn,
    Level,
    PropKind,
    RoomKind,
)
from hack_and_slash.game import rooms
from hack_and_slash.game.combat import roll_damage
from hack_and_slash.game.run import Run
from hack_and_slash.game.sim import step
from hack_and_slash.game.world import Outcome, World

from .helpers import BESTIARY, HERO, open_room

TABLE = rooms.table()

#: Enough transitions that a claim about the roll is about the roll rather than
#: about one lucky index. A run has one fewer than it has arenas -- forty-nine
#: of them -- and it is read off the campaign rather than typed, so extending
#: the campaign cannot leave this quietly covering only part of a run.
TRANSITIONS = range(campaign_io.load(config.LEVELS_DIR / "campaign.json").length - 1)

SEEDS = range(12)

#: The shipped fifty, loaded once. The schedule reads the campaign now -- half
#: of it is "the floor after a boss", and where a boss stands is content rather
#: than a number -- so a test about the schedule needs a real one to read.
#:
#: That is also what makes the pinned floor list below guard
#: `tools/make_level.py` as well as `data/rooms.json`: move a boss and either
#: the stall moves with it or this file fails, which is the entire point of the
#: fact being derived instead of listed.
CAMPAIGN = campaign_io.load(config.LEVELS_DIR / "campaign.json")

#: Where the bosses stand, read off the campaign rather than typed out -- the
#: same argument the code makes, and a list here could go stale the same way.
BOSS_FLOORS = tuple(
    CAMPAIGN.stage_number(i)
    for i in range(len(CAMPAIGN))
    if CAMPAIGN[i].kind is RoomKind.BOSS
)


# --- the offer ---------------------------------------------------------------
def test_the_same_transition_offers_the_same_three_doors() -> None:
    """The whole of the determinism claim, and the reason it is cheap.

    The stream is built from `(seed, index)` and thrown away, so this holds for
    a run loaded off disk as readily as for one that has been played straight
    through -- there is no state for a save to fail to record.
    """
    for index in TRANSITIONS:
        assert rooms.offer(7, index, CAMPAIGN) == rooms.offer(7, index, CAMPAIGN)


def test_a_different_seed_is_a_different_run_of_rooms() -> None:
    a = [rooms.offer(1, index, CAMPAIGN) for index in TRANSITIONS]
    b = [rooms.offer(2, index, CAMPAIGN) for index in TRANSITIONS]
    assert a != b, "two seeds laid out the same rooms in the same order"


def test_every_offer_is_distinct_reward_kinds_only() -> None:
    """Three doors, three different things, and never an arena behind one.

    Duplicates are refused for a reason that only shows up on screen: two
    identical icons on one wall read as the room having failed to decide, not as
    a choice with a repeated option.
    """
    for seed in SEEDS:
        for index in TRANSITIONS:
            kinds = rooms.offer(seed, index, CAMPAIGN)
            assert len(kinds) == TABLE.doors
            assert len(set(kinds)) == len(kinds), f"seed {seed}, room {index}: {kinds}"
            for kind in kinds:
                assert kind in REWARD_KINDS, f"{kind.value} is not something a door opens on"


def test_a_stall_stands_where_the_schedule_says_and_nowhere_else() -> None:
    """The stall is on a schedule, not in the draw.

    Gold that can never be spent is not a reward, and this is the whole of what
    now promises it can be -- there is no draw-and-guarantee pair behind it, so
    if the schedule does not hold there is nothing else to catch it.

    Two rules, and a floor needs only one of them: the interval, and a floor
    that follows a boss. Both halves are asserted, and so is the negative, which
    is the one that is easy to lose: a gate that lets a stall through on a floor
    that is neither is a gate that is not doing anything, and a suite that only
    checked the floors that should have one would pass anyway.
    """
    every = TABLE.stall_every
    assert every > 1, "the shipped table has the stall on every floor; this proves nothing"

    for seed in SEEDS:
        for index in TRANSITIONS:
            floor = rooms.floor_of(index)
            scheduled = floor % every == 0 or (TABLE.stall_on_boss and floor in BOSS_FLOORS)
            offered = RoomKind.SHOP in rooms.offer(seed, index, CAMPAIGN)
            assert offered == scheduled, (
                f"seed {seed}, floor {floor}: "
                f"{'a stall was offered' if offered else 'no stall was offered'}, "
                f"and the schedule is every {every} floors plus {BOSS_FLOORS}"
            )


def test_the_stall_stands_on_the_floors_the_schedule_names() -> None:
    """The schedule spelled out, so a change to it has to be a decision.

    `floor_of` is `index + 2` and that is the kind of arithmetic that looks
    wrong when it is right -- the doors in a room name the room after the *next*
    arena. Pinning the actual floor numbers means an off-by-one in it fails here
    rather than moving every stall in the game by one floor and passing.

    Twenty-three floors, of which **twenty-two are reachable**: the fiftieth
    arena is the last thing in a run and is not followed by a room, so floor 50
    is on the list and is never walked into. It was seven before the interval
    moved from five to three and the boss rule was written down, and nineteen
    before the campaign ran to fifty.
    """
    floors = [rooms.floor_of(i) for i in TRANSITIONS if rooms.is_stall_floor(i, CAMPAIGN)]
    assert floors == [
        3, 5, 6, 9, 10, 12, 15, 18, 20, 21, 24, 25, 27, 30, 33, 35, 36, 39, 40,
        42, 45, 48, 50,
    ]
    assert len([f for f in floors if f < CAMPAIGN.length]) == 22


def test_every_boss_floor_carries_a_stall() -> None:
    """The half of the schedule that is a fact rather than a number.

    Where a boss stands is content -- `tools/make_level.py` stamps
    `RoomKind.BOSS` on eight of the forty -- so the rule reads the campaign
    rather than carrying a list of floors that is free to disagree with it.
    This is what makes that claim true: move a boss and either the stall moves
    with it or this fails.

    It also pins something that used to be an accident. At `stall_every: 5` the
    interval landed on 5, 10 ... 40 by itself, so a shop after every act boss
    fell out of the arithmetic and nothing anywhere recorded that it was wanted.
    Moving the interval to three would have thrown it away silently.
    """
    assert TABLE.stall_on_boss, "the shipped table has the boss rule off"
    assert BOSS_FLOORS, "no boss anywhere in the campaign; this proves nothing"

    for floor in BOSS_FLOORS:
        index = floor - 2  # `floor_of` run backwards
        assert rooms.is_stall_floor(index, CAMPAIGN), f"floor {floor} follows a boss"
        assert RoomKind.SHOP in rooms.offer(0, index, CAMPAIGN)


def test_the_stall_does_not_land_on_the_door_the_bot_takes() -> None:
    """The stall goes on the last door, never the first.

    `autoplay` takes door 0 every time. A stall on door 0 would make the
    reference bot's experience of this feature "shop" on every stall floor,
    which is the one reward it is structurally incapable of using -- so the
    measurement would drift towards meaninglessness without a number changing.
    """
    stalls = 0
    for seed in SEEDS:
        for index in TRANSITIONS:
            kinds = rooms.offer(seed, index, CAMPAIGN)
            if RoomKind.SHOP not in kinds:
                continue
            stalls += 1
            assert kinds[-1] is RoomKind.SHOP, f"seed {seed}, room {index}: {kinds}"
            assert kinds[0] is not RoomKind.SHOP
    assert stalls, "no stall was ever offered, so this proves nothing"


def test_off_a_stall_floor_a_shop_is_not_reachable_at_all() -> None:
    """The gate is a gate, not a weighting.

    "Rarer" and "impossible" are different promises, and the second is the one
    that makes a stall floor a landmark worth planning a run around.
    """
    for seed in SEEDS:
        for index in TRANSITIONS:
            if rooms.is_stall_floor(index, CAMPAIGN):
                continue
            assert RoomKind.SHOP not in rooms.offer(seed, index, CAMPAIGN)


def test_a_stall_every_of_zero_puts_no_stall_anywhere(tmp_path, monkeypatch) -> None:
    """The documented rollback, exercised rather than described.

    The one number above `stall.offers: 0`: that one leaves the stall standing
    with nothing rolled on its shelf, this one means no door anywhere leads to
    one at all.

    **Boss floors included**, which is why `stall_every` is checked before the
    boss rule rather than beside it. A switch that took the stall out of the
    game and left eight of them standing after the bosses would not be the
    switch this is documented as, and it would be a plausible thing to break.
    """
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["stall_every"] = 0
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(rooms, "_TABLE", rooms.Table.load(path))
    try:
        assert payload["stall_on_boss_floors"] is True, "the boss rule is not even on"
        assert not any(rooms.is_stall_floor(index, CAMPAIGN) for index in TRANSITIONS)
        for index in TRANSITIONS:
            assert RoomKind.SHOP not in rooms.offer(0, index, CAMPAIGN)
    finally:
        rooms.reset_cache()


def test_the_boss_rule_switches_off_on_its_own(tmp_path, monkeypatch) -> None:
    """The other half of the rollback: the interval alone.

    `stall_every: 5` with this off is the schedule exactly as it shipped before
    a boss floor meant anything, and that is what makes it a rollback rather
    than a paragraph. Checked at the interval it actually ships with, so the two
    rules are shown to be separable rather than shown to agree.
    """
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["stall_on_boss_floors"] = False
    path = tmp_path / "rooms.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(rooms, "_TABLE", rooms.Table.load(path))
    try:
        floors = [rooms.floor_of(i) for i in TRANSITIONS if rooms.is_stall_floor(i, CAMPAIGN)]
        assert floors == [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48]
        assert 5 in BOSS_FLOORS and 5 not in floors, "a boss floor kept its stall"
    finally:
        rooms.reset_cache()


# --- the stream --------------------------------------------------------------
def _damage_over_a_fight(offers_between_swings: bool) -> list[int]:
    """The same seeded fight, optionally rolling rooms all the way through it."""
    world = World(open_room(), BESTIARY, seed=99)
    weapon = HERO.weapons[0]
    taken = []
    for tick in range(40):
        if offers_between_swings:
            # Every kind of draw this layer makes, interleaved as hard as it can
            # be with the fight -- which is far more than a real run ever does.
            rooms.offer(tick, tick, CAMPAIGN)
            rooms.offer(tick * 3, tick, CAMPAIGN)
        taken.append(roll_damage(weapon, world.rng))
    return taken


def test_the_map_stream_does_not_disturb_the_damage_stream() -> None:
    """The load-bearing test in this file, and it is checking a negative.

    `combat.roll_damage` draws from `world.rng`. If a room roll ever drew from
    the same generator -- through a module-level `random.*` call, most likely --
    every damage roll after the first transition would shift, all 280 cells of
    the recorded grid would move, and every balance number would still read
    exactly as it does today.

    So: run one seeded fight with the room layer rolling continuously through
    it, and one with it silent, and demand the damage came out identical.
    """
    busy = _damage_over_a_fight(True)
    quiet = _damage_over_a_fight(False)

    assert busy == quiet, (
        "the damage rolls changed when rooms were rolled alongside them -- "
        "something in game/rooms.py is drawing from world.rng"
    )
    assert busy, "the fight rolled no damage at all, so it proves nothing"


# --- building one ------------------------------------------------------------
@pytest.mark.parametrize("wall", list(Direction))
@pytest.mark.parametrize("kind", REWARD_KINDS)
def test_a_chamber_of_every_kind_is_playable(kind: RoomKind, wall: Direction) -> None:
    """`problems()` is the only thing between a broken room and a stranded run.

    In an arena a blocked lane costs a slow fight. Here there is nothing to
    kill, so a wall between the entrance and a door is a run that cannot
    continue at all -- which is why the straight-line check is in `Level` rather
    than trusted to `tools/make_rooms.py`.

    Every kind against every approach, because there are now sixteen rooms where
    there was one and a template that only works from three sides is a run that
    strands the first player to walk out of a north door.
    """
    level = rooms.chamber(kind, rooms.offer(0, 0, CAMPAIGN), wall)
    assert level.problems() == []
    assert level.kind is kind
    assert not level.is_fight


@pytest.mark.parametrize("wall", list(Direction))
@pytest.mark.parametrize("kind", REWARD_KINDS)
def test_a_chamber_holds_the_one_prop_its_kind_names(
    kind: RoomKind, wall: Direction
) -> None:
    level = rooms.chamber(kind, rooms.offer(0, 0, CAMPAIGN), wall)
    assert level.reward is not None
    assert level.reward.kind is REWARD_PROP[kind]
    assert len(level.doors) == TABLE.doors


@pytest.mark.parametrize("wall", list(Direction))
def test_the_doors_lead_where_the_offer_said(wall: Direction) -> None:
    offered = rooms.offer(3, 11, CAMPAIGN)
    level = rooms.chamber(RoomKind.SHRINE, offered, wall)
    assert tuple(door.leads_to for door in level.doors) == offered


# --- which wall each door stands on ------------------------------------------
@pytest.mark.parametrize("wall", list(Direction))
def test_a_room_puts_its_doors_on_the_three_walls_it_was_not_entered_through(
    wall: Direction,
) -> None:
    """The shape of the whole feature, asserted from the outside.

    The hero stands in the opening on the wall it arrived through, and that
    opening carries no door -- walking back out the way you came is not one of
    the three choices.
    """
    level = rooms.chamber(RoomKind.FOUNTAIN, rooms.offer(0, 0, CAMPAIGN), wall)
    walls = rooms.openings(rooms.template())

    assert level.hero_spawn == walls[wall]
    assert {door.wall for door in level.doors} == set(Direction) - {wall}
    assert {door.tile for door in level.doors} == set(walls.values()) - {walls[wall]}
    assert level.hero_spawn not in {door.tile for door in level.doors}


@pytest.mark.parametrize("wall", list(Direction))
def test_the_middle_door_is_the_one_straight_ahead(wall: Direction) -> None:
    """Left, forward, right -- and forward is the one in line with the fixture.

    This is `DOOR_ORDER`'s whole job and the reason it is a written-out table
    rather than arithmetic. Every opening shares an axis with the centre, so the
    door straight ahead of the hero is the one whose approach runs over the
    fixture. Putting it at index 1 is what keeps it away from index 0, which is
    the only door anything mechanical ever takes.
    """
    level = rooms.chamber(RoomKind.FOUNTAIN, rooms.offer(0, 0, CAMPAIGN), wall)
    reward = level.reward
    assert reward is not None

    def in_line_from_the_door(tile: tuple[int, int]) -> bool:
        """Whether walking from the spawn to `tile` runs over the fixture.

        Every opening shares an axis with the centre -- that is the layout. What
        separates forward from the other two is sharing it with the *spawn* as
        well, which is what puts the fixture on the walk rather than merely
        somewhere on the same row.
        """
        spawn = level.hero_spawn
        return (spawn[0] == reward.tile[0] == tile[0]) or (
            spawn[1] == reward.tile[1] == tile[1]
        )

    left, forward, right = level.doors
    assert forward.wall is rooms.OPPOSITE[wall]
    assert forward.wall is rooms.DOOR_ORDER[rooms.OPPOSITE[wall]][1]

    assert in_line_from_the_door(forward.tile), "the middle door is not the one ahead"
    for door in (left, right):
        assert not in_line_from_the_door(door.tile), f"the {door.wall} door is in line"


def test_every_opening_is_on_a_wall_of_its_own() -> None:
    """The template has to serve all four approaches or it serves none.

    Refused at load rather than left to raise a `KeyError` out of the middle of
    somebody's twentieth stage.
    """
    walls = rooms.openings(rooms.template())
    assert set(walls) == set(Direction)
    assert len(set(walls.values())) == len(Direction)


def test_a_template_missing_an_opening_is_refused() -> None:
    from dataclasses import replace as _replace

    base = rooms.template()
    crippled = _replace(base, props=base.props[:-1])
    with pytest.raises(ValueError, match="openings"):
        rooms._check_template(crippled)


def test_every_reward_kind_can_be_built_and_has_somewhere_to_stand() -> None:
    """Bidirectional, the way `shop.stock()` checks its goods.

    A kind with no prop would build a room with nothing in it; a prop no kind
    names would be a sprite nothing can ever reach. Both fail here rather than
    in the middle of somebody's run.
    """
    assert set(REWARD_PROP) == set(REWARD_KINDS)
    assert set(rooms.NAMES) == set(REWARD_KINDS)
    for prop_kind in REWARD_PROP.values():
        assert prop_kind is not PropKind.DOOR


# --- what the sim does with one ----------------------------------------------
def a_chamber(
    kind: RoomKind = RoomKind.FOUNTAIN,
    seed: int = 1,
    wall: Direction = rooms.FIRST_ENTRANCE,
) -> World:
    return World(rooms.chamber(kind, rooms.offer(0, 0, CAMPAIGN), wall), BESTIARY, seed=seed)


def test_a_reward_room_is_not_cleared_by_having_nothing_in_it() -> None:
    """The one-line change in `sim._settle`, and what it is guarding.

    A room has no enemies from the tick it opens. Winning on "the enemy list is
    empty" would clear it before the hero had taken a step, and the banner for
    the room would be the only part of it anybody saw.
    """
    world = a_chamber()
    for _ in range(120):
        step(world)
    assert world.outcome is Outcome.RUNNING
    assert world.exit_to is None


def test_walking_onto_a_door_ends_the_room_and_says_where_it_went() -> None:
    world = a_chamber()
    door = world.props[1]
    world.hero.pos = door.pos
    step(world)

    assert world.outcome is Outcome.WON
    assert world.exit_to is door.leads_to


def test_a_fixture_is_used_once_and_reports_it_upward() -> None:
    world = a_chamber(RoomKind.FOUNTAIN)
    fountain = world.props[0]
    world.hero.pos = fountain.pos

    step(world)
    assert world.taken == [PropKind.FOUNTAIN]
    assert fountain.taken

    # Standing on a spent fountain for another second must not pay again.
    world.taken.clear()
    for _ in range(60):
        step(world)
    assert world.taken == []


def test_a_door_is_not_something_the_run_collects() -> None:
    """`taken` is what was picked up; `exit_to` is where we went.

    One door appearing in both would make "did the hero use anything in that
    room" a question with two answers that drift apart.
    """
    world = a_chamber()
    world.hero.pos = world.props[2].pos
    step(world)
    assert world.taken == []
    assert world.exit_to is not None


def test_an_arena_carries_no_props_at_all() -> None:
    """The whole of the argument that the interaction phase is free.

    `_touch_props` returns on a falsy test, so on every tick the balance grid
    has ever measured it costs one comparison. If a stage ever grew a prop, that
    argument would quietly stop being true -- so it is asserted rather than
    assumed.
    """
    from hack_and_slash.core import campaign_io
    from hack_and_slash import config

    campaign = campaign_io.load(config.LEVELS_DIR / "campaign.json")
    for index, stage in enumerate(campaign.stages, start=1):
        assert stage.props == (), f"stage {index} carries {len(stage.props)} props"
        assert stage.is_fight, f"stage {index} is a {stage.kind.value}, not an arena"


# --- what the run does with one ----------------------------------------------
def arena(name: str, enemies=(("grunt", (12, 10)),)) -> Level:
    room = open_room(20, 20)
    return Level(
        name=name,
        rows=room.rows,
        hero_spawn=(4, 10),
        enemy_spawns=tuple(EnemySpawn(t, pos) for t, pos in enemies),
        tile=room.tile,
    )


def a_run(count: int = 4, seed: int = 5) -> Run:
    campaign = Campaign(
        name="rooms", stages=tuple(arena(f"stage {i + 1}") for i in range(count))
    )
    return Run.start(campaign, BESTIARY, seed=seed)


def clear_arena(run: Run) -> None:
    for enemy in run.world.enemies():
        enemy.hp = 0
    step(run.world)
    run.settle()


def touch(run: Run, index: int) -> None:
    """Stand on one of the room's props and let the tick resolve it."""
    run.world.hero.pos = run.world.props[index].pos
    step(run.world)
    run.settle()


def test_clearing_an_arena_leads_into_a_room_rather_than_the_next_arena() -> None:
    run = a_run()
    clear_arena(run)

    assert run.room is not None
    assert run.index == 0, "the index counts arenas, and no arena has been cleared since"
    assert run.stage_number == 1
    assert run.world.level.kind is run.room


def test_the_room_after_the_first_arena_is_the_one_the_data_names() -> None:
    """It was never chosen -- there was no door before it -- so it is fixed."""
    run = a_run()
    clear_arena(run)
    assert run.room is TABLE.first_room


def test_a_door_chooses_the_room_two_rooms_away() -> None:
    """The choice is taken now and paid off after the *next* arena.

    That delay is the whole of what makes it a choice rather than a menu, and
    it is the one thing about this feature that a player has to be told once.
    """
    run = a_run()
    clear_arena(run)
    chosen = run.world.props[3].leads_to

    touch(run, 3)
    assert run.room is None, "walking through a door leaves the room"
    assert run.index == 1, "and starts the next arena"
    assert run.next_room is chosen

    clear_arena(run)
    assert run.room is chosen


def test_the_first_room_is_entered_from_the_wall_it_always_was() -> None:
    """A run that has been through no door has no wall to be turned by.

    West, which is where the entrance stood before rooms could turn -- so the
    room after arena one is the room it has always been, and every recorded
    number that walked through it walked through the same geometry.
    """
    run = a_run()
    clear_arena(run)

    assert run.entered_from is rooms.FIRST_ENTRANCE
    assert rooms.FIRST_ENTRANCE is Direction.WEST
    walls = rooms.openings(rooms.template())
    assert run.world.level.hero_spawn == walls[Direction.WEST]


@pytest.mark.parametrize("door", range(3))
def test_the_door_you_take_becomes_the_wall_you_arrive_through(door: int) -> None:
    """The rooms lie end to end: you come in at the far side of the door taken.

    This is the whole of what makes a sequence of rooms a path rather than a
    series of identical boxes, and it is the one piece of the feature that
    spans three modules -- `chamber` stamps the wall, `sim` reports it, the run
    turns it around. A break anywhere in that chain shows up here.
    """
    run = a_run()
    clear_arena(run)

    took = run.world.props[1 + door].wall
    assert took is not None, "a door stamped by chamber() has to know its wall"

    touch(run, 1 + door)
    assert run.next_entrance is rooms.OPPOSITE[took]

    clear_arena(run)
    assert run.entered_from is rooms.OPPOSITE[took]

    walls = rooms.openings(rooms.template())
    assert run.world.level.hero_spawn == walls[rooms.OPPOSITE[took]]
    assert {d.wall for d in run.world.level.doors} == set(Direction) - {run.entered_from}


def test_a_fountain_heals_by_what_the_table_says() -> None:
    run = a_run()
    run.world.hero.hp = 10
    clear_arena(run)

    before = run.world.hero.hp
    touch(run, 0)

    assert run.used == [PropKind.FOUNTAIN]
    assert run.world.hero.hp == before + TABLE.heal_for(run.world.hero.max_hp)


def test_a_fountain_cannot_take_you_above_full_health() -> None:
    run = a_run()
    clear_arena(run)
    run.world.hero.hp = run.world.hero.max_hp - 1

    touch(run, 0)
    assert run.world.hero.hp == run.world.hero.max_hp


def test_a_chest_pays_what_the_floor_it_was_opened_on_is_worth() -> None:
    run = a_run()
    clear_arena(run)
    run.room = RoomKind.TREASURE
    run.world.props[0].kind = PropKind.CHEST

    before = run.gold
    touch(run, 0)
    assert run.gold == before + TABLE.chest_worth(run.index + 1)


def test_a_shrine_is_the_only_way_to_a_point_in_the_shipped_game() -> None:
    """`xp_base` is 0, so no kill ever pays a level and the panel never opens.

    A shrine hands the attribute layer something to spend without turning
    experience back on -- which is the part that would move the grid.
    """
    from hack_and_slash.game import progression

    assert progression.table().is_off, "this test is about a game where nothing levels"

    run = a_run()
    clear_arena(run)
    run.room = RoomKind.SHRINE
    run.world.props[0].kind = PropKind.SHRINE

    assert run.unspent_points == 0
    touch(run, 0)
    assert run.unspent_points == TABLE.shrine_points


def test_a_stall_pays_nothing_and_leaves_it_to_the_scene() -> None:
    """There is nothing for the run layer to *do* about a stall.

    The whole of what one means is "open the shop", which is a decision about
    panels. So it lands in `used`, where the scene finds it, and moves no number
    here.
    """
    run = a_run()
    clear_arena(run)
    run.room = RoomKind.SHOP
    run.world.props[0].kind = PropKind.STALL

    before = (run.gold, run.unspent_points, run.world.hero.hp)
    touch(run, 0)

    assert run.used == [PropKind.STALL]
    assert (run.gold, run.unspent_points, run.world.hero.hp) == before


def test_used_is_drained_and_never_read_back() -> None:
    run = a_run()
    clear_arena(run)
    touch(run, 0)
    assert run.used

    run.settle()
    assert run.used == []


def test_the_final_arena_is_not_followed_by_a_room() -> None:
    """A run ends on clearing the last arena. There is nothing to walk into."""
    run = a_run(count=1)
    clear_arena(run)

    assert run.room is None
    assert run.is_over


def test_switching_rooms_off_puts_the_campaign_back_in_a_straight_line() -> None:
    """The rollback, exercised rather than described.

    `enabled: false` in `data/rooms.json` and a cleared arena leads straight to
    the next one -- which is the campaign arithmetically as it was measured.
    """
    off = rooms.Table(**{**vars(TABLE), "enabled": False})
    rooms._TABLE = off
    try:
        assert off.is_off
        run = a_run()
        clear_arena(run)
        assert run.room is None
        assert run.index == 1
        assert run.stage_number == 2
    finally:
        rooms.reset_cache()


# --- the reference bot -------------------------------------------------------
def test_the_reference_bot_walks_past_every_fixture() -> None:
    """The whole of why rooms cost the measurement nothing.

    `autoplay` walks from a room's entrance to a door and touches what is in the
    middle on the way to neither. So no number in `data/rooms.json` reaches any
    bracket, and the campaign the harness measures is arithmetically the one it
    measured before rooms existed.

    This is not the bot being bad at rooms. It was the first draft, and it cost
    a whole run: over twelve seeds a healing fountain flipped one from won to
    lost, and the losing run arrived at the stage it died on with *more* health
    than the surviving one. Forty stages of a deterministic fight amplify a
    nudge, and the grid reported that amplification in the same units it reports
    difficulty.

    The geometry is load-bearing and that is why this is a test rather than a
    comment: every opening is in line with the fixture, so a bot walking to the
    door *straight ahead* would pass right over it. `DOOR_ORDER` puts that door
    second and the bot takes door 0. Move a door and this fails.

    Swept over all four approaches, because the room turns with the run now --
    a layout that clears the fixture from the west and shaves it from the north
    would be measured for as long as nobody walked out of a south door.
    """
    from hack_and_slash.game.autoplay import autoplay

    for wall in Direction:
        world = a_chamber(RoomKind.FOUNTAIN, wall=wall)
        for _ in range(600):
            if world.outcome is not Outcome.RUNNING:
                break
            step(world, autoplay(world))

        assert world.outcome is Outcome.WON, f"entered from {wall.value}: never got out"
        assert world.taken == [], f"entered from {wall.value}: used a fixture on the way"
        assert not any(prop.taken for prop in world.props if not prop.is_door)


def test_the_door_the_bot_takes_clears_the_fixture_by_a_margin() -> None:
    """The clearance itself, in pixels, rather than only its consequence.

    The test above walks the bot and asserts nothing was touched, which is the
    thing that matters -- but it passes just as well at one pixel of margin as
    at fifty, and a layout tweak that quietly cut it to two would keep passing
    until a hero radius changed somewhere else entirely.

    So: the perpendicular distance from the fixture to the straight line the bot
    walks, against the reach it would use one at. Worst case is the east
    approach and it is over 45px against a reach under 15.
    """
    from hack_and_slash.game.sim import TOUCH_RADIUS

    margins = {}
    for wall in Direction:
        world = a_chamber(RoomKind.FOUNTAIN, wall=wall)
        hero = world.hero
        fixture = next(prop for prop in world.props if not prop.is_door)
        door = next(prop for prop in world.props if prop.is_door)

        along = (door.pos - hero.pos).normalized()
        to_fixture = fixture.pos - hero.pos
        # The component of `to_fixture` perpendicular to the walk -- how far the
        # bot passes the fixture by at its closest.
        margins[wall] = abs(to_fixture.x * along.y - to_fixture.y * along.x)

        reach = hero.radius + TOUCH_RADIUS
        assert margins[wall] > reach * 3, (
            f"entered from {wall.value}: the bot passes the fixture by only "
            f"{margins[wall]:.1f}px against a {reach:.1f}px reach"
        )

    assert min(margins.values()) > 45.0, margins


def test_a_fountain_that_heals_nothing_is_rooms_switched_off() -> None:
    """The claim the bot's door policy rests on, at one remove.

    Measured rather than argued: over twelve seeds, a run with rooms enabled and
    `heal_percent: 0` reproduces a run with rooms disabled stage for stage and
    hit point for hit point. So the room layer perturbs nothing by *existing* --
    the fixtures are the entire mechanism, and a bot that touches none of them
    is measuring the campaign it always measured.

    Checked here on one transition rather than on twelve full runs, because
    twelve full runs is four minutes and the thing worth pinning is that
    entering and leaving a room leaves the hero exactly as an ordinary
    transition would.
    """
    off = rooms.Table(**{**vars(TABLE), "enabled": False})
    zero = rooms.Table(**{**vars(TABLE), "heal_percent": 0})

    results = []
    for table in (off, zero):
        rooms._TABLE = table
        try:
            run = a_run()
            run.world.hero.hp = 40
            clear_arena(run)
            if run.room is not None:
                touch(run, 1)  # a door, not the fixture
            results.append((run.index, run.stage_number, run.world.hero.hp))
        finally:
            rooms.reset_cache()

    assert results[0] == results[1], (
        f"a zero fountain is not the same as no rooms: {results[0]} vs {results[1]}"
    )


# --- the content file --------------------------------------------------------
def test_the_shipped_table_matches_the_file_on_disk() -> None:
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    assert payload["enabled"] is True, "the shipped game has rooms in it"
    assert payload["doors"] == len(rooms.offer(0, 0, CAMPAIGN))
    assert payload["stall_every"] == TABLE.stall_every
    assert payload["stall_on_boss_floors"] == TABLE.stall_on_boss
    assert RoomKind(payload["first_room"]) in REWARD_KINDS


def test_more_doors_than_kinds_is_refused_at_load(tmp_path) -> None:
    """Sampled without replacement, so it is not a duller room -- it is no room.

    Said at startup rather than raised out of the middle of somebody's
    twentieth stage.
    """
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["doors"] = len(rooms.ORDINARY_KINDS) + 1
    broken = tmp_path / "rooms.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="outside the stall"):
        rooms.Table.load(broken)


def test_the_bound_on_doors_is_the_kinds_outside_the_stall(tmp_path) -> None:
    """One fewer than there are reward kinds, and the reason is the schedule.

    The stall is not in the draw, so off a stall floor there are only the
    ordinary kinds to fill a wall from. A bound of `len(REWARD_KINDS)` would
    accept a table that builds a room on floor 5 and raises on floor 6, which is
    the worst shape this check could take -- valid until the player is four
    stages in.
    """
    assert len(rooms.ORDINARY_KINDS) == len(REWARD_KINDS) - 1
    assert RoomKind.SHOP not in rooms.ORDINARY_KINDS

    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["doors"] = len(rooms.ORDINARY_KINDS)
    payload["stall_every"] = 0
    fine = tmp_path / "rooms.json"
    fine.write_text(json.dumps(payload), encoding="utf-8")

    assert rooms.Table.load(fine).doors == len(rooms.ORDINARY_KINDS)


def test_a_negative_stall_every_is_refused_at_load(tmp_path) -> None:
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["stall_every"] = -1
    broken = tmp_path / "rooms.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="not a count of floors"):
        rooms.Table.load(broken)


def test_a_first_room_that_is_an_arena_is_refused_at_load(tmp_path) -> None:
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["first_room"] = RoomKind.BOSS.value
    broken = tmp_path / "rooms.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="reward room"):
        rooms.Table.load(broken)
