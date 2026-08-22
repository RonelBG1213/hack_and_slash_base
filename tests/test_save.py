"""Putting a run down and picking it up again.

The headline test is `test_a_restored_stage_is_the_stage_that_was_saved`. Every
other claim this feature makes rests on it: a save records a handful of numbers
and the arena is *rebuilt* from the campaign rather than deserialised, so if the
rebuild is not identical then loading a run silently rearranges the room the
player was standing in and nothing anywhere would report it.

The second one worth reading is the promotion pair. `Run` keeps `job_id` beside
`hero_type_id` rather than overwriting it, and a save that flattened the two
would load a Dark Knight back as a Knight -- twenty stages into a campaign tuned
for the class it had just discarded. That is not a hypothetical: it is the exact
bug this project already found once in `Run._advance`, and it was invisible for
as long as no code path could reach it.
"""

from __future__ import annotations

import json

import pytest

from hack_and_slash import config
from hack_and_slash.core import campaign_io
from hack_and_slash.core.level import Direction, RoomKind
from hack_and_slash.game import difficulty, jobs, rooms, save
from hack_and_slash.game.attributes import NEUTRAL, Attributes
from hack_and_slash.game.run import Run
from hack_and_slash.game.world import World

from .helpers import BESTIARY


def campaign():
    return campaign_io.load(config.LEVELS_DIR / "campaign.json")


def bodies(run: Run):
    """Everything about the arena that a rebuild has to reproduce."""
    return [
        (e.id, e.type.id, e.pos.x, e.pos.y, e.hp, e.type.faction, e.bonus)
        for e in run.world.entities
    ]


def mid_run(stage: int = 14, hero: str = "archer", seed: int = 11) -> Run:
    """A run standing at the start of a stage, the way a save is always taken.

    Started *at* the stage rather than played into it, for the reason
    `test_render.promotion_scene` gives about the promotion panel: what is under
    test is the snapshot, not the campaign. The world a run arrives at through
    `Run.start` and the one it arrives at through `_advance` are built by the
    same constructor from the same four values.
    """
    return Run.start(campaign(), BESTIARY, seed=seed, at_stage=stage - 1, hero_type_id=hero)


# --- the guarantee -----------------------------------------------------------
def test_a_restored_stage_is_the_stage_that_was_saved() -> None:
    """The load-bearing claim of the whole feature.

    A snapshot names a campaign index, a seed and a health. If the world those
    three rebuild is not the world they were taken from, then loading a run
    hands the player a different fight wearing the same stage number -- and the
    only symptom is that the room is not where they left it.
    """
    run = mid_run()
    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert bodies(restored) == bodies(run)
    assert restored.world.seed == run.world.seed


def test_a_restored_reward_room_is_the_room_that_was_saved() -> None:
    """The second boundary a save is taken on, and the one with no `Level` on disk.

    An arena is restored by handing `campaign[index]` back. A reward room has no
    file: it is stamped out of one template by `rooms.chamber`, from a kind and
    three door destinations. So this is a rebuild in the fuller sense, and the
    thing that makes it work is that **nothing about the doors is written down**
    -- `rooms.offer` is a pure function of the seed and the index, so the loaded
    room is offered the three it was offered before.

    If that ever stops being true the symptom is quiet and specific: the player
    is handed a different set of doors from the ones they were looking at when
    they quit, and every one of them is plausible.
    """
    run = mid_run()
    run.room = RoomKind.SHRINE
    run.next_room = RoomKind.TREASURE
    run.entered_from = Direction.SOUTH
    run.next_entrance = Direction.EAST
    run.world = World(
        rooms.chamber(run.room, rooms.offer(run.seed, run.index, run.campaign), run.entered_from),
        BESTIARY,
        seed=Run._room_seed(run.seed, run.index),
        carry_hp=run.world.hero.hp,
        hero_type_id=run.hero_type_id,
    )

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert restored.room is run.room
    assert restored.next_room is run.next_room
    assert restored.world.level.kind is run.world.level.kind
    assert bodies(restored) == bodies(run)
    assert [
        (p.kind, p.pos.x, p.pos.y, p.leads_to, p.wall) for p in restored.world.props
    ] == [(p.kind, p.pos.x, p.pos.y, p.leads_to, p.wall) for p in run.world.props]


