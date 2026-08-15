"""What a kill is worth, and the guarantee that working it out changes nothing.

The load-bearing test in this file is
`test_loot_rolls_do_not_disturb_the_damage_stream`. Everything else checks that
the numbers come out right; that one checks that asking for them at all has not
quietly rewritten every fight in the game.
"""

from __future__ import annotations

import random

from hack_and_slash import config
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game.loot import LootTable, Pickup, Rarity, table

from .helpers import BESTIARY


TABLE = table()


def rng(seed: int = 5) -> random.Random:
    return random.Random(seed)


# --- the file itself ---------------------------------------------------------
def test_the_shipped_table_loads() -> None:
    assert TABLE.item_chance > 0
    assert TABLE.gold_base > 0
    assert [tier.rarity for tier in TABLE.tiers] == list(Rarity)


def test_rarer_tiers_are_worth_more_and_drop_less() -> None:
    """The one relationship that makes a rarity mean anything.

    Values are not pinned -- they are a first pass and `data/loot.json` says so.
    The ordering is pinned, because a table where an epic is commoner or cheaper
    than a rare is not a mistuned game, it is a broken one.
    """
    for better, worse in zip(TABLE.tiers[1:], TABLE.tiers):
        assert better.worth > worse.worth, f"{better.rarity} is worth no more than {worse.rarity}"
        assert better.weight < worse.weight, f"{better.rarity} is no rarer than {worse.rarity}"


def test_comment_keys_are_not_loaded_as_shop_stock() -> None:
    assert all(not key.startswith("_") for key in TABLE.shop)


def test_a_table_with_no_weight_anywhere_is_refused(tmp_path) -> None:
    """Every weight at zero is a division by zero mid-fight, not "no drops".

    Refused at load, where the file can be named, rather than raising out of
    `roll_rarity` several stages into a run.
    """
    broken = tmp_path / "loot.json"
    broken.write_text(
        '{"gold": {"base": 1, "floor_step": 0, "variance": 0}, "item_chance": 1,'
        ' "rarities": [{"id": "common", "weight": 0, "worth": 1}], "shop": {}}',
        encoding="utf-8",
    )
    try:
        LootTable.load(broken)
    except ValueError as exc:
        assert "weights sum to zero" in str(exc)
        assert "loot.json" in str(exc)
    else:
        raise AssertionError("a table that can never roll a tier was accepted")


# --- the gold formula --------------------------------------------------------
def test_a_bigger_monster_pays_more_on_the_same_floor() -> None:
    """The whole point of monster level being separate from floor.

    Averaged over many rolls rather than compared once, because the payout has
    variance in it and a single pair of rolls can come out the wrong way round
    without anything being wrong.
    """
    rat = _mean(lambda r: TABLE.gold_for(1, 5, r))
    sovereign = _mean(lambda r: TABLE.gold_for(8, 5, r))
    assert sovereign > rat * 5


def test_the_same_monster_pays_more_deeper_in() -> None:
    shallow = _mean(lambda r: TABLE.gold_for(2, 1, r))
    deep = _mean(lambda r: TABLE.gold_for(2, 20, r))
    assert deep > shallow * 2


def test_gold_find_raises_the_payout_by_the_fraction_it_says() -> None:
    plain = _mean(lambda r: TABLE.gold_for(4, 10, r))
    found = _mean(lambda r: TABLE.gold_for(4, 10, r, find=0.5))
    assert 1.4 < found / plain < 1.6


def test_a_kill_never_pays_nothing() -> None:
    """A payout of zero reads as a bug, exactly as a hit for zero damage would.

    Checked against a table deliberately tuned so low that the arithmetic would
    round to zero, which is the only way this can go wrong.
    """
    stingy = LootTable(
        gold_base=0.01, floor_step=0.0, variance=0.0, item_chance=0.0,
        scatter=0.0, tiers=TABLE.tiers, shop={},
    )
    for seed in range(50):
        assert stingy.gold_for(1, 1, rng(seed)) >= 1


