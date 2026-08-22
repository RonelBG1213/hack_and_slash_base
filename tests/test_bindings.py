"""Which key asks for what, and the rules about changing it.

Two halves, and they are tested apart because they are pure apart. `bindings.py`
knows action names and key names and no pygame at all; `scenes/keymap.py` is the
only place those names become the integers an `event.key` carries.

The first test in this file is the important one and the rest are detail: it
asserts that a player who never opens the Controls screen is playing the game
that was measured. Everything below it is about somebody who did.
"""

from __future__ import annotations

import pygame
import pytest

from hack_and_slash.bindings import DEFAULTS, LABELS, Action, resolve
from hack_and_slash.scenes import keymap
from hack_and_slash.settings import Settings

from .test_render import display  # noqa: F401


# --- what shipped ------------------------------------------------------------
def test_the_defaults_are_the_keys_the_game_has_always_had(display) -> None:
    """The whole claim that rebinding moved nothing.

    Written against the literal `pygame.K_*` values `scenes/play.py` carried as
    module constants before this layer existed -- `MOVE_KEYS`, `DODGE_KEYS`,
    `SKILL_KEYS`, `SHEET_KEYS` and the inline `K_j` and `K_r`. Asserting against
    `DEFAULTS` instead would be asserting that a table equals itself.
    """
    codes = keymap.keycodes(Settings())

    assert codes[Action.MOVE_UP] == (pygame.K_w, pygame.K_UP)
    assert codes[Action.MOVE_DOWN] == (pygame.K_s, pygame.K_DOWN)
    assert codes[Action.MOVE_LEFT] == (pygame.K_a, pygame.K_LEFT)
    assert codes[Action.MOVE_RIGHT] == (pygame.K_d, pygame.K_RIGHT)
    assert codes[Action.ATTACK] == (pygame.K_j,)
    assert codes[Action.NEUTRAL] == (pygame.K_q,)
    assert codes[Action.HEAVY] == (pygame.K_e,)
    assert codes[Action.ULTIMATE] == (pygame.K_f,)
    assert codes[Action.DODGE] == (pygame.K_SPACE, pygame.K_LSHIFT, pygame.K_RSHIFT)
    assert codes[Action.SHEET] == (pygame.K_i, pygame.K_TAB)
    assert codes[Action.RESTART] == (pygame.K_r,)


def test_every_action_ships_bound_to_something() -> None:
    """An action with no key is an attack the player cannot reach."""
    for action in Action:
        assert DEFAULTS[action], f"{action} ships bound to nothing"
        assert action in LABELS, f"{action} has no name for the screen"


def test_a_fresh_settings_object_expresses_no_opinion() -> None:
    """Empty, not filled in with the defaults.

    The same sentinel argument as `AUTO_SCALE`: a player who never touched a row
    follows the shipped key if it ever moves. Writing the defaults into their
    file on first launch is how a preference quietly outvotes the program.
    """
    assert Settings().bindings == {}
    assert resolve(Settings().bindings) == DEFAULTS


# --- what a settings file may say --------------------------------------------
def test_an_action_this_build_does_not_know_is_ignored() -> None:
    """A file from a later build still loads, minus the part that is from it."""
    assert resolve({"grapple": ["g"], "dodge": ["c"]})[Action.DODGE] == ("c",)


def test_an_action_bound_to_nothing_falls_back_rather_than_stranding() -> None:
    assert resolve({"heavy": []})[Action.HEAVY] == DEFAULTS[Action.HEAVY]


def test_a_key_this_platform_does_not_have_falls_back(display) -> None:
    """Names are SDL's, and SDL's answer can differ from machine to machine.

    Dropped rather than raised on, because the alternative is a settings file
    from another keyboard layout stopping the scene from being built at all.
    """
    codes = keymap.keycodes(Settings(bindings={"heavy": ["no such key"]}))
    assert codes[Action.HEAVY] == (pygame.K_e,)


def test_a_name_that_does_not_survive_the_round_trip_is_refused(display) -> None:
    assert keymap.name_of(pygame.K_LSHIFT) == "left shift"
    assert keymap.name_of(pygame.K_q) == "q"
    assert keymap.name_of(-1) is None


# --- the rules ---------------------------------------------------------------
@pytest.mark.parametrize("name", ["escape", "return", "enter", "backspace", "1", "8"])
def test_a_reserved_key_is_refused(display, name) -> None:
    """The keys a player needs in order to leave the screen they are standing on."""
    settings = Settings()
    complaint = keymap.assign(settings, Action.DODGE, name)

    assert complaint is not None
    assert settings.bindings == {}, "a refused binding must change nothing"


def test_space_is_bindable_even_though_the_menus_use_it(display) -> None:
    """The interesting omission from `RESERVED`, asserted so it stays deliberate.

    Space confirms on every menu *and* is the shipped dodge key. Reserving it
    would mean the screen refusing the game's own default, which is the reductio
    that decided the list.
    """
    assert "space" not in keymap.RESERVED
    assert keymap.assign(Settings(), Action.HEAVY, "space") is None


def test_taking_a_key_removes_it_from_whatever_held_it(display) -> None:
    """Two actions on one key is not a conflict the arena could resolve."""
    settings = Settings()

    assert keymap.assign(settings, Action.ATTACK, "up") is None

    codes = keymap.keycodes(settings)
    assert codes[Action.ATTACK] == (pygame.K_UP,)
    assert codes[Action.MOVE_UP] == (pygame.K_w,), "Move up kept its other key"


def test_a_key_is_not_taken_if_it_would_strand_the_action_that_had_it(
    display,
) -> None:
    """The Class buff has one key, so the swing may not have it."""
    settings = Settings()
    complaint = keymap.assign(settings, Action.ATTACK, "q")

    assert complaint is not None
    assert "Class buff" in complaint, "the refusal names what it would have stranded"
    assert settings.bindings == {}
    assert keymap.keycodes(settings)[Action.NEUTRAL] == (pygame.K_q,)


def test_rebinding_replaces_every_key_the_action_had(display) -> None:
    """One press, one key -- so a row shows what it is bound to and nothing else."""
    settings = Settings()
    keymap.assign(settings, Action.DODGE, "c")

    assert keymap.keycodes(settings)[Action.DODGE] == (pygame.K_c,)


def test_resetting_forgets_rather_than_writing_the_defaults_down(display) -> None:
    """Back to having no opinion, not back to today's answer recorded forever."""
    settings = Settings()
    keymap.assign(settings, Action.DODGE, "c")
    keymap.reset(settings)

    assert settings.bindings == {}
    assert keymap.keycodes(settings)[Action.DODGE] == (
        pygame.K_SPACE,
        pygame.K_LSHIFT,
        pygame.K_RSHIFT,
    )


def test_only_what_was_changed_is_written_down(display) -> None:
    """The sparse-file rule, which is what makes a shipped key still movable."""
    settings = Settings()
    keymap.assign(settings, Action.DODGE, "c")

    assert set(settings.bindings) == {"dodge"}


# --- what the game prints ----------------------------------------------------
def test_the_printed_key_is_the_key_that_is_listened_for(display) -> None:
    """One source for both, so a HUD pip cannot be confidently wrong."""
    settings = Settings()
    assert keymap.label(Action.NEUTRAL, settings) == "Q"
    assert keymap.label(Action.SHEET, settings) == "I"
    assert keymap.label(Action.RESTART, settings) == "R"
    assert keymap.label(Action.DODGE, settings) == "space"

    keymap.assign(settings, Action.NEUTRAL, "c")
    assert keymap.label(Action.NEUTRAL, settings) == "C"