def test_a_restored_room_stands_at_the_wall_it_was_entered_by() -> None:
    """The doors are derivable from the seed; the wall they stand on is not.

    Which door the player walked through is the one thing in a room that was a
    *choice*, and it decides where the next three stand. A save that dropped it
    would rebuild the same three destinations on three different walls -- and
    would put the hero at the west entrance of a room they had walked into from
    the north. Plausible, and wrong.
    """
    for wall in Direction:
        run = mid_run()
        run.room = RoomKind.FOUNTAIN
        run.entered_from = wall
        run.next_entrance = rooms.OPPOSITE[wall]
        run.world = World(
            rooms.chamber(run.room, rooms.offer(run.seed, run.index, run.campaign), wall),
            BESTIARY,
            seed=Run._room_seed(run.seed, run.index),
            carry_hp=run.world.hero.hp,
            hero_type_id=run.hero_type_id,
        )

        restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

        assert restored.entered_from is wall
        assert restored.next_entrance is rooms.OPPOSITE[wall]
        assert restored.world.level.hero_spawn == run.world.level.hero_spawn
        assert {d.wall for d in restored.world.level.doors} == set(Direction) - {wall}


def test_a_save_taken_in_an_arena_says_so() -> None:
    """Empty and None are the same answer here, and it has to survive the trip.

    A room that came back as an arena would drop the player into a stage they
    have already fought; an arena that came back as a room would put them in a
    fountain with the stage still ahead of them. Both are silent.
    """
    run = mid_run()
    assert save.snapshot(run)["room"] == ""
    assert save.restore(save.snapshot(run), campaign(), BESTIARY).room is None


def test_a_save_naming_a_room_that_is_an_arena_is_refused() -> None:
    payload = save.snapshot(mid_run())
    payload["room"] = RoomKind.BOSS.value

    with pytest.raises(save.SaveFormatError, match="standing in a boss"):
        save.restore(payload, campaign(), BESTIARY)


def test_a_save_naming_a_wall_that_does_not_exist_is_refused() -> None:
    payload = save.snapshot(mid_run())
    payload["entered_from"] = "northeast"

    with pytest.raises(save.SaveFormatError, match="wall that does not exist"):
        save.restore(payload, campaign(), BESTIARY)


def test_a_save_with_no_wall_at_all_falls_back_to_the_first_entrance() -> None:
    """Absent and wrong are different, and only one of them is a corrupt save.

    A run that has not been through a door yet has no wall to record, and the
    room after arena one is entered from the west by definition -- so an empty
    value falls back where a misspelt one is refused. That is the opposite of
    what `_room` does with an empty string, and deliberately so: there, empty
    means "standing in an arena" and is a fact, not a gap.
    """
    payload = save.snapshot(mid_run())
    payload["entered_from"] = ""
    payload["next_entrance"] = ""

    restored = save.restore(payload, campaign(), BESTIARY)
    assert restored.entered_from is rooms.FIRST_ENTRANCE
    assert restored.next_entrance is rooms.FIRST_ENTRANCE


def test_a_restored_run_draws_the_same_dice() -> None:
    """The half the entity list cannot see.

    Two worlds can hold identical bodies and still resolve differently from the
    first swing if their generators are not in the same place -- and all three
    streams matter, because the split between them is what keeps the loot and
    attribute layers from disturbing a damage roll.
    """
    run = mid_run()
    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    for stream in ("rng", "loot_rng", "attr_rng"):
        assert getattr(restored.world, stream).getstate() == getattr(run.world, stream).getstate(), (
            f"{stream} came back in a different place"
        )


def test_every_carried_number_survives_the_round_trip() -> None:
    run = mid_run()
    run.gold = 3120
    run.bonus_heal = 40
    run.gold_find = 0.75
    run.xp = 17
    run.hero_level = 4
    run.unspent_points = 2
    run.purchases = {"poultice": 3, "tonic": 1}
    run.earned = Attributes(max_hp=24, damage=3)
    run.world.hero.hp = 61

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert restored.gold == 3120
    assert restored.bonus_heal == 40
    assert restored.gold_find == 0.75
    assert restored.xp == 17
    assert restored.hero_level == 4
    assert restored.unspent_points == 2
    assert restored.purchases == {"poultice": 3, "tonic": 1}
    assert restored.earned == Attributes(max_hp=24, damage=3)
    assert restored.world.hero.hp == 61