def test_the_floor_number_is_never_read_as_a_penalty() -> None:
    """Floor 0 and floor 1 pay the same.

    `World` defaults its floor to 1 and every test that predates loot uses that
    default, but a tool could hand it a zero-based index by mistake. Clamped, so
    the worst case is a payout that is merely wrong rather than negative.
    """
    assert TABLE.gold_for(3, 0, rng(1)) == TABLE.gold_for(3, 1, rng(1))


# --- rarity ------------------------------------------------------------------
def test_rarity_comes_out_in_roughly_the_stated_proportions() -> None:
    """Weights are relative, so this is the only place the percentages appear.

    Loose brackets: it is checking that the weights are being used at all and in
    the right direction, not re-deriving the arithmetic of a weighted choice.
    """
    generator = rng(99)
    rolls = [TABLE.roll_rarity(generator) for _ in range(20000)]
    share = {r: rolls.count(r) / len(rolls) for r in Rarity}

    assert 0.55 < share[Rarity.COMMON] < 0.65
    assert 0.20 < share[Rarity.UNCOMMON] < 0.30
    assert 0.005 < share[Rarity.LEGENDARY] < 0.02
    # And the ladder holds all the way down, which the brackets alone do not say.
    ordered = [share[r] for r in Rarity]
    assert ordered == sorted(ordered, reverse=True)


def test_an_items_worth_scales_with_its_rarity() -> None:
    for better, worse in zip(TABLE.tiers[1:], TABLE.tiers):
        assert TABLE.worth_of(better.rarity) > TABLE.worth_of(worse.rarity)


# --- drops -------------------------------------------------------------------
def test_every_kill_drops_gold_and_only_sometimes_an_item() -> None:
    generator = rng(3)
    drops = [TABLE.roll_drops(2, 4, Vec2(50, 50), generator) for _ in range(400)]

    assert all(len(batch) in (1, 2) for batch in drops)
    assert all(batch[0].rarity is None for batch in drops), "the first drop is always coin"

    with_item = [batch for batch in drops if len(batch) == 2]
    assert 0.15 < len(with_item) / len(drops) < 0.35
    assert all(batch[1].is_item for batch in with_item)


def test_an_item_is_worth_a_multiple_of_the_coin_beside_it() -> None:
    generator = rng(11)
    for _ in range(300):
        batch = TABLE.roll_drops(3, 7, Vec2(0, 0), generator)
        if len(batch) != 2:
            continue
        coin, item = batch
        assert item.gold >= coin.gold, f"a {item.rarity} was worth less than the coin"


def test_drops_scatter_so_two_things_do_not_land_as_one() -> None:
    generator = rng(2)
    for _ in range(200):
        batch = TABLE.roll_drops(3, 3, Vec2(100, 100), generator)
        if len(batch) == 2:
            assert batch[0].pos != batch[1].pos
            return
    raise AssertionError("no kill in 200 dropped an item to compare positions with")


def test_the_same_seed_drops_the_same_loot() -> None:
    """Loot is part of a replay, not a decoration on top of one."""
    first = [TABLE.roll_drops(4, 9, Vec2(0, 0), rng(77)) for _ in range(1)]
    second = [TABLE.roll_drops(4, 9, Vec2(0, 0), rng(77)) for _ in range(1)]
    assert first == second


def test_a_pickup_knows_whether_it_is_a_coin_or_a_valuable() -> None:
    coin = Pickup(pos=Vec2(0, 0), gold=5)
    relic = Pickup(pos=Vec2(0, 0), gold=40, rarity=Rarity.EPIC)

    assert not coin.is_item and coin.sprite == "coin"
    assert relic.is_item and relic.sprite == "relic"
    assert relic.sprite in config.SPRITE_ORDER and coin.sprite in config.SPRITE_ORDER


def test_every_rarity_has_a_colour_to_draw_it_in() -> None:
    """The colour is the whole difference between a common and a legendary --
    there is one relic sprite for all five tiers."""
    for rarity in Rarity:
        assert rarity.value in config.RARITY_COLORS


# --- the guarantee -----------------------------------------------------------
def test_every_enemy_can_be_paid_for() -> None:
    """A level of 1 on a real enemy would pay a rat's wage silently."""
    for entity_type in BESTIARY.types.values():
        assert TABLE.gold_for(entity_type.level, 1, rng()) >= 1


