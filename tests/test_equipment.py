"""What a stall rolls, what it costs, and what buying it writes.

Three things this file is protecting, in descending order of how expensive they
would be to find out about later:

1. **The stall stream touches none of the other four.** One draw from
   `world.rng` here shifts every damage roll for the rest of the run and moves
   all 280 cells of the recorded class-by-stage grid, with no balance number
   changing and nothing else in the suite to report it. Same argument
   `test_rooms.py` opens with, and the same test, aimed at the new stream.
2. **The roll is derived, never held.** A save records nothing about a shelf, so
   a run picked back up has to re-derive the shelf it was put down in front of.
   If this stops holding, a player loses a piece they were about to buy and the
   save file cannot say what it was.
3. **A purchase writes both halves.** `run.earned` survives the stage boundary;
   `Entity.bonus` is what the sim reads on the body standing here. One without
   the other is a purchase that is inert now or lost in a minute.

Headless throughout. The stall is a pure function of a `Run` -- the scene decides
when to show it, and none of that is under test here.
"""

from __future__ import annotations

import json

import pytest

from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.game import equipment, loot, progression, rooms
from hack_and_slash.game.attributes import NEUTRAL, Attributes
from hack_and_slash.game.combat import roll_damage
from hack_and_slash.game.run import Run
from hack_and_slash.game.world import World

from .helpers import BESTIARY, HERO, open_room

TABLE = equipment.table()
OFFERS = rooms.table().stall_offers

#: Enough rooms that a claim about the roll is about the roll rather than about
#: one lucky index. A run has thirty-nine transitions.
ROOMS = range(39)

SEEDS = range(12)


def campaign(count: int = 3) -> Campaign:
    room = open_room(20, 20)
    return Campaign(
        name="test equipment",
        stages=tuple(
            Level(
                name=f"stage {i + 1}",
                rows=room.rows,
                hero_spawn=(4, 10),
                enemy_spawns=(EnemySpawn("grunt", (12, 10)),),
                tile=room.tile,
            )
            for i in range(count)
        ),
    )


def rich_run(gold: int = 100000, index: int = 0, seed: int = 5) -> Run:
    run = Run.start(campaign(), BESTIARY, seed=seed)
    run.gold = gold
    run.index = index
    return run


# --- the roll ----------------------------------------------------------------
def test_the_same_stall_offers_the_same_three_pieces() -> None:
    """The whole of the determinism claim, and the reason it is cheap.

    The stream is built from `(seed, index)` and thrown away, so this holds for
    a run loaded off disk as readily as for one played straight through -- there
    is no state for a save to fail to record. It is why `save.py` did not have
    to change for any of this.
    """
    for index in ROOMS:
        run = rich_run(index=index)
        assert equipment.offers(run) == equipment.offers(run)


def test_a_run_rebuilt_from_the_same_seed_finds_the_same_shelf() -> None:
    """The half of the above that a save actually depends on.

    Two separate `Run` objects, never having met, standing at the same index of
    the same seed. This is what `PlayScene` does when it is rebuilt from disk.
    """
    for index in (0, 7, 22, 38):
        assert equipment.offers(rich_run(index=index)) == equipment.offers(
            rich_run(index=index)
        )


def test_a_different_seed_is_a_different_run_of_stalls() -> None:
    """Otherwise every run of the game sells the same twelve things in order."""
    shelves = {
        tuple(offer.piece_id for offer in equipment.offers(rich_run(seed=seed)))
        for seed in SEEDS
    }
    assert len(shelves) > 1, "every seed rolled the same first stall"


def test_a_different_room_is_a_different_shelf() -> None:
    shelves = {
        tuple(offer.piece_id for offer in equipment.offers(rich_run(index=index)))
        for index in ROOMS
    }
    assert len(shelves) > 1, "every stall in a run sells the same three pieces"


