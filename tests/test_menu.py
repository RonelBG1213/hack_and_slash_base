"""The title screen and the four screens behind it.

The menu is six rows and almost no logic, so most of what can go wrong here is
wiring: a row that returns the wrong scene, a row that returns nothing when it
should, a label that grew into the column beside it. Those are the three things
this file checks, plus the one piece of real behaviour on the screen -- Load Game
being dead until there is something to load.

Layout is measured with the screens' own fonts rather than eyeballed, the way
`test_render.py` measures the shop and the job panel. A label that overruns is a
rendering bug that reads as a wording one, and it is invisible in a headless
suite unless something goes looking.
"""

from __future__ import annotations

import pygame
import pytest

from hack_and_slash import config
from hack_and_slash.core import campaign_io
from hack_and_slash.game import jobs, profile, save
from hack_and_slash.game.run import Run
from hack_and_slash.scenes.achievements import AchievementsScene
from hack_and_slash.scenes.menu import ITEMS, MenuScene
from hack_and_slash.scenes.options import ROWS, OptionsScene
from hack_and_slash.scenes.play import PlayScene
from hack_and_slash.scenes.select import CharacterSelectScene
from hack_and_slash.scenes.unlockables import UnlockablesScene
from hack_and_slash.settings import SCALES, Settings

from .helpers import BESTIARY
from .test_render import atlas, campaign, display, is_blank  # noqa: F401


def menu(atlas, **kwargs) -> MenuScene:
    return MenuScene(campaign(), BESTIARY, atlas, **kwargs)


def row(action: str) -> int:
    """The index of a row, by id. Written this way so re-ordering `ITEMS` is a
    change to one tuple rather than to a dozen magic numbers here."""
    return [item for item, _ in ITEMS].index(action)


def press(scene, key: int):
    return scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def a_saved_run(stage: int = 7, hero: str = "rogue") -> Run:
    run = Run.start(campaign(), BESTIARY, seed=5, at_stage=stage - 1, hero_type_id=hero)
    run.gold = 1234
    save.write(run)
    return run


# --- the six rows ------------------------------------------------------------
def test_the_menu_offers_the_six_rows_in_order(atlas) -> None:
    """The whole of what was asked for, in one assertion.

    Pinned as a list rather than left implicit because the order is the design:
    the two rows that start a game are first and the row that closes it is last,
    and a refactor that quietly sorted them alphabetically would put Quit Game
    where Load Game was.
    """
    assert [label for _, label in ITEMS] == [
        "New Game",
        "Load Game",
        "Settings",
        "Achievements",
        "Unlockables",
        "Quit Game",
    ]


def test_the_menu_draws_something(atlas) -> None:
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene = menu(atlas)

    # Every row in turn: the detail line changes with the cursor, and the Load
    # Game row draws through a different branch from the other five.
    for index in range(len(ITEMS)):
        scene.index = index
        scene.draw(surface)
        assert not is_blank(surface)


def test_the_cursor_wraps_at_both_ends(atlas) -> None:
    scene = menu(atlas)
    last = len(ITEMS) - 1

    scene._move(-1)
    assert scene.index == last, "moving up off the top should wrap to the bottom"
    scene._move(1)
    assert scene.index == 0


def test_new_game_goes_to_the_character_select(atlas) -> None:
    scene = menu(atlas, seed=9)
    scene.index = row("new")

    chosen = press(scene, pygame.K_RETURN)
    assert isinstance(chosen, CharacterSelectScene)
    assert chosen.seed == 9, "the seed must survive the menu"
    assert chosen.start_stage == 0


def test_quit_asks_the_app_to_close(atlas) -> None:
    """Posted rather than returned. `App.run` is the only thing that owns the
    loop, and a scene that could stop it directly would be a second answer to
    the question of when the game ends."""
    pygame.event.clear()
    scene = menu(atlas)
    scene.index = row("quit")

    assert press(scene, pygame.K_RETURN) is None
    assert any(e.type == pygame.QUIT for e in pygame.event.get())


