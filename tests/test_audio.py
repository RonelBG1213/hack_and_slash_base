"""The audio pass, and the guarantee that it is only an audio pass.

The headline test is `test_a_fight_resolves_identically_with_cues_running`, and
it is `test_effects.py`'s headline test one layer along. Sound exists to tell the
player a hit connected, and the moment it can change who wins, tuning the audio
means re-checking the balance. This file is what makes "cosmetic" a fact rather
than an intention.

The bank tests are a different kind of claim: not that sound changes nothing,
but that the *absence* of sound changes nothing either. A machine with no audio
device has to reach the same arena as one with speakers.
"""

from __future__ import annotations

import pygame
import pytest

from hack_and_slash import config
from hack_and_slash.audio import bank as sound_bank
from hack_and_slash.audio.cues import DEFAULT_VOLUME, MAX_VOLUME, Cues, cue_for
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import intent as intents
from hack_and_slash.game.events import Event, EventKind
from hack_and_slash.game.sim import step

from .helpers import add_enemy, make_world

RIGHT = Vec2(1, 0)


def fight(seed: int, cues: Cues | None):
    """Run the same scripted fight, optionally draining events into Cues.

    Deliberately the same fight `test_effects.py` runs, down to the seed and the
    two enemies -- a grunt to be hit and a bowman to do the shooting -- so the
    two guarantees are being made about one situation rather than two.
    """
    world = make_world(seed=seed)
    add_enemy(world, "grunt", world.hero.pos + Vec2(30, 0))
    add_enemy(world, "bowman", world.hero.pos + Vec2(-90, 40))

    press = intents.Intent(move=RIGHT, aim=RIGHT, attack=True)
    for tick in range(300):
        command = press if tick % 40 < 30 else intents.dodge_toward(RIGHT)
        step(world, command)
        if cues is not None:
            cues.feed(world.drain_events())
            cues.drain()

    return [(e.id, e.pos, e.hp, e.state) for e in world.entities], world.outcome


# --- the guarantee -----------------------------------------------------------
def test_a_fight_resolves_identically_with_cues_running() -> None:
    """Sound must not be able to change a fight.

    If this fails, something in the audio layer is reading or writing simulation
    state -- most likely a cue that consumed a number from the world's Random,
    which shifts every roll after it. `audio/cues.py` holds no generator at all
    today, which is the cheapest possible way to keep this true.
    """
    plain = fight(seed=31337, cues=None)
    heard = fight(seed=31337, cues=Cues())
    assert plain == heard


def test_a_fight_resolves_identically_at_every_volume() -> None:
    """The same guarantee, extended to the row the options screen exposes.

    Putting a volume on the audio pass is only safe because of the test above --
    but "only the presentation layer changed" is exactly what somebody would say
    while adding a setting that skipped a `drain_events` and left a tick's events
    queued into the next one. Both ends and the middle, against the silent fight.
    """
    plain = fight(seed=31337, cues=None)

    for volume in (0, 1, DEFAULT_VOLUME, MAX_VOLUME):
        heard = fight(seed=31337, cues=Cues(volume=volume))
        assert plain == heard, f"volume={volume} changed the fight"


def test_volume_zero_actually_plays_nothing() -> None:
    """The other half: a switch that changed nothing at all would pass every
    test above and be a lie on the screen."""
    quiet = Cues(volume=0)
    quiet.feed(
        [
            Event(EventKind.HIT, Vec2(0, 0), 1, amount=9),
            Event(EventKind.DEATH, Vec2(0, 0), 1),
        ]
    )

    assert quiet.drain() == []
    assert quiet.level == 0.0


def test_a_full_volume_fight_actually_asks_for_something() -> None:
    """And the other other half -- the test above passes trivially if `feed` is
    broken, so something has to prove the pipe carries anything at all."""
    loud = Cues(volume=MAX_VOLUME)
    loud.feed(
        [
            Event(EventKind.HIT, Vec2(0, 0), 1, amount=9),
            Event(EventKind.DEATH, Vec2(0, 0), 1),
        ]
    )

    assert loud.drain() == ["hit", "death"]
    assert loud.level == 1.0