def test_earned_attributes_reach_the_body_and_not_only_the_run() -> None:
    """`run.earned` is the owner and `Entity.bonus` is what the sim reads.

    A restore that set one and not the other would give a player their levels
    back on the HUD and not in the fight -- or the reverse, and lose them at the
    next stage boundary.
    """
    run = mid_run()
    run.earned = Attributes(max_hp=30)
    run.world.hero.bonus = run.earned
    run.world.hero.hp = 100

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert restored.world.hero.bonus == Attributes(max_hp=30)
    assert restored.world.hero.max_hp == run.world.hero.max_hp


def test_a_neutral_block_comes_back_as_the_shared_singleton() -> None:
    """Identity, not equality, and it is load-bearing.

    `World._populate` tests `hero_bonus is not NEUTRAL` and refills the hero to
    full health when it fires. An equal-but-distinct block would take a branch
    on load that the same stage did not take when it was played -- a divergence
    of exactly the kind the round-trip test above exists to rule out, arriving
    by the back door.
    """
    run = mid_run()
    assert run.earned is NEUTRAL

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)
    assert restored.earned is NEUTRAL


# --- promotion ---------------------------------------------------------------
def test_a_run_comes_back_on_the_tier_it_was_started_on() -> None:
    """The same class of failure as a promotion loaded away, and it is worth
    naming that way round.

    A run reloaded onto the default tier is a run that silently got harder or
    easier at the moment the player walked back into it -- and nothing on the
    screen says so, because the tier is chosen once at the select and never
    shown again. The health carried into the next stage is the only symptom,
    and by then it is twenty stages of arithmetic away from the cause.
    """
    tier = difficulty.table()["relentless"]
    run = Run.start(
        campaign(), BESTIARY, seed=11, at_stage=13, hero_type_id="archer",
        difficulty=tier,
    )

    payload = save.snapshot(run)
    assert payload["difficulty"] == "relentless", (
        "the tier is not in the snapshot at all"
    )

    restored = save.restore(payload, campaign(), BESTIARY)
    assert restored.difficulty.id == "relentless"
    # ...and it has to reach the fight, not merely the run object beside it.
    assert restored.world.difficulty.id == "relentless"


def test_a_save_naming_a_tier_that_no_longer_exists_loads_at_the_default() -> None:
    """The one deliberately forgiving field in this loader.

    `data/difficulty.json` is content and is explicitly allowed to move -- three
    of the four tiers ship marked unmeasured. Renaming one must not cost
    somebody the run they were halfway through, and the default is a coherent
    place to put them; every other malformed field still raises.

    The id below is deliberately not a plausible tier name. It used to be
    "nightmare", which stopped testing anything the day a tier was called that
    -- the assertion still passed, because Nightmare is not the identity, but
    for the opposite reason to the one intended.
    """
    run = mid_run()
    payload = save.snapshot(run)
    payload["difficulty"] = "no-such-tier"

    restored = save.restore(payload, campaign(), BESTIARY)
    assert restored.difficulty.is_identity


def test_a_promoted_run_comes_back_promoted() -> None:
    run = mid_run(stage=jobs.PROMOTION_STAGE + 3, hero="knight")
    jobs.promote(run, BESTIARY.promotions_for("knight")[0])
    assert run.job_id == "dark_knight"

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert restored.job_id == "dark_knight"
    assert restored.hero_type.id == "dark_knight"
    assert restored.world.hero.type.id == "dark_knight", (
        "the body was rebuilt from the base class -- a promotion evaporated on load"
    )


def test_a_promoted_run_still_restarts_as_the_class_it_began_as() -> None:
    """The other half of why `job_id` sits beside `hero_type_id`.

    `Run.restart()` reads `hero_type_id`, so flattening the two on save would
    make R start a fresh run at stage one as an advanced class -- one the
    character select cannot offer and the balance grid has never seen.
    """
    run = mid_run(stage=jobs.PROMOTION_STAGE + 3, hero="knight")
    jobs.promote(run, BESTIARY.promotions_for("knight")[0])

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert restored.hero_type_id == "knight"
    assert restored.restart().world.hero.type.id == "knight"


