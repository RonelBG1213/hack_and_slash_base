"""Status effects, and the claim that nothing in the game has one.

The substrate landed before the content, deliberately: `docs/roadmap.md` calls
status effects "the substrate the gear gap is missing", and the cheapest honest
way to add one to a tuned game is to add the *mechanism* at rest and prove it
inert before a single weapon opts in.

The substrate shipped first and empty, and then **three** attacks opted in --
the Assassin's Deathmark, the Magic Archer's Runeshot and the Wizard's
Cataclysm. All three are a promoted class's heavy or ultimate, which is the only
place in the game a status is invisible to the recorded grid: the reference bot
presses the light attack and nothing else, and it is `INFLICTING` below that
says so as a list rather than as a hope. A status on an *enemy* weapon would
move all 280 cells on the day it landed, and there is a test for that too.

**Three of the four effects needed no arithmetic at all.** A vulnerability is a
negative `defense`, which `combat.resolve_damage` has always subtracted; a slow
is a negative `move_speed`, which `sim._walk_speed` has always multiplied by; a
burn is a negative `regen`, which is the one that needed a branch. What they
needed was a slot to sit in and a timer to take them off again.
"""

from __future__ import annotations

from dataclasses import replace

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import actions, combat, difficulty, skills
from hack_and_slash.game.attributes import NEUTRAL, PER_MILLE, Attributes
from hack_and_slash.game.entities import ActionState, Faction
from hack_and_slash.game.events import EventKind
from hack_and_slash.game.intent import Intent
from hack_and_slash.game.sim import _walk_speed, step
from hack_and_slash.game.world import Projectile, World

from .helpers import BESTIARY, add_enemy, make_world, open_room, run

RIGHT = Vec2(1, 0)

BURN = Attributes(regen=-50)
SLOW = Attributes(move_speed=-500)
VULNERABLE = Attributes(defense=-3)


# --- the claim ---------------------------------------------------------------
#: Every attack in the game that leaves something behind, and what it leaves.
#: Pinned as a list rather than counted, in `test_bindings.py`'s image -- the
#: useful failure is not "the number changed", it is *this weapon started
#: inflicting and nobody said so*, because each of the three below is on a slot
#: chosen so the recorded grid cannot see it.
INFLICTING = {
    "assassin_deathmark": "defense",
    "magic_archer_runeshot": "move_speed",
    "wizard_cataclysm": "regen",
}


def inflicting() -> dict:
    return {
        weapon.id: entity_type
        for entity_type in BESTIARY.types.values()
        for weapon in entity_type.weapons
        if weapon.is_inflicting
    }


def test_exactly_three_attacks_inflict_anything() -> None:
    """The inventory, and the reason it is worth having as a list.

    Every one of the three is an advanced class's heavy or ultimate, which is
    the only place in the game a status is invisible to the recorded grid: the
    reference bot presses the light attack and nothing else. A fourth entry
    arriving without a decision behind it is exactly what this catches."""
    assert set(inflicting()) == set(INFLICTING)


def test_no_enemy_attack_inflicts_anything() -> None:
    """**The one that would move all 280 cells on the day it landed.** Every
    enemy attack is pressed by the sim on every measured tick, so a burn on a
    grunt is a change to every recorded number rather than to a slot nobody
    swept."""
    for entity_type in BESTIARY.types.values():
        if entity_type.faction is not Faction.ENEMY:
            continue
        for weapon in entity_type.weapons:
            assert not weapon.is_inflicting, f"{entity_type.id}'s {weapon.id} inflicts"


def test_no_light_attack_inflicts_anything() -> None:
    """The slot the reference bot presses, and the reason every recorded number
    still measures what it measured. `data/weapons.json` says the same thing
    from the other side: leaving the five lights untouched is what keeps the
    grid meaningful."""
    for entity_type in BESTIARY.types.values():
        if entity_type.faction is not Faction.HERO:
            continue
        assert not entity_type.weapons[skills.LIGHT].is_inflicting, entity_type.id


def test_nothing_inflicted_touches_max_hp() -> None:
    """`test_no_buff_grants_max_hp`'s argument, pointed at the layer that can be
    applied by somebody else. A ceiling that drops under a body standing above
    it is bad enough when the body asked for it."""
    for weapon_id, entity_type in inflicting().items():
        weapon = next(w for w in entity_type.weapons if w.id == weapon_id)
        assert weapon.inflict.max_hp == 0, weapon_id


