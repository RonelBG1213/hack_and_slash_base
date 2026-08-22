"""The four numbers the run-end summary shows that the sim never counted.

Every one of them is *derived* from the event stream rather than measured, so
this file is mostly about not miscounting. The two tests that matter most are
`test_a_crit_is_not_counted_twice` -- because the failure looks exactly like a
tuning problem rather than a bug -- and `test_a_fight_resolves_identically_with_a_tally_running`,
which is the house rule every reader of the drained list has to pass.
"""

from __future__ import annotations

import pytest

from hack_and_slash import config
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import intent as intents
from hack_and_slash.game.events import Event, EventKind
from hack_and_slash.game.sim import step
from hack_and_slash.render.tally import Tally, format_time

from .helpers import add_enemy, make_world

RIGHT = Vec2(1, 0)


def hit(amount: int, is_hero: bool = False) -> Event:
    return Event(kind=EventKind.HIT, pos=Vec2(0, 0), entity_id=1,
                 amount=amount, is_hero=is_hero)


def of(kind: EventKind, amount: int = 0, is_hero: bool = False) -> Event:
    return Event(kind=kind, pos=Vec2(0, 0), entity_id=1,
                 amount=amount, is_hero=is_hero)


# --- the counting rules ------------------------------------------------------
def test_a_crit_is_not_counted_twice() -> None:
    """The one miscount that would look like a balance problem, not a bug.

    `events.py` says a CRIT "accompanies the HIT it belongs to rather than
    replacing it", and `HIT.amount` is already multiplied. A `case CRIT` in
    `feed` would silently double every critical hit in a run -- and the number
    it produced would still be plausible, which is what makes it dangerous.
    """
    tally = Tally()
    tally.feed([hit(12), of(EventKind.CRIT, amount=12)])

    assert tally.dealt == 12


def test_damage_dealt_and_taken_are_told_apart_by_whose_body_it_was() -> None:
    tally = Tally()
    tally.feed([hit(12), hit(5, is_hero=True), hit(3)])

    assert tally.dealt == 15
    assert tally.taken == 5


def test_the_floor_is_not_an_enemy() -> None:
    """`TRAP` is a separate kind precisely so this sum can exclude it.

    From `events.py`: "anything counting what the *enemies* did to the hero
    would otherwise count the room's spikes among them". `burned` is where it
    goes instead, and `hurt` is the two put back together for a screen that
    wants one number.
    """
    tally = Tally()
    tally.feed([of(EventKind.TRAP, amount=9, is_hero=True), hit(4, is_hero=True)])

    assert tally.taken == 4, "trap damage was counted as something an enemy did"
    assert tally.burned == 9
    assert tally.hurt == 13


def test_a_trap_never_counts_as_damage_the_hero_dealt() -> None:
    tally = Tally()
    tally.feed([of(EventKind.TRAP, amount=9, is_hero=True)])

    assert tally.dealt == 0


def test_only_the_deaths_that_were_not_the_hero_are_kills() -> None:
    tally = Tally()
    tally.feed([of(EventKind.DEATH), of(EventKind.DEATH, is_hero=True),
                of(EventKind.DEATH)])

    assert tally.kills == 2


def test_a_blocked_hit_costs_nothing() -> None:
    """i-frames and evasion both arrive as BLOCKED and neither is damage."""
    tally = Tally()
    tally.feed([of(EventKind.BLOCKED, amount=7, is_hero=True)])

    assert (tally.dealt, tally.taken, tally.burned) == (0, 0, 0)


@pytest.mark.parametrize("kind", list(EventKind))
def test_every_event_kind_is_survivable(kind: EventKind) -> None:
    """Fed one of each, in both flavours, and nothing raises.

    Parametrised over the enum rather than over a list somebody keeps in step,
    so a thirteenth kind arrives here as a failing test rather than as a
    `KeyError` on the death screen of somebody's fiftieth stage.
    """
    for is_hero in (True, False):
        Tally().feed([of(kind, amount=3, is_hero=is_hero)])