# --- refusing what it cannot read --------------------------------------------
def test_a_save_from_another_version_is_refused_rather_than_guessed_at() -> None:
    payload = save.snapshot(mid_run())
    payload["version"] = save.SAVE_VERSION + 1

    with pytest.raises(save.SaveFormatError):
        save.restore(payload, campaign(), BESTIARY)


def test_a_save_naming_a_class_that_does_not_exist_is_refused() -> None:
    # The failure this catches is a class deleted from `entities.json` between
    # one session and the next. Loading it would raise from inside `World`, four
    # layers down, with a message about the bestiary.
    payload = save.snapshot(mid_run())
    payload["hero_type_id"] = "paladin"

    with pytest.raises(save.SaveFormatError):
        save.restore(payload, campaign(), BESTIARY)


def test_a_save_past_the_end_of_a_shortened_campaign_lands_on_the_last_stage() -> None:
    """Clamped rather than refused. `levels/*.json` is generated, so a campaign
    getting shorter is an ordinary thing that happens to a working tree -- and
    it is not a good enough reason to throw a run away."""
    payload = save.snapshot(mid_run())
    payload["index"] = 9999

    restored = save.restore(payload, campaign(), BESTIARY)
    assert restored.index == len(campaign()) - 1


# --- the disk ----------------------------------------------------------------
def test_writing_then_reading_gives_the_run_back(tmp_path) -> None:
    run = mid_run()
    run.gold = 909
    path = tmp_path / "save.json"

    save.write(run, path)
    restored = save.restore(save.read(path), campaign(), BESTIARY)

    assert restored.gold == 909
    assert bodies(restored) == bodies(run)


def test_no_save_reads_as_none_rather_than_raising(tmp_path) -> None:
    # "There is no save" and "there is a save and it is wrong" are two different
    # answers: the menu greys its row silently for the first and has something
    # to say about the second.
    assert save.read(tmp_path / "nothing.json") is None


def test_a_corrupt_save_says_so(tmp_path) -> None:
    path = tmp_path / "save.json"
    path.write_text("{not json at all", encoding="utf-8")

    with pytest.raises(save.SaveFormatError):
        save.read(path)