def test_no_inflicted_slow_can_root_a_body() -> None:
    """Nothing paths around walls in this game, so a monster that cannot walk is
    a stage that never ends -- the same refusal `data/elites.json` makes at
    load, made here about the other half of the layer."""
    for weapon_id, entity_type in inflicting().items():
        weapon = next(w for w in entity_type.weapons if w.id == weapon_id)
        assert weapon.inflict.move_speed > -PER_MILLE, weapon_id


def test_every_inflicting_attack_is_a_promoted_slot() -> None:
    """Which is the whole of why these three could ship without a sweep."""
    for weapon_id, entity_type in inflicting().items():
        assert entity_type.promotes_from, f"{entity_type.id} is not a promoted class"
        index = [w.id for w in entity_type.weapons].index(weapon_id)
        assert index in (skills.HEAVY, skills.ULTIMATE), weapon_id


def test_every_body_starts_with_the_shared_neutral_status() -> None:
    """By identity, because `Entity.attrs` tests it that way -- an
    equal-but-distinct block would put an eight-field sum on every body on every
    tick of a 300,000-tick run."""
    world = make_world()
    add_enemy(world, "grunt", Vec2(200, 200))
    for entity in world.entities:
        assert entity.status is NEUTRAL
        assert entity.status_ticks == 0


def test_a_neutral_status_is_the_attribute_sum_that_was_measured() -> None:
    world = make_world()
    hero = world.hero
    before = hero.attrs

    hero.status = NEUTRAL
    assert hero.attrs == before


