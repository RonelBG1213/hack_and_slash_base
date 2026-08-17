"""The feel pass, and the guarantee that it is only a feel pass.

The headline test is `test_a_fight_resolves_identically_with_effects_running`.
Screenshake, damage numbers and hitstop exist to make hits land harder, and the
moment any of them can change who wins, tuning the feel means re-checking the
balance. This file is what makes "cosmetic" a fact rather than an intention.
"""

from __future__ import annotations

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import intent as intents
from hack_and_slash.game.events import Event, EventKind
from hack_and_slash.game.sim import step
from hack_and_slash.render.effects import NUMBER_LIFETIME, Effects

from .helpers import add_enemy, make_world

RIGHT = Vec2(1, 0)


def fight(seed: int, effects: Effects | None):
    """Run the same scripted fight, optionally draining events into Effects."""
    world = make_world(seed=seed)
    add_enemy(world, "grunt", world.hero.pos + Vec2(30, 0))
    add_enemy(world, "bowman", world.hero.pos + Vec2(-90, 40))

    press = intents.Intent(move=RIGHT, aim=RIGHT, attack=True)
    for tick in range(300):
        command = press if tick % 40 < 30 else intents.dodge_toward(RIGHT)
        step(world, command)
        if effects is not None:
            effects.feed(world.drain_events(), world.hitstop)
            effects.tick()

    return [(e.id, e.pos, e.hp, e.state) for e in world.entities], world.outcome


# --- the guarantee -----------------------------------------------------------
def test_a_fight_resolves_identically_with_effects_running() -> None:
    """Cosmetics must not be able to change a fight.

    If this fails, something in the presentation layer is reading or writing
    simulation state -- most likely drawing code that consumed a number from
    the world's Random, which shifts every roll after it.
    """
    plain = fight(seed=31337, effects=None)
    decorated = fight(seed=31337, effects=Effects())
    assert plain == decorated


def test_a_fight_resolves_identically_whichever_way_the_toggles_are_set() -> None:
    """The same guarantee, extended to the two rows the options screen exposes.

    Putting a switch on the feel pass is only safe because of the test above --
    but "only the presentation layer changed" is exactly what somebody would say
    while adding a toggle that skipped a `drain_events` and left a tick's events
    queued into the next one. All four combinations, against the undecorated
    fight, so a toggle cannot be the thing that makes the difference.
    """
    plain = fight(seed=31337, effects=None)

    for screenshake in (True, False):
        for numbers in (True, False):
            decorated = fight(
                seed=31337,
                effects=Effects(screenshake=screenshake, damage_numbers=numbers),
            )
            assert plain == decorated, (
                f"screenshake={screenshake}, damage_numbers={numbers} changed the fight"
            )


def test_the_toggles_actually_turn_the_thing_off() -> None:
    """The other half: a switch that changes nothing at all would pass every
    test above and be a lie on the screen."""
    quiet = Effects(screenshake=False, damage_numbers=False)
    quiet.feed([Event(EventKind.HIT, Vec2(0, 0), 1, amount=9, is_hero=True)])

    assert quiet.numbers == [], "a damage number was drawn with numbers switched off"
    assert quiet.shake_offset().is_zero(), "the viewport moved with shake switched off"

    # And the magnitude is still recorded, so the two halves of the class do not
    # disagree about what happened -- see the note on `shake_offset`.
    assert quiet.shake > 0.0


def test_switching_damage_numbers_off_keeps_the_ones_that_answer_a_question() -> None:
    """A coin picked up and a hit rolled out of are outcomes with no other tell
    in the game. The row says "damage numbers" and it means them."""
    quiet = Effects(damage_numbers=False)
    quiet.feed(
        [
            Event(EventKind.HIT, Vec2(0, 0), 1, amount=9),
            Event(EventKind.PICKUP, Vec2(0, 0), 1, amount=12, rarity="rare"),
            Event(EventKind.BLOCKED, Vec2(0, 0), 1, is_hero=True),
        ]
    )
    assert [n.text for n in quiet.numbers] == ["+12", "dodge"]