def test_escape_still_quits_from_the_title_screen(atlas) -> None:
    # It always has, and there is nothing behind the title screen to go back to.
    pygame.event.clear()
    press(menu(atlas), pygame.K_ESCAPE)
    assert any(e.type == pygame.QUIT for e in pygame.event.get())


@pytest.mark.parametrize(
    "action, scene_type",
    [
        ("settings", OptionsScene),
        ("achievements", AchievementsScene),
        ("unlockables", UnlockablesScene),
    ],
)
def test_each_row_opens_its_own_screen(atlas, action, scene_type) -> None:
    scene = menu(atlas)
    scene.index = row(action)
    assert isinstance(press(scene, pygame.K_RETURN), scene_type)


def test_every_screen_comes_back_to_the_menu(atlas) -> None:
    """Escape is "back" on all three, and the way back is the same object shape
    it left from -- a screen that returned None would strand the player."""
    scene = menu(atlas)
    for action in ("settings", "achievements", "unlockables"):
        scene.index = row(action)
        opened = press(scene, pygame.K_RETURN)
        assert isinstance(press(opened, pygame.K_ESCAPE), MenuScene)


def test_leaving_a_screen_puts_the_cursor_back_where_it_was(atlas) -> None:
    # Coming back to the top of the list every time makes a settings change feel
    # like it lost your place, because it did.
    scene = menu(atlas)
    scene.index = row("unlockables")
    returned = press(press(scene, pygame.K_RETURN), pygame.K_ESCAPE)
    assert returned.index == row("unlockables")


# --- Load Game ---------------------------------------------------------------
def test_load_game_is_dead_until_there_is_a_save(atlas) -> None:
    """Nothing happens, and nothing is the right answer.

    The row is greyed before it is pressed and greying it is what said so, so
    there is nothing left to explain that the screen was not already saying.
    """
    scene = menu(atlas)
    assert not scene.can_load

    scene.index = row("load")
    assert press(scene, pygame.K_RETURN) is None


def test_load_game_returns_the_saved_run_to_the_stage_it_was_left_on(atlas) -> None:
    a_saved_run(stage=7, hero="rogue")
    scene = menu(atlas)
    assert scene.can_load

    scene.index = row("load")
    loaded = press(scene, pygame.K_RETURN)

    assert isinstance(loaded, PlayScene)
    assert loaded.run.stage_number == 7
    assert loaded.run.hero_type_id == "rogue"
    assert loaded.run.gold == 1234


def test_a_promoted_run_loads_back_as_the_class_it_became(atlas) -> None:
    """The end-to-end version of the promotion test in `test_save.py`.

    Worth having at this level too: the menu is where a real player meets this,
    and the failure -- half a campaign fought as the class you declined -- looks
    like a balance problem rather than a loading one.
    """
    run = Run.start(
        campaign(), BESTIARY, seed=2, at_stage=jobs.PROMOTION_STAGE, hero_type_id="knight"
    )
    jobs.promote(run, BESTIARY.promotions_for("knight")[0])
    save.write(run)

    scene = menu(atlas)
    scene.index = row("load")
    loaded = press(scene, pygame.K_RETURN)

    assert loaded.run.job_id == "dark_knight"
    assert loaded.world.hero.type.id == "dark_knight"


def test_the_row_names_the_run_rather_than_saying_load_game_twice(atlas) -> None:
    a_saved_run(stage=7, hero="rogue")
    scene = menu(atlas)
    scene.index = row("load")

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.draw(surface)
    assert BESTIARY["rogue"].name in save.describe(scene.saved, BESTIARY)


def test_a_corrupt_save_greys_the_row_instead_of_stopping_the_game(atlas) -> None:
    """A save file that cannot be read is not a reason the game will not open.

    The menu is the first thing constructed after the atlas, so an exception
    escaping here is a black window and a traceback rather than a title screen.
    """
    config.SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SAVE_FILE.write_text("{ not json", encoding="utf-8")

    scene = menu(atlas)
    assert not scene.can_load
    assert scene.save_error

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.index = row("load")
    scene.draw(surface)
    assert not is_blank(surface)