def test_a_status_draws_no_dice() -> None:
    """The layer adds no randomness anywhere, so it cannot shift the sequence a
    damage roll draws from however it is used. A proc chance would have to draw
    from `world.attr_rng` like `combat.evades`, never from `world.rng`."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(160, 200))
    enemy.status, enemy.status_ticks = BURN, 600

    before = world.rng.getstate()
    run(world, 30)
    after = world.rng.getstate()

    # The hero is not swinging, so nothing should have drawn at all -- and the
    # burn certainly should not have.
    assert before == after


# --- the slot ----------------------------------------------------------------
def test_a_status_is_a_fourth_addend_and_not_the_buff_slot() -> None:
    """The two look alike and may never share a slot: `apply_buff` replaces
    rather than stacks, and `render/hud.py` lights the Q pip off `buff_ticks`.
    A hero set alight would light their own skill pip."""
    world = make_world()
    hero = world.hero

    hero.buff, hero.buff_ticks = Attributes(defense=4), 60
    actions.apply_status(hero, VULNERABLE, 60)

    assert hero.buff == Attributes(defense=4), "the status wiped the buff"
    assert hero.buff_ticks == 60
    assert hero.attrs.defense == 4 - 3, "both halves are in the sum"


def test_casting_a_buff_does_not_put_out_a_fire() -> None:
    world = make_world()
    hero = world.hero
    actions.apply_status(hero, BURN, 120)

    hero.buff, hero.buff_ticks = Attributes(defense=4), 60

    assert hero.status is BURN
    assert hero.status_ticks == 120


def test_a_status_replaces_rather_than_stacking() -> None:
    """The reading that stays correct when two attacks inflict two different
    things -- and the one that stops an attack ratcheting itself upward by being
    landed on time."""
    world = make_world()
    hero = world.hero

    actions.apply_status(hero, BURN, 120)
    actions.apply_status(hero, SLOW, 30)

    assert hero.status is SLOW
    assert hero.status_ticks == 30


def test_a_status_with_no_duration_is_inert() -> None:
    """`is_inflicting` reads the duration, so a block with no ticks is nothing
    at all rather than something permanent -- the safe way round, and the same
    way `is_buff` reads."""
    world = make_world()
    actions.apply_status(world.hero, BURN, 0)
    assert world.hero.status is NEUTRAL


def test_a_status_expires_back_to_the_shared_neutral_singleton() -> None:
    world = make_world()
    hero = world.hero
    actions.apply_status(hero, SLOW, 3)

    run(world, 3)

    assert hero.status_ticks == 0
    assert hero.status is NEUTRAL, "expired to an equal block rather than the singleton"


# --- where it is applied -----------------------------------------------------
def burning_grunt(world: World, ticks: int = 90):
    """A grunt whose attack sets things alight."""
    enemy = add_enemy(world, "grunt", Vec2(200, 200))
    burning = replace(enemy.type.weapons[0], inflict=BURN, inflict_ticks=ticks)
    enemy.type = replace(enemy.type, weapons=(burning,))
    return enemy


def test_a_confirmed_blow_inflicts_its_weapon_s_status() -> None:
    world = make_world()
    enemy = burning_grunt(world)
    hero = world.hero

    assert combat.apply_hit(world, enemy, hero, enemy.weapon, world.rng)

    assert hero.status is BURN
    assert hero.status_ticks == 90


def test_an_evaded_blow_inflicts_nothing() -> None:
    """Past the gate, so a blow that was avoided leaves nothing behind --
    exactly as it lands no damage, no knockback and no stagger."""
    world = make_world()
    enemy = burning_grunt(world)
    hero = world.hero
    hero.bonus = Attributes(evasion=PER_MILLE - 1)

    assert not combat.apply_hit(world, enemy, hero, enemy.weapon, world.rng)
    assert hero.status is NEUTRAL


def test_a_blow_eaten_by_iframes_inflicts_nothing() -> None:
    world = make_world()
    enemy = burning_grunt(world)
    hero = world.hero
    hero.iframes = 10

    assert not combat.apply_hit(world, enemy, hero, enemy.weapon, world.rng)
    assert hero.status is NEUTRAL


def test_a_projectile_carries_its_status_to_where_it_lands() -> None:
    """A shot knows its `owner_id` and not its owner, and the owner may be dead
    and culled by the time it arrives -- so the block rides on the shot, exactly
    as its damage and knockback already do."""
    world = make_world()
    target = add_enemy(world, "grunt", Vec2(210, 200))
    hero = world.hero

    world.spawn_projectile(
        Projectile(
            id=world.take_projectile_id(),
            owner_id=hero.id,
            faction=hero.type.faction,
            pos=Vec2(target.pos.x - 6, target.pos.y),
            velocity=RIGHT * 4.0,
            radius=3.0,
            damage=4,
            knockback=0.0,
            ticks_left=30,
            inflict=BURN,
            inflict_ticks=45,
        )
    )

    world.rebuild_index()
    combat.resolve_projectile_hits(world)

    assert target.status is BURN
    assert target.status_ticks == 45


# --- vulnerability, which needed nothing -------------------------------------
def test_a_vulnerability_makes_a_blow_land_harder() -> None:
    world = make_world()
    plain = add_enemy(world, "grunt", Vec2(200, 200))
    weak = add_enemy(world, "grunt", Vec2(240, 200))
    weak.status, weak.status_ticks = VULNERABLE, 60

    hero = world.hero
    hard, _ = combat.resolve_damage(10, hero.attrs, weak.attrs, world.attr_rng)
    soft, _ = combat.resolve_damage(10, hero.attrs, plain.attrs, world.attr_rng)

    assert hard > soft


def test_a_vulnerability_cannot_take_a_blow_past_the_floor() -> None:
    """`combat.MIN_DAMAGE` is a floor and not a cap, so a negative defense adds
    where a positive one subtracts -- and nothing underneath it changes."""
    world = make_world()
    hero = world.hero
    damage, _ = combat.resolve_damage(1, hero.attrs, VULNERABLE, world.attr_rng)
    assert damage >= combat.MIN_DAMAGE


# --- the slow ----------------------------------------------------------------
def test_a_slow_slows_a_body() -> None:
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(200, 200))
    quick = _walk_speed(enemy)

    enemy.status, enemy.status_ticks = SLOW, 60
    assert 0 < _walk_speed(enemy) < quick


def test_a_slow_can_stop_a_body_and_can_never_reverse_it() -> None:
    """Past -1000 the product turns negative, which does not stop a body -- it
    marches it away from what it was chasing, into a wall. A stopped body is a
    body a slow made useless; a reversed one is a bug wearing a status."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(200, 200))

    enemy.status, enemy.status_ticks = Attributes(move_speed=-PER_MILLE), 60
    assert _walk_speed(enemy) == 0.0

    enemy.status = Attributes(move_speed=-PER_MILLE * 3)
    assert _walk_speed(enemy) == 0.0