# --- the per-frame collapse --------------------------------------------------
def test_a_frame_that_paid_out_many_ticks_plays_each_cue_once() -> None:
    """The mechanic this module exists for.

    A stalled frame pays out up to fifteen ticks (`config.MAX_FRAME_TIME`), and
    `feed` is called once per tick while `drain` is called once per frame.
    Fifteen swings in one frame is not a swing, it is a buzz.
    """
    cues = Cues()
    for _ in range(15):
        cues.feed([Event(EventKind.SWING, Vec2(0, 0), 1)])

    assert cues.drain() == ["swing"]


def test_a_swing_that_catches_a_crowd_is_one_sound() -> None:
    """The same collapse from the other direction: one tick, six victims."""
    cues = Cues()
    cues.feed(
        [Event(EventKind.HIT, Vec2(0, 0), i, amount=4) for i in range(6)]
    )

    assert cues.drain() == ["hit"]


def test_draining_leaves_nothing_behind_for_the_next_frame() -> None:
    cues = Cues()
    cues.feed([Event(EventKind.HIT, Vec2(0, 0), 1, amount=4)])
    assert cues.drain() == ["hit"]
    assert cues.drain() == []


def test_cues_come_out_in_the_order_the_sim_resolved_them() -> None:
    """Playing a death before the hit that caused it is audible, which is why
    `pending` is a list and not a set."""
    cues = Cues()
    cues.feed(
        [
            Event(EventKind.SWING, Vec2(0, 0), 1),
            Event(EventKind.HIT, Vec2(0, 0), 2, amount=9),
            Event(EventKind.DEATH, Vec2(0, 0), 2),
        ]
    )

    assert cues.drain() == ["swing", "hit", "death"]


def test_clearing_drops_what_a_departed_stage_had_queued() -> None:
    cues = Cues()
    cues.feed([Event(EventKind.HIT, Vec2(0, 0), 1, amount=4)])
    cues.clear()
    assert cues.drain() == []


# --- the cue table -----------------------------------------------------------
def test_taking_a_hit_sounds_different_from_landing_one() -> None:
    """The single distinction most worth having. "Was that me?" has to be
    answerable without looking at the health bar."""
    landed = cue_for(Event(EventKind.HIT, Vec2(0, 0), 1, amount=9, is_hero=False))
    taken = cue_for(Event(EventKind.HIT, Vec2(0, 0), 1, amount=9, is_hero=True))

    assert landed == "hit"
    assert taken == "hurt"
    assert landed != taken


def test_the_hero_dying_sounds_different_from_anything_else_dying() -> None:
    assert cue_for(Event(EventKind.DEATH, Vec2(0, 0), 1)) == "death"
    assert cue_for(Event(EventKind.DEATH, Vec2(0, 0), 1, is_hero=True)) == "hero_death"


def test_a_relic_sounds_different_from_a_coin() -> None:
    """There is one relic sprite for all five rarities, so the sound is carrying
    information the picture is not."""
    coin = Event(EventKind.PICKUP, Vec2(0, 0), 1, amount=5)
    relic = Event(EventKind.PICKUP, Vec2(0, 0), 1, amount=5, rarity="epic")

    assert cue_for(coin) == "coin"
    assert cue_for(relic) == "relic"


def test_a_spent_projectile_asks_for_nothing() -> None:
    """Deliberately silent: the payload cannot tell an arrow that hit a body from
    one that aged out over empty floor, so any cue here clicks for no reason."""
    assert cue_for(Event(EventKind.PROJECTILE_SPENT, Vec2(0, 0), 1)) is None