def _mean(roll, samples: int = 400) -> float:
    generator = rng(4242)
    return sum(roll(generator) for _ in range(samples)) / samples


# --- in a live world ---------------------------------------------------------
def test_loot_rolls_do_not_disturb_the_damage_stream() -> None:
    """The load-bearing test in this file.

    `combat.roll_damage` draws from `world.rng`. If a loot roll ever drew from
    the same generator, every damage roll after the first kill would shift, and
    all hundred cells of the recorded class-by-stage grid would move without a
    single balance number being touched -- silently, and with nothing else in
    the suite to catch it.

    So: run the same seeded fight twice, once with drops worth having and once
    with the loot layer turned off entirely, and assert the damage came out
    identical. It is the only way to check a negative like this.
    """
    generous = LootTable(
        gold_base=50.0, floor_step=0.5, variance=0.4, item_chance=1.0,
        scatter=6.0, tiers=TABLE.tiers, shop={},
    )
    silent = LootTable(
        gold_base=1.0, floor_step=0.0, variance=0.0, item_chance=0.0,
        scatter=0.0, tiers=TABLE.tiers, shop={},
    )

    rich = _damage_taken_over_a_fight(generous)
    poor = _damage_taken_over_a_fight(silent)

    assert rich == poor, (
        "the damage rolls changed when the loot table did -- something in the "
        "loot layer is drawing from world.rng"
    )
    assert rich, "the fight did no damage at all, so it proves nothing"


def test_a_kill_leaves_something_on_the_floor() -> None:
    """Killed with a friend still standing, so the room is not clear.

    A stage with one enemy in it cannot show this: killing the only enemy wins
    the stage, the sweep fires on the same tick, and the floor is bare again
    before anything can look at it.
    """
    world = _world_with_two_enemies()
    _kill_one(world)

    assert world.pickups, "a dead grunt dropped nothing"
    assert any(not p.is_item for p in world.pickups), "no gold dropped"
    assert world.gold == 0, "it was banked without the hero going near it"


def test_a_pickup_is_never_an_entity() -> None:
    """A coin in `world.entities` would be seen by the broadphase, the
    separation pass and every AI brain in the game."""
    world = _world_with_two_enemies()
    _kill_one(world)

    assert world.pickups
    assert all(not hasattr(p, "hp") for p in world.pickups)
    assert len(world.entities) == 2, "a pickup got into the entity list"


def test_walking_over_gold_banks_it() -> None:
    from hack_and_slash.game.sim import step

    world = _world_with_one_enemy(kill=False)
    hero = world.hero
    # Placed by hand rather than fought for, so this is a test about collection
    # and not about whether a grunt happened to die somewhere reachable.
    world.pickups.append(Pickup(pos=hero.pos, gold=17))

    step(world, NOTHING)
    assert world.gold == 17
    assert not world.pickups


def test_gold_out_of_reach_stays_on_the_floor() -> None:
    from hack_and_slash.game.sim import step

    world = _world_with_one_enemy(kill=False)
    hero = world.hero
    world.pickups.append(Pickup(pos=hero.pos + Vec2(120, 0), gold=17))

    step(world, NOTHING)
    assert world.gold == 0
    assert len(world.pickups) == 1


def test_collecting_gold_says_so_and_says_what_rarity() -> None:
    from hack_and_slash.game.events import EventKind
    from hack_and_slash.game.sim import step

    world = _world_with_one_enemy(kill=False)
    hero = world.hero
    world.pickups.append(Pickup(pos=hero.pos, gold=9, rarity=Rarity.EPIC))

    step(world, NOTHING)
    picked = [e for e in world.events if e.kind is EventKind.PICKUP]
    assert len(picked) == 1
    assert picked[0].amount == 9
    assert picked[0].rarity == "epic"