def test_every_offer_is_a_distinct_piece() -> None:
    """Sampled without replacement. Two identical rows read as a bug rather than
    as a repeated option, which is the same reason `rooms.offer` draws distinct
    door kinds."""
    for seed in SEEDS:
        for index in ROOMS:
            offers = equipment.offers(rich_run(seed=seed, index=index))
            assert len(offers) == OFFERS
            assert len({offer.piece_id for offer in offers}) == OFFERS


def test_every_offer_has_its_own_key() -> None:
    """The key is what records the purchase, so two rows sharing one would mean
    buying the first greys out the second."""
    for index in (0, 11, 38):
        offers = equipment.offers(rich_run(index=index))
        assert len({offer.key for offer in offers}) == len(offers)


def test_every_key_is_namespaced_away_from_the_shop() -> None:
    """`run.purchases` carries both, and `shop.bought` looks up bare good ids."""
    for offer in equipment.offers(rich_run()):
        assert offer.key.startswith("eq:")


# --- the stream --------------------------------------------------------------
def _damage_over_a_fight(rolling: bool) -> list[int]:
    """The same seeded fight, optionally rolling stalls all the way through it."""
    world = World(open_room(), BESTIARY, seed=99)
    weapon = HERO.weapons[0]
    taken = []
    for tick in range(40):
        if rolling:
            # Every kind of draw this layer makes, interleaved as hard as it can
            # be with the fight -- which is far more than a real run ever does.
            equipment.offers(rich_run(index=tick, seed=tick))
            progression.offers(tick * 3, tick, 3)
        taken.append(roll_damage(weapon, world.rng))
    return taken


def test_the_stall_and_shrine_rolls_do_not_disturb_the_damage_stream() -> None:
    """The load-bearing test in this file, and it is checking a negative.

    `combat.roll_damage` draws from `world.rng`. If a stall roll ever drew from
    the same generator -- through a module-level `random.*` call, most likely --
    every damage roll after the first stall would shift, all 280 cells of the
    recorded grid would move, and every balance number would still read exactly
    as it does today.

    Note this rolls a `loot.roll_rarity` per offer, which is the draw most likely
    to be given the wrong generator: `loot.roll_drops` is normally handed
    `world.loot_rng`, and a copy-paste of that call site is how this breaks.
    """
    busy = _damage_over_a_fight(True)
    quiet = _damage_over_a_fight(False)

    assert busy == quiet, (
        "the damage rolls changed when stalls were rolled alongside them -- "
        "something in game/equipment.py is drawing from world.rng"
    )
    assert busy, "the fight rolled no damage at all, so it proves nothing"


def test_the_stall_and_the_shrine_do_not_draw_the_same_sequence() -> None:
    """Two rooms of one run should not agree by construction.

    Separate constants are the whole mechanism; if one were copied from the
    other, a shrine and a stall at the same index would be correlated and
    nothing else would say so.
    """
    assert rooms.STALL_STREAM != rooms.SHRINE_STREAM != rooms.MAP_STREAM
    a = [rooms.stall_stream(5, i).random() for i in ROOMS]
    b = [rooms.shrine_stream(5, i).random() for i in ROOMS]
    c = [rooms._stream(5, i).random() for i in ROOMS]
    assert a != b and b != c and a != c


# --- the arithmetic ----------------------------------------------------------
def test_a_deeper_floor_prices_the_same_piece_higher() -> None:
    """The same depth curve a kill and a chest already use.

    Asserted on `price_on` rather than on a rolled shelf, because two shelves at
    two indices are two different pieces at two different rarities and would
    prove nothing about the floor term.
    """
    prices = [TABLE.price_on(300, 1, floor) for floor in range(1, 41)]
    assert prices == sorted(prices)
    assert prices[0] < prices[-1]
    assert prices[0] == 300