# --- the settings screen -----------------------------------------------------
def test_a_toggle_sticks_across_leaving_and_coming_back(atlas) -> None:
    settings = Settings()
    scene = OptionsScene(settings, lambda: None)
    scene.index = [name for name, _ in ROWS].index("screenshake")

    press(scene, pygame.K_RETURN)
    assert settings.screenshake is False

    scene._leave()
    from hack_and_slash import settings as settings_module

    assert settings_module.load().screenshake is False


def test_the_settings_a_run_starts_with_are_the_ones_that_were_set(atlas) -> None:
    """The wiring that makes the toggles mean anything.

    `Effects` is built in `PlayScene.__init__`, so a settings object that did
    not reach it would leave every toggle inert while still appearing to save.
    """
    settings = Settings(screenshake=False, damage_numbers=False)
    scene = MenuScene(campaign(), BESTIARY, atlas, settings=settings)
    scene.index = row("new")

    play = press(scene, pygame.K_RETURN)._begin()
    assert play.effects.screenshake is False
    assert play.effects.damage_numbers is False


def test_the_scale_row_cycles_through_the_whole_numbers_only(atlas) -> None:
    # Fractional scaling is what makes pixel art look smeared, so the row must
    # not be able to reach one.
    settings = Settings()
    scene = OptionsScene(settings, None)
    scene.index = [name for name, _ in ROWS].index("scale")

    seen = set()
    for _ in range(len(SCALES) + 1):
        press(scene, pygame.K_RIGHT)
        seen.add(settings.scale)
    assert seen == set(SCALES)


def test_typing_a_seed_replaces_the_command_line_flag(atlas) -> None:
    settings = Settings()
    scene = OptionsScene(settings, None)
    scene.index = [name for name, _ in ROWS].index("seed")

    for digit in "407":
        scene.handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_0, unicode=digit)
        )
    assert settings.seed == 407

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE))
    assert settings.seed == 40


def test_the_seed_reaches_the_run_it_is_supposed_to_seed(atlas) -> None:
    scene = MenuScene(campaign(), BESTIARY, atlas, seed=77, settings=Settings(seed=77))
    scene.index = row("new")
    assert press(scene, pygame.K_RETURN)._begin().run.seed == 77


# --- erasing -----------------------------------------------------------------
def test_erasing_takes_two_presses(atlas) -> None:
    """One keypress away from destroying a forty-stage run is one too few.

    The first press arms; the second erases. Asserted as two separate states so
    a change that made the row erase on the first press fails here rather than
    on somebody's campaign.
    """
    a_saved_run()
    profile.save(profile.Profile(runs_started=9))
    scene = OptionsScene(Settings(), None)
    scene.index = [name for name, _ in ROWS].index("erase")

    press(scene, pygame.K_RETURN)
    assert scene.confirming
    assert save.read() is not None, "one press erased the run"

    press(scene, pygame.K_RETURN)
    assert save.read() is None
    assert profile.load().runs_started == 0


def test_moving_away_disarms_the_erase_row(atlas) -> None:
    """A confirmation that survives navigation is not a confirmation.

    The player who moved off the row has said no as clearly as the one who
    pressed Escape, and an armed row waiting for them when they come back is a
    trap left behind them.
    """
    a_saved_run()
    scene = OptionsScene(Settings(), None)
    scene.index = [name for name, _ in ROWS].index("erase")

    press(scene, pygame.K_RETURN)
    assert scene.confirming

    press(scene, pygame.K_UP)
    press(scene, pygame.K_DOWN)
    assert not scene.confirming

    press(scene, pygame.K_RETURN)
    assert save.read() is not None, "the row was still armed after navigating away"


def test_the_menu_notices_the_run_was_erased(atlas) -> None:
    """The reason `_back` builds a fresh `MenuScene` rather than returning the
    one it left. The old object read the save file when it was constructed and
    would go on offering a row for a run that no longer exists."""
    a_saved_run()
    scene = menu(atlas)
    assert scene.can_load

    scene.index = row("settings")
    options = press(scene, pygame.K_RETURN)
    options.index = [name for name, _ in ROWS].index("erase")
    press(options, pygame.K_RETURN)
    press(options, pygame.K_RETURN)

    assert not press(options, pygame.K_ESCAPE).can_load