def test_the_last_kill_s_drop_is_swept_up_rather_than_lost() -> None:
    """The trap this whole design is shaped around.

    A stage is won the tick its last enemy dies, and `Run._advance` builds the
    next `World` on that same tick -- so a drop from the final kill has no tick
    in which it could be walked over. The sweep collects everything the moment
    the room is clear, which is the only reason clearing a stage is not a way to
    lose money.
    """
    from hack_and_slash.game.world import Outcome

    world = _world_with_one_enemy()
    _kill_everything(world)

    assert world.outcome is Outcome.WON
    assert not world.pickups, "loot was left on the floor of a cleared stage"
    assert world.gold > 0, "clearing the stage collected nothing"


def test_a_hero_who_dies_banks_nothing_more() -> None:
    from hack_and_slash.game.sim import step

    world = _world_with_one_enemy(kill=False)
    hero = world.hero
    world.pickups.append(Pickup(pos=hero.pos, gold=99))
    hero.hp = 0

    step(world, NOTHING)
    assert world.gold == 0


def test_a_deeper_floor_pays_more_for_the_same_enemy() -> None:
    """End to end, through the world rather than through the formula."""
    shallow = sum(_stage_income(floor=1, seed=s) for s in range(12))
    deep = sum(_stage_income(floor=20, seed=s) for s in range(12))
    assert deep > shallow * 2


def test_gold_find_is_applied_where_the_drop_lands() -> None:
    plain = sum(_stage_income(floor=5, seed=s) for s in range(12))
    found = sum(_stage_income(floor=5, seed=s, find=1.0) for s in range(12))
    assert 1.7 < found / plain < 2.3


# --- fixtures ----------------------------------------------------------------
from hack_and_slash.game.intent import NOTHING  # noqa: E402
from hack_and_slash.game.world import Purse, World  # noqa: E402

from .helpers import add_enemy, level_with, make_world  # noqa: E402


def _world_with_one_enemy(kill: bool = True, floor: int = 1, seed: int = 3, find: float = 0.0):
    world = World(
        level_with((10, 10), [("grunt", (4, 4))]),
        BESTIARY,
        seed=seed,
        purse=Purse(floor=floor, gold_find=find),
    )
    return world


def _world_with_two_enemies(seed: int = 3):
    """Somewhere a kill can happen without the stage being cleared by it.

    The second enemy is parked far from the hero so it neither reaches the fight
    nor wanders onto the loot the first one dropped.
    """
    return World(
        level_with((10, 10), [("grunt", (4, 4)), ("grunt", (17, 17))]),
        BESTIARY,
        seed=seed,
    )


def _kill_one(world) -> None:
    from hack_and_slash.game.sim import step

    world.enemies()[0].hp = 0
    step(world, NOTHING)


def _kill_everything(world) -> None:
    """Set every enemy's health to zero and let the sim notice.

    Killed by fiat rather than by fighting: this file is about what a death
    produces, and a test that has to win a fight first fails for reasons that
    have nothing to do with loot.
    """
    from hack_and_slash.game.sim import step

    for enemy in world.enemies():
        enemy.hp = 0
    step(world, NOTHING)


def _stage_income(floor: int, seed: int, find: float = 0.0) -> int:
    world = _world_with_one_enemy(floor=floor, seed=seed, find=find)
    _kill_everything(world)
    return world.gold


def _damage_taken_over_a_fight(loot_table: LootTable) -> list[int]:
    """Every hit landed in one seeded fight, with a given loot table in force.

    Monkeypatched rather than injected: `loot.table()` is the shipped content
    and there is no seam to pass another through, which is correct -- the game
    has one loot table and inventing a way to have two would be a worse design
    than a test that swaps it for a moment.
    """
    from hack_and_slash.game import loot as loot_module
    from hack_and_slash.game.events import EventKind
    from hack_and_slash.game.sim import step

    original = loot_module._TABLE
    loot_module._TABLE = loot_table
    try:
        world = World(
            level_with((10, 10), [("grunt", (9, 10)), ("rat", (11, 10)), ("grunt", (10, 9))]),
            BESTIARY,
            seed=4242,
        )
        damage = []
        for _ in range(600):
            step(world, NOTHING)
            damage.extend(e.amount for e in world.events if e.kind is EventKind.HIT)
        return damage
    finally:
        loot_module._TABLE = original