def test_a_rarity_scales_the_block_and_the_price_by_the_same_factor() -> None:
    """What a rarity buys is a bigger purchase, never a better deal.

    If the two ever came apart, one tier would be strictly the correct thing to
    hold out for and the other four would be noise.
    """
    piece = TABLE.pieces[0]
    for rarity, scale in TABLE.rarity_scale.items():
        assert TABLE.price_on(piece.price, scale, 1) == piece.price * scale
        assert piece.attributes.scaled(scale) == _times(piece.attributes, scale)


def _times(block: Attributes, factor: int) -> Attributes:
    """The scaling written out long-hand, so the test is not the implementation."""
    return Attributes(
        max_hp=block.max_hp * factor,
        damage=block.damage * factor,
        defense=block.defense * factor,
        crit_chance=block.crit_chance * factor,
        crit_damage=block.crit_damage * factor,
        evasion=block.evasion * factor,
        regen=block.regen * factor,
        move_speed=block.move_speed * factor,
    )


def test_a_rolled_offer_agrees_with_the_table_it_came_from() -> None:
    """Ties the roll to the arithmetic, so neither can drift alone."""
    run = rich_run(index=9)
    for offer in equipment.offers(run):
        piece = next(p for p in TABLE.pieces if p.id == offer.piece_id)
        scale = TABLE.scale_of(offer.rarity)
        assert offer.attributes == piece.attributes.scaled(scale)
        assert offer.price == TABLE.price_on(piece.price, scale, run.index + 1)


def test_a_price_is_never_free() -> None:
    for seed in SEEDS:
        for index in ROOMS:
            for offer in equipment.offers(rich_run(seed=seed, index=index)):
                assert offer.price >= 1


# --- buying ------------------------------------------------------------------
def test_buying_writes_both_earned_and_the_live_body() -> None:
    """The half of a purchase that is easy to get half right.

    `run.earned` is what the next stage's `World` is handed; `hero.bonus` is what
    the sim reads on the body standing in this room. Writing only the first
    leaves the purchase inert until the boundary; only the second loses it at it.
    """
    run = rich_run()
    offer = equipment.offers(run)[0]

    assert equipment.buy(run, offer)
    assert run.earned == offer.attributes
    assert run.world.hero.bonus == run.earned


def test_buying_spends_exactly_the_price() -> None:
    run = rich_run(gold=100000)
    offer = equipment.offers(run)[0]
    before = run.gold

    assert equipment.buy(run, offer)
    assert run.gold == before - offer.price


def test_a_piece_cannot_be_bought_twice() -> None:
    """A rolled row is one purchase. Uncapped *pieces* are fine -- the pool is
    twelve and a stall shows three -- but one row buyable twice is a row that is
    buyable as many times as the purse allows, which is the failure the Charm's
    cap exists to prevent."""
    run = rich_run()
    offer = equipment.offers(run)[0]

    assert equipment.buy(run, offer)
    gold, earned = run.gold, run.earned

    assert not equipment.buy(run, offer)
    assert run.gold == gold and run.earned == earned
    assert equipment.taken(run, offer)
    assert not equipment.can_buy(run, offer)


def test_a_bought_piece_leaves_the_shelf() -> None:
    """One purchase per rolled row, so a bought one has nothing left to offer.

    The stall used to keep it and write `taken` beside it in red, which said the
    same thing and said it in the row a player was trying to read past.
    """
    run = rich_run()
    offers = equipment.offers(run)

    assert equipment.buy(run, offers[0])

    shelf = equipment.available(run, offers)
    assert offers[0] not in shelf
    assert shelf == offers[1:], "the rows that were not bought moved or vanished"