# --- the two stubs -----------------------------------------------------------
def test_the_stub_screens_draw_what_the_profile_knows(atlas) -> None:
    profile.save(profile.Profile(runs_started=4, runs_won=1, deepest_stage=23, best_gold=8100))
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))

    achievements = AchievementsScene(None)
    achievements.draw(surface)
    assert not is_blank(surface)
    assert ("Deepest stage", "23") in achievements.rows

    UnlockablesScene(None).draw(surface)
    assert not is_blank(surface)


def test_the_stub_screens_draw_on_a_machine_that_has_never_played(atlas) -> None:
    # Every counter zero, which is the state of a fresh clone and the one most
    # likely to divide by something or index into nothing.
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    for scene in (AchievementsScene(None), UnlockablesScene(None)):
        scene.draw(surface)
        assert not is_blank(surface)


# --- the autosave ------------------------------------------------------------
def cleared(atlas, start: int = 0, hero: str = "knight") -> PlayScene:
    """A scene that has just cleared a stage, with the panels still up."""
    scene = PlayScene(
        campaign(), BESTIARY, atlas, start_stage=start, hero_type_id=hero
    )
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    return scene


def test_a_run_is_saved_as_soon_as_it_is_being_played(atlas) -> None:
    scene = PlayScene(campaign(), BESTIARY, atlas, hero_type_id="priest")
    assert save.read() is None, "written before a frame had been drawn"

    scene.update(1.0)
    assert save.read()["hero_type_id"] == "priest"


def test_clearing_a_stage_saves_the_stage_that_was_entered(atlas) -> None:
    scene = cleared(atlas)
    assert scene.run.stage_number == 2

    press(scene, pygame.K_RETURN)  # close the shop
    scene.update(1.0)

    assert save.read()["index"] == 1


def test_nothing_is_saved_while_a_panel_is_still_open(atlas) -> None:
    """The reason the write is armed on the transition and taken afterwards.

    All three panels open on the tick a stage begins and all three change what
    the run is. A save taken then records a run that has not promoted and has
    not spent its gold.
    """
    scene = cleared(atlas)
    assert scene.shopping
    assert scene._needs_save, "the new stage was not armed to be saved"

    scene.update(1.0)
    assert save.read()["index"] == 0, (
        "the new stage was saved with the shop still open -- anything bought or "
        "chosen behind that panel would be missing from it"
    )

    # And it is taken the moment the panel is answered.
    press(scene, pygame.K_RETURN)
    scene.update(1.0)
    assert save.read()["index"] == 1


def test_the_save_taken_at_the_fork_records_the_class_that_was_chosen(atlas) -> None:
    """The failure this rules out is the worst one available to this feature.

    The promotion is offered exactly once per run. Saving before it is answered
    and then loading that save takes the fork away permanently -- and the player
    finds out twenty stages later, as a difficulty problem.
    """
    scene = cleared(atlas, start=jobs.PROMOTION_STAGE - 2)
    assert scene.promoting

    press(scene, pygame.K_1)  # take the first branch
    press(scene, pygame.K_RETURN)  # close the shop underneath it
    scene.update(1.0)

    assert save.read()["job_id"] == "dark_knight"