# --- the clock ---------------------------------------------------------------
def test_the_clock_counts_the_ticks_it_is_given() -> None:
    tally = Tally()
    for _ in range(90):
        tally.advance()

    assert tally.ticks == 90
    assert tally.seconds == 90 / config.TICKS_PER_SEC


def test_feeding_events_does_not_move_the_clock() -> None:
    """`advance` is separate from `feed` so the clock cannot double the day
    somebody feeds twice -- and so a tick that emitted nothing still counts."""
    tally = Tally()
    tally.feed([hit(4), hit(4)])

    assert tally.ticks == 0


@pytest.mark.parametrize(
    "ticks, shown",
    [
        (0, "0:00"),
        (config.TICKS_PER_SEC, "0:01"),
        (59 * config.TICKS_PER_SEC, "0:59"),
        (60 * config.TICKS_PER_SEC, "1:00"),
        # Deliberately no hour rollover: a fifty-stage run is tens of minutes,
        # and 1:04:22 is a format nobody needs to learn to read 64:22.
        (64 * 60 * config.TICKS_PER_SEC + 22 * config.TICKS_PER_SEC, "64:22"),
    ],
)
def test_the_clock_reads_as_minutes_and_seconds(ticks: int, shown: str) -> None:
    assert format_time(ticks) == shown


# --- the guarantee -----------------------------------------------------------
def fight(seed: int, tally: Tally | None):
    """The same scripted fight, optionally draining events into a tally."""
    world = make_world(seed=seed)
    add_enemy(world, "grunt", world.hero.pos + Vec2(30, 0))
    add_enemy(world, "bowman", world.hero.pos + Vec2(-90, 40))

    press = intents.Intent(move=RIGHT, aim=RIGHT, attack=True)
    for tick in range(300):
        command = press if tick % 40 < 30 else intents.dodge_toward(RIGHT)
        step(world, command)
        if tally is not None:
            tally.feed(world.drain_events())
            tally.advance()

    return [(e.id, e.pos, e.hp, e.state) for e in world.entities], world.outcome


def test_a_fight_resolves_identically_with_a_tally_running() -> None:
    """The house rule for every reader of the drained list.

    `Effects` has to keep its own seeded `Random` so that drawing cannot consume
    a number the sim was about to draw. A tally holds no `Random` at all, so it
    has nothing to guard -- but "it obviously cannot" is what somebody would say
    while adding the drain that swallowed a tick's events.
    """
    plain = fight(seed=31337, tally=None)
    counted = fight(seed=31337, tally=Tally())

    assert plain == counted


def test_the_tally_agrees_with_the_bodies() -> None:
    """Not merely self-consistent: checked against health that actually moved.

    A plain arena with no fountain and no regen, so the identity holds --
    everything the hero lost, it lost to a blow or to the floor. Stated here
    because the caveat is about the test, not about the tally: put a fountain in
    and the two stop matching for a good reason.
    """
    world = make_world(seed=99)
    add_enemy(world, "grunt", world.hero.pos + Vec2(26, 0))
    add_enemy(world, "grunt", world.hero.pos + Vec2(-26, 0))

    tally = Tally()
    full = world.hero.max_hp
    for _ in range(400):
        step(world, intents.Intent(aim=RIGHT, attack=True))
        tally.feed(world.drain_events())
        tally.advance()
        if world.hero is None or not world.hero.is_alive:
            break

    if world.hero is not None and world.hero.is_alive:
        assert tally.hurt == full - world.hero.hp, "the tally lost track of the hero"
    assert tally.dealt > 0, "the fight did no damage at all -- check the fixture"


def test_a_fresh_tally_is_empty_and_whole() -> None:
    """`partial` is the flag that stops a resumed run under-reporting itself."""
    tally = Tally()

    assert (tally.dealt, tally.taken, tally.burned, tally.kills, tally.ticks) == (
        0, 0, 0, 0, 0,
    )
    assert tally.partial is False