def test_the_roll_itself_is_never_filtered() -> None:
    """**The one that would be expensive to find out about later.**

    `offers` is the room's roll and a save records nothing about it: a run picked
    back up re-derives its shelf and finds its rows by index. Filter here and the
    piece at index 0 changes the moment anything is bought, so a reloaded run
    quietly shows a different shelf than the one it was put down in front of --
    and `run.purchases`, which is all that survives, would then be pointing at
    rows nobody chose.

    `test_save.py` is the end-to-end version of this. It passes unchanged, and
    that it did not have to change is the point.
    """
    run = rich_run()
    before = equipment.offers(run)

    for offer in before:
        assert equipment.buy(run, offer)

    assert equipment.offers(run) == before, "buying changed the roll"
    assert equipment.available(run, before) == (), "a bought-out stall kept a row"


def test_available_and_can_buy_never_disagree_about_a_bought_row() -> None:
    """The panel draws one and greys with the other, and a row that is drawn
    and refused is the failure both of them exist to rule out.

    Affordability is deliberately not in this claim: a row too expensive to buy
    stays on the shelf and greys, because the answer to it is more gold rather
    than a shorter shelf.
    """
    run = rich_run(gold=100000)
    offers = equipment.offers(run)
    assert equipment.buy(run, offers[1])

    for offer in equipment.available(run, offers):
        assert equipment.can_buy(run, offer), "a drawn row would refuse its own key"


def test_a_purchase_that_cannot_be_afforded_costs_nothing() -> None:
    """Refused rather than partial, the way `shop.buy` refuses."""
    run = rich_run(gold=0)
    offer = equipment.offers(run)[0]

    assert not equipment.can_buy(run, offer)
    assert not equipment.buy(run, offer)
    assert run.gold == 0
    assert run.earned is NEUTRAL


def test_can_buy_agrees_with_buy_on_every_offer() -> None:
    """The contract the panel greys rows out on. If these ever disagreed, a row
    a player is shown and what happens when they press it would be two different
    answers -- which is the reason `shop.can_buy` exists at all."""
    for gold in (0, 200, 800, 100000):
        for index in (0, 13, 38):
            run = rich_run(gold=gold, index=index)
            for offer in equipment.offers(run):
                expected = equipment.can_buy(run, offer)
                assert equipment.buy(run, offer) is expected


def test_two_purchases_accumulate() -> None:
    run = rich_run()
    first, second = equipment.offers(run)[:2]

    assert equipment.buy(run, first)
    assert equipment.buy(run, second)
    assert run.earned == first.attributes + second.attributes


def test_a_purchase_survives_the_stage_boundary() -> None:
    """`run.earned` is handed to the next `World` as `hero_bonus`. This is the
    end-to-end version of the two-halves test above."""
    run = rich_run()
    offer = equipment.offers(run)[0]
    assert equipment.buy(run, offer)

    for enemy in run.world.enemies():
        enemy.hp = 0
    from hack_and_slash.game.sim import step

    step(run.world)
    run.settle()

    assert run.world.hero.bonus == offer.attributes


# --- the content file --------------------------------------------------------
def test_the_shipped_pool_matches_the_file_on_disk() -> None:
    """The pool the game plays with is the one in the repo, not a default."""
    from hack_and_slash import config

    payload = json.loads(config.EQUIPMENT_DATA.read_text(encoding="utf-8"))
    named = {k for k in payload["pieces"] if not k.startswith("_")}
    assert {piece.id for piece in TABLE.pieces} == named


def test_every_attribute_is_reachable_through_the_pool() -> None:
    """No attribute may be shrine-only.

    Not a rule about fairness -- it is what stops an attribute quietly becoming
    unreachable the day somebody trims the pool, which nothing else would report.
    """
    covered = {
        name
        for piece in TABLE.pieces
        for name in progression.SPENDABLE
        if getattr(piece.attributes, name)
    }
    assert covered == set(progression.SPENDABLE), (
        f"no piece carries {sorted(set(progression.SPENDABLE) - covered)}"
    )


def _written(tmp_path, payload) -> object:
    path = tmp_path / "equipment.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _shipped() -> dict:
    from hack_and_slash import config

    return json.loads(config.EQUIPMENT_DATA.read_text(encoding="utf-8"))