def test_a_lost_run_leaves_no_save_behind(atlas) -> None:
    """A dead run is not somewhere to come back to.

    Leaving the file would put it on the Load Game row and hand the player back
    the arena they just died in, at the health they died with.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.update(1.0)
    assert save.read() is not None

    scene.world.hero.hp = 0
    scene.update(1.0)

    assert scene.run.is_over
    assert save.read() is None


def test_a_finished_run_is_counted_and_forgotten(atlas) -> None:
    scene = PlayScene(
        campaign(), BESTIARY, atlas, start_stage=len(campaign()) - 1
    )
    scene.update(1.0)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)

    assert scene.run.outcome.value == "won"
    assert save.read() is None
    assert profile.load().runs_won == 1


def test_a_run_is_counted_once_when_it_begins_and_not_when_it_is_resumed(atlas) -> None:
    """`runs_started` counts runs, not sessions.

    Counted in `PlayScene.__init__` rather than at the character select so that
    every route in -- the menu, `--class`, R -- is counted on one line; which
    makes "a run handed in was already counted" the case that has to be
    excluded, and this is it.
    """
    PlayScene(campaign(), BESTIARY, atlas)
    assert profile.load().runs_started == 1

    run = a_saved_run()
    PlayScene(campaign(), BESTIARY, atlas, run=run)
    assert profile.load().runs_started == 1, "resuming a run counted it a second time"


def test_restarting_counts_a_new_run_and_keeps_the_class(atlas) -> None:
    scene = PlayScene(campaign(), BESTIARY, atlas, hero_type_id="priest")
    restarted = scene.restarted()

    assert profile.load().runs_started == 2
    assert restarted.hero_type_id == "priest"


def test_a_loaded_run_restarts_where_it_originally_began(atlas) -> None:
    """R is "try that again", and for a loaded run "that" is the run it was --
    from the top, as the class it began as, on the same seed. The three values
    `restarted()` needs are read off the run rather than off the arguments,
    because a loaded run arrives with the arguments unset."""
    run = Run.start(campaign(), BESTIARY, seed=42, at_stage=0, hero_type_id="magician")
    run.index = 12  # played twelve stages in
    scene = PlayScene(campaign(), BESTIARY, atlas, run=run)

    assert scene.seed == 42
    assert scene.hero_type_id == "magician"

    restarted = scene.restarted()
    assert restarted.run.seed == 42
    assert restarted.run.stage_number == 1
    assert restarted.world.hero.type.id == "magician"


# --- layout ------------------------------------------------------------------
def test_no_menu_label_runs_into_the_controls_column(atlas) -> None:
    """384 pixels, two columns, measured with the menu's own fonts.

    The same check `test_render.py` makes on the shop rows and the job panel
    columns, and for the same reason: a label that overruns looks like a
    rendering bug and is a wording one, and nothing headless sees it otherwise.
    """
    from hack_and_slash.scenes import menu as screen

    drawn = MenuScene(campaign(), BESTIARY, atlas)
    for _, label in ITEMS:
        right = screen.MENU_X + drawn.body.size(label)[0]
        assert right <= screen.CONTROLS_X, (
            f"'{label}' runs {right - screen.CONTROLS_X}px into the controls column"
        )

    for key, action in screen.CONTROLS:
        key_right = screen.CONTROLS_X + drawn.small.size(key)[0]
        assert key_right <= screen.CONTROLS_ACTION_X, f"'{key}' runs into its own action"

        action_right = screen.CONTROLS_ACTION_X + drawn.small.size(action)[0]
        assert action_right <= config.INTERNAL_W, f"'{action}' runs off the right edge"


def test_every_menu_row_fits_on_the_screen(atlas) -> None:
    from hack_and_slash.scenes import menu as screen

    last_row = screen.ROW_Y + (len(ITEMS) - 1) * screen.ROW_H
    assert last_row + 13 <= screen.DETAIL_Y, "the last row is drawn over the detail line"
    assert screen.DETAIL_Y + 11 <= config.INTERNAL_H, "the detail line is off the bottom"

    last_control = screen.CONTROLS_Y + (len(screen.CONTROLS) - 1) * screen.CONTROLS_H
    assert last_control + 11 <= config.INTERNAL_H


def test_no_settings_row_runs_into_its_own_value(atlas) -> None:
    from hack_and_slash.scenes import options as screen

    drawn = OptionsScene(Settings(), None)
    for name, label in ROWS:
        right = screen.LABEL_X + drawn.body.size(label)[0]
        assert right <= screen.VALUE_X, f"'{label}' runs into its value"

        text, _ = drawn._value(name, selected=True)
        assert screen.VALUE_X + drawn.body.size(text)[0] <= config.INTERNAL_W, (
            f"the value for '{label}' runs off the right edge"
        )

    last_row = screen.ROW_Y + (len(ROWS) - 1) * screen.ROW_H
    assert last_row + 13 <= screen.HINT_Y
    assert screen.HINT_Y + 11 <= config.INTERNAL_H
