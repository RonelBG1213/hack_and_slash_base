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

from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.level import (
    REWARD_KINDS,
    REWARD_PROP,
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
#: about one lucky index. A run has thirty-nine of them.
TRANSITIONS = range(39)

SEEDS = range(12)


# --- the offer ---------------------------------------------------------------
def test_the_same_transition_offers_the_same_three_doors() -> None:
    """The whole of the determinism claim, and the reason it is cheap.

    The stream is built from `(seed, index)` and thrown away, so this holds for
    a run loaded off disk as readily as for one that has been played straight
    through -- there is no state for a save to fail to record.
    """
    for index in TRANSITIONS:
        assert rooms.offer(7, index) == rooms.offer(7, index)


def test_a_different_seed_is_a_different_run_of_rooms() -> None:
    a = [rooms.offer(1, index) for index in TRANSITIONS]
    b = [rooms.offer(2, index) for index in TRANSITIONS]
    assert a != b, "two seeds laid out the same rooms in the same order"


def test_every_offer_is_distinct_reward_kinds_only() -> None:
    """Three doors, three different things, and never an arena behind one.

    Duplicates are refused for a reason that only shows up on screen: two
    identical icons on one wall read as the room having failed to decide, not as
    a choice with a repeated option.
    """
    for seed in SEEDS:
        for index in TRANSITIONS:
            kinds = rooms.offer(seed, index)
            assert len(kinds) == TABLE.doors
            assert len(set(kinds)) == len(kinds), f"seed {seed}, room {index}: {kinds}"
            for kind in kinds:
                assert kind in REWARD_KINDS, f"{kind.value} is not something a door opens on"


def test_a_shop_is_never_further_away_than_the_guarantee_promises() -> None:
    """Gold that can never be spent is not a reward.

    Three doors drawn from four kinds can go a long way without a shop, and a
    run that banks twenty-four thousand gold and is never offered a shelf has
    quietly lost a whole system rather than had a run of bad luck.
    """
    window = TABLE.guarantee_shop_within
    for seed in SEEDS:
        gap = 0
        for index in TRANSITIONS:
            if RoomKind.SHOP in rooms.offer(seed, index):
                gap = 0
                continue
            gap += 1
            assert gap < window, (
                f"seed {seed}: no shop offered for {gap} transitions ending at "
                f"room {index}, and the guarantee is {window}"
            )


def test_the_guarantee_does_not_land_on_the_door_the_bot_takes() -> None:
    """A forced shop goes on the last door, never the first.

    `autoplay` takes door 0 every time. A guarantee that wrote to door 0 would
    make the reference bot's experience of this feature mostly "shop", which is
    the one reward it is structurally incapable of using -- so the measurement
    would drift towards meaninglessness without a single number changing.
    """
    forced = 0
    for seed in SEEDS:
        for index in TRANSITIONS:
            raw = rooms._raw_offer(seed, index)
            live = rooms.offer(seed, index)
            if raw == live:
                continue
            forced += 1
            assert live[0] == raw[0], f"seed {seed}, room {index}: the guarantee moved door 0"
    assert forced, "the guarantee never fired, so this proves nothing"


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
            rooms.offer(tick, tick)
            rooms._raw_offer(tick * 3, tick)
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
@pytest.mark.parametrize("kind", REWARD_KINDS)
def test_a_chamber_of_every_kind_is_playable(kind: RoomKind) -> None:
    """`problems()` is the only thing between a broken room and a stranded run.

    In an arena a blocked lane costs a slow fight. Here there is nothing to
    kill, so a wall between the entrance and a door is a run that cannot
    continue at all -- which is why the straight-line check is in `Level` rather
    than trusted to `tools/make_rooms.py`.
    """
    level = rooms.chamber(kind, rooms.offer(0, 0))
    assert level.problems() == []
    assert level.kind is kind
    assert not level.is_fight


@pytest.mark.parametrize("kind", REWARD_KINDS)
def test_a_chamber_holds_the_one_prop_its_kind_names(kind: RoomKind) -> None:
    level = rooms.chamber(kind, rooms.offer(0, 0))
    assert level.reward is not None
    assert level.reward.kind is REWARD_PROP[kind]
    assert len(level.doors) == TABLE.doors


def test_the_doors_lead_where_the_offer_said() -> None:
    offered = rooms.offer(3, 11)
    level = rooms.chamber(RoomKind.SHRINE, offered)
    assert tuple(door.leads_to for door in level.doors) == offered


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
def a_chamber(kind: RoomKind = RoomKind.FOUNTAIN, seed: int = 1) -> World:
    return World(rooms.chamber(kind, rooms.offer(0, 0)), BESTIARY, seed=seed)


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
    comment: the chamber puts its fixture on the middle row, so a bot walking to
    the *middle* door would pass straight over it. Move a door and this fails.
    """
    from hack_and_slash.game.autoplay import autoplay
    from hack_and_slash.game.intent import NOTHING

    world = a_chamber(RoomKind.FOUNTAIN)
    for _ in range(600):
        if world.outcome is not Outcome.RUNNING:
            break
        step(world, autoplay(world))

    assert world.outcome is Outcome.WON, "the bot never found its way out of a room"
    assert world.taken == [], "the bot used a fixture on its way through"
    assert not any(prop.taken for prop in world.props if not prop.is_door)


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
    assert payload["doors"] == len(rooms.offer(0, 0))
    assert RoomKind(payload["first_room"]) in REWARD_KINDS


def test_more_doors_than_kinds_is_refused_at_load(tmp_path) -> None:
    """Sampled without replacement, so it is not a duller room -- it is no room.

    Said at startup rather than raised out of the middle of somebody's
    twentieth stage.
    """
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["doors"] = len(REWARD_KINDS) + 1
    broken = tmp_path / "rooms.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="reward kinds"):
        rooms.Table.load(broken)


def test_a_first_room_that_is_an_arena_is_refused_at_load(tmp_path) -> None:
    payload = json.loads(rooms.config.ROOMS_DATA.read_text(encoding="utf-8"))
    payload["first_room"] = RoomKind.BOSS.value
    broken = tmp_path / "rooms.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="reward room"):
        rooms.Table.load(broken)