def test_effects_draw_from_their_own_random_not_the_world_s() -> None:
    """The specific way the test above would break.

    Shake direction and number drift need randomness. Taking it from the world's
    Random would make every damage roll depend on how many hits happened to be
    on screen.
    """
    world = make_world(seed=5)
    effects = Effects()
    before = world.rng.getstate()

    for _ in range(30):
        effects.feed(
            [Event(EventKind.HIT, Vec2(10, 10), 1, amount=7)], hitstop=4
        )
        effects.tick()
        effects.shake_offset()

    assert world.rng.getstate() == before, "the presentation layer consumed a sim roll"


# --- damage numbers ----------------------------------------------------------
def test_a_hit_produces_a_number_saying_what_it_was_for() -> None:
    effects = Effects()
    effects.feed([Event(EventKind.HIT, Vec2(40, 40), 2, amount=9)])
    assert [n.text for n in effects.numbers] == ["9"]


def test_numbers_expire_rather_than_piling_up_forever() -> None:
    effects = Effects()
    effects.feed([Event(EventKind.HIT, Vec2(40, 40), 2, amount=9)])
    for _ in range(NUMBER_LIFETIME + 1):
        effects.tick()
    assert effects.numbers == []


def test_numbers_rise_and_fade_over_their_life() -> None:
    effects = Effects()
    effects.feed([Event(EventKind.HIT, Vec2(40, 40), 2, amount=9)])
    number = effects.numbers[0]

    start_offset = number.offset().y
    for _ in range(NUMBER_LIFETIME // 2):
        effects.tick()
    assert number.offset().y < start_offset, "did not rise"
    assert number.alpha == 255, "started fading too early to read"

    for _ in range(NUMBER_LIFETIME // 2 - 1):
        effects.tick()
    assert number.alpha < 255, "never faded"


def test_damage_to_the_hero_is_coloured_differently() -> None:
    # The colour answers "was that me?" without having to read the number.
    effects = Effects()
    effects.feed(
        [
            Event(EventKind.HIT, Vec2(0, 0), 1, amount=5, is_hero=True),
            Event(EventKind.HIT, Vec2(0, 0), 2, amount=5, is_hero=False),
        ]
    )
    hero_number, enemy_number = effects.numbers
    assert hero_number.color != enemy_number.color


def test_a_dodged_hit_shows_something_rather_than_nothing() -> None:
    # A dodge that looks identical to a miss teaches the player nothing.
    effects = Effects()
    effects.feed([Event(EventKind.BLOCKED, Vec2(0, 0), 1, is_hero=True)])
    assert effects.numbers and effects.numbers[0].text == "dodge"


# --- shake -------------------------------------------------------------------
def test_being_hit_shakes_harder_than_hitting_something() -> None:
    hitting = Effects()
    hitting.feed([Event(EventKind.HIT, Vec2(0, 0), 2, amount=5, is_hero=False)])

    hurt = Effects()
    hurt.feed([Event(EventKind.HIT, Vec2(0, 0), 1, amount=5, is_hero=True)])

    assert hurt.shake > hitting.shake


def test_shake_decays_to_nothing() -> None:
    effects = Effects()
    effects.feed([Event(EventKind.HIT, Vec2(0, 0), 1, amount=5, is_hero=True)])
    for _ in range(60):
        effects.tick()
    assert effects.shake == 0.0
    assert effects.shake_offset().is_zero()


def test_shake_offset_stays_within_its_magnitude() -> None:
    # An unbounded shake makes the arena unreadable in a crowd.
    effects = Effects()
    effects.feed([Event(EventKind.HIT, Vec2(0, 0), 1, amount=5, is_hero=True)])
    for _ in range(20):
        assert effects.shake_offset().length() <= effects.shake + 1e-9
        effects.tick()


def test_a_quiet_tick_shakes_not_at_all() -> None:
    effects = Effects()
    effects.feed([])
    assert effects.shake_offset().is_zero()