def test_every_cue_the_table_can_name_exists_in_the_sound_names() -> None:
    """The one that catches adding a cue and forgetting the file.

    A name `cue_for` can return that `config.SOUND_NAMES` does not carry is a
    cue nothing generates and nothing loads -- silent in the game, with no error
    anywhere to say so.
    """
    for kind in EventKind:
        for is_hero in (False, True):
            for rarity in ("", "epic"):
                cue = cue_for(
                    Event(kind, Vec2(0, 0), 1, is_hero=is_hero, rarity=rarity)
                )
                assert cue is None or cue in config.SOUND_NAMES, (
                    f"{kind} asks for '{cue}', which is not in config.SOUND_NAMES"
                )


def test_every_event_kind_but_one_makes_a_noise() -> None:
    """The reverse: a kind that quietly stopped mapping to anything would be a
    cue that went missing without a test noticing."""
    silent = [
        kind
        for kind in EventKind
        if cue_for(Event(kind, Vec2(0, 0), 1)) is None
    ]
    assert silent == [EventKind.PROJECTILE_SPENT]


def test_the_generator_writes_everything_the_names_ask_for() -> None:
    """Checks tools/gen_sfx.py against config.SOUND_NAMES without running it.

    The same shape as `test_atlas.py::test_the_generator_paints_everything_the_
    order_asks_for`, and it catches the same mistake: a name added to config.py
    with no voice behind it.
    """
    import sys
    from pathlib import Path

    tools = Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(tools))
    try:
        import gen_sfx
    finally:
        sys.path.remove(str(tools))

    for name in config.SOUND_NAMES:
        assert name in gen_sfx.VOICES, f"nothing generates '{name}'"


# --- the bank ----------------------------------------------------------------
def test_a_missing_sound_directory_is_quiet_rather_than_fatal(tmp_path) -> None:
    """The asymmetry with `atlas.load`, which refuses loudly and is right to.

    A game that cannot draw cannot run. A game that cannot make a noise runs
    fine, and a player with no sound card still gets to play.
    """
    quiet = sound_bank.load(tmp_path / "not_here")

    assert not quiet.ok
    # And it is safe to drive, which is the half that actually matters -- the
    # caller does not check.
    quiet.play(["hit", "death"])


def test_a_bank_with_no_mixer_is_quiet_rather_than_fatal(monkeypatch) -> None:
    """`SDL_AUDIODRIVER=dummy` under the suite, a tool that never opened a
    mixer, or an SDL that declined to find a device."""
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)

    quiet = sound_bank.load()

    assert not quiet.ok
    quiet.play(["hit"])


def test_an_unknown_cue_name_is_ignored_rather_than_raising() -> None:
    """A bank loaded against a half-generated directory is the degradation case
    this module exists for; crashing a run over one missing WAV is the only
    outcome worse than not hearing it."""
    sound_bank.SILENT.play(["basilisk"])


def test_the_memo_hands_back_one_bank(monkeypatch) -> None:
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    sound_bank.reset()
    try:
        assert sound_bank.get() is sound_bank.get()
    finally:
        sound_bank.reset()


@pytest.mark.skipif(
    not config.SOUNDS_DIR.is_dir(),
    reason="no cues -- run `python tools/gen_sfx.py`",
)
def test_every_generated_cue_loads_when_a_mixer_exists(tmp_path) -> None:
    """The end-to-end read, under the dummy audio driver conftest already sets.

    Skipped rather than failed when `assets/sfx/` has not been generated, which
    is how `test_atlas.py` treats a missing atlas.
    """
    pygame.init()
    try:
        pygame.mixer.init(frequency=config.SOUND_RATE, size=-16, channels=1)
    except pygame.error:
        pytest.skip("SDL would not open a mixer, even a dummy one")

    try:
        loaded = sound_bank.load()
        assert loaded.ok
        assert set(loaded.sounds) == set(config.SOUND_NAMES)
        # Under SDL_AUDIODRIVER=dummy this reaches the mixer and produces no
        # audible sound, which is exactly what is wanted from a test.
        loaded.play(list(config.SOUND_NAMES), level=0.5)
    finally:
        pygame.mixer.quit()