def test_the_speed_of_an_unslowed_body_is_still_its_own_number() -> None:
    """The identity branch, untouched: `max(0.0, x)` returns a new float, so
    folding the clamp into one expression would break the `is` this asserts."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(200, 200))
    assert _walk_speed(enemy) is enemy.type.speed


# --- the burn ----------------------------------------------------------------
def test_a_burn_pays_out_in_whole_points_like_regen_does() -> None:
    """Banked in hundredths and paid whole, because nothing anywhere may hold a
    fractional hit point -- a float bank would drift over 300,000 ticks and a
    seeded run has to replay exactly."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    enemy.status, enemy.status_ticks = Attributes(regen=-25), 600
    full = enemy.hp

    run(world, 4)
    assert enemy.hp == full - 1


def test_a_burn_and_a_heal_of_one_size_are_one_schedule() -> None:
    """The burn drains its bank on the magnitude, not on the signed value.

    `divmod` floors toward minus infinity, so draining the negative bank
    directly paid out on tick 1 where the mirror-image heal waits until tick 9 --
    same number, opposite sign, different behaviour. Asserted as the two halves
    side by side rather than as a tick count on its own, because the claim worth
    keeping is that they *match*, not that either lands on nine.
    """
    def first_payout(regen: int) -> int:
        # The hero, not a grunt: this has to run for tens of ticks with room to
        # move in both directions, and a grunt has 18 hit points to do it in.
        world = make_world()
        hero = world.hero
        hero.hp = hero.max_hp - 40
        hero.status, hero.status_ticks = Attributes(regen=regen), 600
        start = hero.hp
        for tick in range(1, 60):
            step(world, Intent())
            if hero.hp != start:
                return tick
        raise AssertionError(f"nothing paid out at regen={regen}")

    assert first_payout(-12) == first_payout(12) == 9


def test_a_burn_pays_the_whole_number_of_points_it_accrued() -> None:
    """Rounding down, exactly as the healing branch does. Draining the negative
    bank directly rounded *up* -- 22 points where 2160 hundredths accrued."""
    world = make_world()
    hero = world.hero
    hero.status, hero.status_ticks = Attributes(regen=-12), 600
    full = hero.hp

    run(world, 180)
    assert full - hero.hp == 21  # 180 * 12 == 2160 hundredths


def test_a_spent_burn_leaves_no_credit_behind_for_the_next_one() -> None:
    """The residue was the second half of the same bug. Nothing drained the
    bank when a status expired, so a body that had been burned once carried a
    part-paid point into every status that landed on it afterwards -- and a
    `vital` champion carried it as free healing for the rest of the stage.
    """
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))

    def burn_until_first_point() -> int:
        enemy.hp = enemy.max_hp
        actions.apply_status(enemy, Attributes(regen=-12), 600)
        start = enemy.hp
        for tick in range(1, 60):
            step(world, Intent())
            if enemy.hp != start:
                return tick
        raise AssertionError("nothing paid out")

    first = burn_until_first_point()

    # Let it lapse the way the timer does, then light the same fire again.
    enemy.status_ticks = 1
    step(world, Intent())
    assert enemy.status is NEUTRAL

    assert burn_until_first_point() == first, "the second burn started part-paid"


def test_an_expiring_status_leaves_a_standing_regen_its_bank() -> None:
    """The counterpart guard. A body with regen of its own -- a `vital`
    champion -- is mid-way through banking a point it earned, and an unrelated
    slow wearing off is not a reason to take it away.

    Compared against a control that never carried a status at all, rather than
    asserted non-zero: the bank refills the tick after it is emptied, so
    "non-zero a moment later" is true whether the gate is there or not.
    """
    def bank_after(ticks: int, slow: bool) -> int:
        world = make_world()
        enemy = add_enemy(world, "grunt", Vec2(400, 200))
        enemy.hp = enemy.max_hp - 10
        enemy.bonus = Attributes(regen=40)
        if slow:
            actions.apply_status(enemy, SLOW, 2)
        run(world, ticks)
        assert enemy.status is NEUTRAL
        return enemy.regen_bank

    assert bank_after(2, slow=True) == bank_after(2, slow=False) != 0, (
        "an expiring slow emptied a healer's bank"
    )