def test_a_save_from_another_build_is_refused_on_read_not_on_press(tmp_path) -> None:
    """`read` makes the version check too, so the menu can grey its row before
    the player commits to it. A row that looks live and then admits it cannot
    load is worse than one that was honest first."""
    path = tmp_path / "save.json"
    payload = save.snapshot(mid_run())
    payload["version"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(save.SaveFormatError):
        save.read(path)


def test_a_half_written_save_never_replaces_a_good_one(tmp_path) -> None:
    """The write is atomic, and this is why it has to be.

    The autosave fires on every stage transition of a forty-stage run, so "the
    process died mid-write" is a moment that comes round forty times a run. A
    plain `write_text` truncates first, which means the window where a crash
    costs the whole run is exactly the window where the run was being preserved.
    """
    path = tmp_path / "save.json"
    save.write(mid_run(), path)
    good = path.read_text(encoding="utf-8")

    # The scratch file is what a killed process would leave behind.
    assert not list(tmp_path.glob("*.part")), "the temporary file was not cleaned up"
    assert json.loads(good)["version"] == save.SAVE_VERSION


def test_deleting_a_save_that_is_not_there_is_not_an_error(tmp_path) -> None:
    # `PlayScene` deletes on every route out of a run, including ones where
    # nothing was ever written -- a run lost on stage one before the first
    # update, or a `--class` run in a read-only checkout.
    save.delete(tmp_path / "nothing.json")


def test_the_menu_line_names_the_class_the_run_is_now(tmp_path) -> None:
    """Not the class it began as. A player looking for their Dark Knight run
    will not recognise it described as a Knight."""
    run = mid_run(stage=jobs.PROMOTION_STAGE + 3, hero="knight")
    jobs.promote(run, BESTIARY.promotions_for("knight")[0])
    run.gold = 4200

    line = save.describe(save.snapshot(run), BESTIARY)
    assert BESTIARY["dark_knight"].name in line
    assert "4200" in line
    assert str(run.stage_number) in line


# --- what a stall and a shrine remember --------------------------------------
def test_a_restored_stall_offers_the_same_three_pieces() -> None:
    """The gear half of the claim `test_a_restored_reward_room...` makes for the
    doors, and it is the same claim for the same reason.

    **Nothing about a shelf is written down.** `equipment.offers` is a pure
    function of the seed and the index, so a run picked back up finds the three
    pieces it was looking at, at the prices it was looking at. If that ever
    stops being true the symptom is quiet and specific: the player quits in
    front of a legendary they were saving for and comes back to three commons,
    and every one of them is plausible.
    """
    from hack_and_slash.game import equipment

    run = mid_run()
    run.room = RoomKind.SHOP
    before = equipment.offers(run)

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert equipment.offers(restored) == before
    assert before, "the stall rolled nothing, so this proves nothing"


def test_a_restored_shrine_offers_the_same_three_attributes() -> None:
    from hack_and_slash.game import progression

    run = mid_run()
    run.room = RoomKind.SHRINE
    count = rooms.table().shrine_offers
    before = progression.offers(run.seed, run.index, count)

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert progression.offers(restored.seed, restored.index, count) == before
    assert before, "the shrine offered nothing, so this proves nothing"


def test_a_bought_piece_is_still_bought_after_a_reload() -> None:
    """The one thing about a shelf that *is* written down, and it rides in
    `run.purchases` beside the shop's tally -- which is why no save field and no
    migration were needed. A row that came back buyable would let a player bank
    the same piece twice by quitting between purchases.
    """
    from hack_and_slash.game import equipment

    run = mid_run()
    run.room = RoomKind.SHOP
    run.gold = 100000
    offer = equipment.offers(run)[0]
    assert equipment.buy(run, offer)

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert equipment.taken(restored, equipment.offers(restored)[0])
    assert not equipment.can_buy(restored, equipment.offers(restored)[0])
    assert restored.earned == offer.attributes


def test_gear_keys_do_not_collide_with_the_shops_tally() -> None:
    """Both namespaces live in one dict. `shop.bought` looks up bare good ids
    and `equipment.taken` looks up `eq:`-prefixed ones, and this is the test
    that says so rather than the comment that hopes so."""
    from hack_and_slash.game import equipment, shop

    run = mid_run()
    run.gold = 100000
    run.world.hero.hp = 1
    poultice = next(g for g in shop.stock() if g.id == "poultice")
    assert shop.buy(run, poultice)
    assert equipment.buy(run, equipment.offers(run)[0])

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert shop.bought(restored, poultice) == 1
    assert equipment.taken(restored, equipment.offers(restored)[0])


# --- champions ---------------------------------------------------------------
def test_a_restored_run_remembers_that_it_opted_into_champions() -> None:
    """The decision, not the layer. What an affix *is* lives in
    `data/elites.json` and is allowed to move, so a save that stored the numbers
    would hand a run back on the tuning it was started under rather than on the
    one the file now holds -- the same argument the tier's id is stored for.
    """
    from hack_and_slash.game import elites

    run = mid_run()
    run.elites = elites.table()

    restored = save.restore(save.snapshot(run), campaign(), BESTIARY)

    assert not restored.elites.is_off
    assert restored.world.elites is restored.elites


def test_a_restored_run_that_never_asked_for_champions_still_has_none() -> None:
    from hack_and_slash.game import elites

    restored = save.restore(save.snapshot(mid_run()), campaign(), BESTIARY)

    assert restored.elites is elites.OFF
    assert restored.world.elites.is_off


def test_a_save_written_before_champions_existed_is_refused() -> None:
    """Not migrated -- refused, which is what `check_version` has always done.
    An older build reading a newer file would drop the flag and hand back a run
    with the champions quietly switched off, and that silent wrongness is the
    whole reason the version moved."""
    payload = save.snapshot(mid_run())
    payload["version"] = save.SAVE_VERSION - 1

    with pytest.raises(save.SaveFormatError):
        save.check_version(payload)