def test_a_piece_with_three_attributes_is_refused_at_load(tmp_path) -> None:
    """A layout rule, checked because a piece is content and content is added by
    somebody who is not looking at a 384px panel at the time."""
    payload = _shipped()
    payload["pieces"]["overloaded"] = {
        "name": "Overloaded",
        "price": 100,
        "attributes": {"max_hp": 1, "damage": 1, "defense": 1},
    }
    with pytest.raises(ValueError, match="attributes"):
        equipment.Table.load(_written(tmp_path, payload))


def test_a_rarity_the_pool_cannot_price_is_refused_at_load(tmp_path) -> None:
    payload = _shipped()
    del payload["rarity_scale"]["legendary"]
    with pytest.raises(KeyError, match="legendary"):
        equipment.Table.load(_written(tmp_path, payload))


def test_a_price_for_a_rarity_that_does_not_exist_is_refused_at_load(tmp_path) -> None:
    payload = _shipped()
    payload["rarity_scale"]["mythic"] = 9
    with pytest.raises(ValueError):
        equipment.Table.load(_written(tmp_path, payload))


def test_an_unknown_attribute_is_refused_at_load(tmp_path) -> None:
    """Through `Attributes.from_dict`, which already raises -- asserted here so
    the guarantee is known to reach this file rather than assumed to."""
    payload = _shipped()
    payload["pieces"]["typo"] = {
        "name": "Typo",
        "price": 100,
        "attributes": {"crit_rate": 10},
    }
    with pytest.raises(KeyError, match="crit_rate"):
        equipment.Table.load(_written(tmp_path, payload))


def test_an_empty_pool_is_refused_at_load(tmp_path) -> None:
    payload = _shipped()
    payload["pieces"] = {}
    with pytest.raises(ValueError, match="empty"):
        equipment.Table.load(_written(tmp_path, payload))


# --- the rollback ------------------------------------------------------------
def test_a_stall_offering_nothing_is_the_shop_exactly_as_it_was(monkeypatch) -> None:
    """`stall.offers: 0` in `data/rooms.json`, the narrow rollback.

    The panel then draws the five goods and nothing above them, which is the
    shop this replaced. Asserted rather than assumed, because it is the thing
    somebody will reach for at two in the morning.
    """
    import dataclasses

    monkeypatch.setattr(
        rooms, "_TABLE", dataclasses.replace(rooms.table(), stall_offers=0)
    )
    assert equipment.offers(rich_run()) == ()


def test_more_offers_than_pieces_is_refused(monkeypatch) -> None:
    import dataclasses

    monkeypatch.setattr(
        rooms,
        "_TABLE",
        dataclasses.replace(rooms.table(), stall_offers=len(TABLE.pieces) + 1),
    )
    with pytest.raises(ValueError, match="stall.offers"):
        equipment.offers(rich_run())


# --- the blurb ---------------------------------------------------------------
def test_a_blurb_names_every_attribute_the_block_carries() -> None:
    for piece in TABLE.pieces:
        for name in progression.SPENDABLE:
            if getattr(piece.attributes, name):
                assert equipment.LABELS[name] in piece.blurb


def test_a_neutral_block_describes_as_nothing() -> None:
    assert equipment.describe(NEUTRAL) == ""


def test_the_two_panels_call_the_eight_attributes_the_same_things() -> None:
    """`render/level_panel.py` names them for the shrine and this names them for
    the stall. Two vocabularies is a thing a player would have to learn twice."""
    from hack_and_slash.render import level_panel

    assert equipment.LABELS == level_panel.LABELS


def test_every_rarity_the_loot_table_can_roll_has_a_scale() -> None:
    """The other direction of the load-time check, asserted against the live
    table rather than against a fixture."""
    for tier in loot.table().tiers:
        assert TABLE.scale_of(tier.rarity) >= 1