def test_a_burn_drains_a_body_that_is_already_at_full_health() -> None:
    """The one place the burn deliberately does not mirror the healing branch.
    Being on fire at full health is the ordinary case, not the excluded one."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    assert enemy.hp == enemy.max_hp

    enemy.status, enemy.status_ticks = BURN, 600
    run(world, 10)

    assert enemy.hp < enemy.max_hp


def test_a_burn_cannot_take_a_body_below_zero() -> None:
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    enemy.hp = 1
    enemy.status, enemy.status_ticks = Attributes(regen=-900), 600

    run(world, 20)
    assert enemy.hp == 0


def test_a_burn_that_kills_announces_the_death() -> None:
    """Without it a burn kill is silent: no cue, no shake, and nothing for
    `Tally.kills` to count."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    enemy.hp = 1
    enemy.status, enemy.status_ticks = Attributes(regen=-900), 600

    step(world, Intent())
    assert any(e.kind is EventKind.DEATH and e.entity_id == enemy.id
               for e in world.events)


def test_a_body_the_burn_killed_is_not_killed_twice() -> None:
    """A burn is phase 1 and a swing is phase 7, so a body could die to the
    first and be struck by the second on the same tick -- two DEATH events for
    one death, and `Tally.kills` counting both. `resolve_swings` skips anything
    not alive, and this is the test that says so rather than the reading that
    hopes so."""
    world = make_world()
    hero = world.hero
    enemy = add_enemy(world, "grunt", Vec2(hero.pos.x + 12, hero.pos.y))
    enemy.hp = 1
    enemy.status, enemy.status_ticks = Attributes(regen=-900), 600

    hero.state = ActionState.ACTIVE
    hero.facing = 0.0
    step(world, Intent(aim=RIGHT, attack=True))

    deaths = [e for e in world.events if e.kind is EventKind.DEATH]
    assert len(deaths) == 1, "the same body died twice in one tick"


def test_a_burn_does_not_claim_the_kill_it_made() -> None:
    """`last_hit_by` is left alone, exactly as `apply_hazard` leaves it: nothing
    hit you, a status did."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    enemy.status, enemy.status_ticks = Attributes(regen=-900), 600

    run(world, 5)
    assert enemy.last_hit_by is None


def test_the_dead_do_not_burn() -> None:
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    enemy.hp = 0
    enemy.status, enemy.status_ticks = Attributes(regen=-900), 600

    run(world, 5)
    assert enemy.hp == 0


def test_healing_and_burning_on_one_body_net_out_through_one_bank() -> None:
    """`attrs.regen` already sums the layers, so one bank is correct rather than
    merely cheaper: +50 against a -50 burn is a body that is neither healing nor
    burning."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    enemy.hp = enemy.max_hp - 5
    enemy.bonus = Attributes(regen=50)
    enemy.status, enemy.status_ticks = Attributes(regen=-50), 600

    before = enemy.hp
    run(world, 60)
    assert enemy.hp == before


def test_a_burn_costs_what_the_tier_says_a_blow_costs() -> None:
    """Through `combat.incoming`, the same argument `apply_hazard` makes: the
    hero cannot tell mid-fight which of the two hurt it, and a tier that scaled
    one and not the other would be lying about how hard it is."""
    harsh = difficulty.Difficulty(id="harsh", name="Harsh", incoming=2000)

    def burned(tier) -> int:
        world = World(open_room(), BESTIARY, seed=7, difficulty=tier)
        hero = world.hero
        hero.status, hero.status_ticks = Attributes(regen=-100), 600
        before = hero.hp
        run(world, 6)
        return before - hero.hp

    assert burned(harsh) > burned(difficulty.NORMAL)


def test_a_burn_the_hero_suffers_is_not_filed_under_what_the_floor_did() -> None:
    """`EventKind.TRAP` is *what the room did*, and an enemy's fire is not that.
    `render/tally.py` splits them for the same reason `events.py` did."""
    from hack_and_slash.render.tally import Tally

    world = make_world()
    hero = world.hero
    hero.status, hero.status_ticks = Attributes(regen=-200), 600

    step(world, Intent())
    tally = Tally()
    tally.feed(world.drain_events())

    assert tally.taken > 0
    assert tally.burned == 0


def test_regeneration_is_the_arithmetic_it_always_was() -> None:
    """The guard moved from `rate <= 0` to `rate == 0`, and on every body in the
    shipped game the rate is exactly zero. This is the receipt."""
    world = make_world()
    enemy = add_enemy(world, "grunt", Vec2(400, 200))
    enemy.hp = 1
    enemy.bonus = Attributes(regen=100)

    run(world, 1)
    assert enemy.hp == 2

    enemy.hp = enemy.max_hp
    enemy.regen_bank = 90
    run(world, 1)
    assert enemy.regen_bank == 0, "banking at full health still stops"
