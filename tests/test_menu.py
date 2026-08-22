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

from hack_and_slash import config, settings as settings_module
from hack_and_slash.bindings import Action
from hack_and_slash.core import campaign_io
from hack_and_slash.game import difficulty, jobs, profile, save
from hack_and_slash.game.run import Run
from hack_and_slash.scenes.achievements import AchievementsScene
from hack_and_slash.scenes import keymap
from hack_and_slash.scenes.controls import ROWS as ROWS_C
from hack_and_slash.scenes.controls import ControlsScene
from hack_and_slash.scenes.menu import ITEMS, MenuScene
from hack_and_slash.scenes.options import ROWS, OptionsScene
from hack_and_slash.scenes.play import PlayScene
from hack_and_slash.scenes.select import DIFFICULTY_Y, CharacterSelectScene
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


def row_of(action: str) -> int:
    """The index of a Settings row, by id -- `row()` above, for the other screen."""
    return [name for name, _ in ROWS].index(action)


#: Where each action sits on the Controls screen. Derived, so re-ordering
#: `bindings.LABELS` is a change to one dict rather than to a dozen indices here.
ROW_OF = {action: i for i, action in enumerate(ROWS_C) if action in Action.__members__.values()}


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


# --- the difficulty row on the character select ------------------------------
def select(atlas, **kwargs) -> CharacterSelectScene:
    return CharacterSelectScene(campaign(), BESTIARY, atlas, **kwargs)


def test_the_character_select_opens_on_the_measured_tier(atlas) -> None:
    """Not on the first tier in the file -- on the *default* one.

    A screen that opened on Forgiving would make the unmeasured tier the normal
    way to play the game, and every number in docs/balance.md would describe a
    fight most players never have.
    """
    scene = select(atlas)
    assert scene.difficulty.is_identity
    assert scene.difficulty.id == difficulty.table().default.id


def test_up_and_down_move_the_tier_and_leave_the_roster_alone(atlas) -> None:
    """Two axes, no focus cursor. Left and right are still the roster."""
    scene = select(atlas)
    hero_before = scene.index

    press(scene, pygame.K_DOWN)
    assert scene.difficulty.id == "relentless"
    assert scene.index == hero_before, "moving the tier moved the roster"

    press(scene, pygame.K_UP)
    press(scene, pygame.K_UP)
    assert scene.difficulty.id == "forgiving"


def test_the_tier_clamps_rather_than_wrapping(atlas) -> None:
    """The roster wraps and this deliberately does not. Difficulty is an
    ordered scale, and wrapping one puts the hardest tier a single keypress
    below the easiest -- the worst misread available on this screen."""
    tiers = difficulty.table().tiers
    walk = len(tiers) + 3  # comfortably past either end

    scene = select(atlas)
    for _ in range(walk):
        press(scene, pygame.K_DOWN)
    assert scene.difficulty.id == tiers[-1].id

    for _ in range(walk):
        press(scene, pygame.K_UP)
    assert scene.difficulty.id == difficulty.table().gentlest.id


def test_the_chosen_tier_reaches_the_run(atlas) -> None:
    """The whole point of the row. It has to survive the scene handover, land
    on the `Run`, and reach the `World` where combat can read it."""
    scene = select(atlas)
    press(scene, pygame.K_DOWN)

    play = press(scene, pygame.K_RETURN)
    assert isinstance(play, PlayScene)
    assert play.run.difficulty.id == "relentless"
    assert play.run.world.difficulty.id == "relentless"


def test_restarting_keeps_the_tier_that_was_chosen(atlas) -> None:
    """`R` is a second attempt at this run. A second attempt that quietly
    changed how hard it was would not be one -- the same argument that keeps
    the class across a restart."""
    scene = select(atlas)
    press(scene, pygame.K_DOWN)
    play = press(scene, pygame.K_RETURN)

    assert play.restarted().run.difficulty.id == "relentless"


def click_internal(scene, x: int, y: int):
    """Click at a point in the 384x216 internal space.

    The scene hit-tests in window coordinates, so the point has to go out
    through the same integer scale and letterbox the picture came in through --
    which is the whole reason this helper exists rather than passing `(x, y)`
    straight in and quietly testing the top-left corner of the window.
    """
    window = pygame.display.get_surface()
    win_w, win_h = window.get_size()
    scale = config.integer_scale(win_w, win_h)
    off_x, off_y = config.letterbox_offset(win_w, win_h)
    return scene.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=(off_x + x * scale, off_y + y * scale),
        )
    )


def test_every_tier_can_be_reached_with_the_mouse(atlas, display) -> None:
    """The regression. A mouse could reach exactly one of the three tiers.

    The first draft hit-tested the whole row as one band and advanced by one per
    click. `_move_difficulty` clamps rather than wrapping -- deliberately, since
    wrapping puts the hardest tier one keypress below the easiest -- so clicking
    walked up to Relentless and stopped there permanently. From the default,
    a single click jumped straight past Normal and there was no route back to
    either of the other two.

    So this walks every tier forwards *and* backwards: forwards alone would
    still pass against the broken version for the last tier.
    """
    scene = select(atlas)
    tiers = [tier.id for tier in scene.difficulties.tiers]

    for expected, (left, width) in zip(tiers, scene._tier_spans()):
        click_internal(scene, left + width // 2, DIFFICULTY_Y + 3)
        assert scene.difficulty.id == expected

    for expected, (left, width) in reversed(list(zip(tiers, scene._tier_spans()))):
        click_internal(scene, left + width // 2, DIFFICULTY_Y + 3)
        assert scene.difficulty.id == expected, (
            f"could not get back to {expected} with the mouse -- the row is a "
            f"one-way trip again"
        )


def test_the_drawn_tier_row_is_the_row_that_can_be_clicked(atlas, display) -> None:
    """`_tier_spans` is the single source of the layout, and this is why.

    Two copies of a coordinate is how a clickable row drifts off the thing it
    claims to click -- the label moves, the hit-box does not, and the symptom is
    a player clicking a word and nothing happening.
    """
    scene = select(atlas)
    for i, (left, width) in enumerate(scene._tier_spans()):
        assert scene._tier_at(_to_window(left + width // 2, DIFFICULTY_Y + 3)) == i


def test_a_click_beside_the_tier_names_changes_nothing(atlas, display) -> None:
    """The row is the names, not the width of the screen. A click in the empty
    margin either side is not a vote for the nearest one."""
    scene = select(atlas)
    before = scene.difficulty.id
    click_internal(scene, 4, DIFFICULTY_Y + 3)
    assert scene.difficulty.id == before


def _to_window(x: int, y: int) -> tuple[int, int]:
    window = pygame.display.get_surface()
    win_w, win_h = window.get_size()
    scale = config.integer_scale(win_w, win_h)
    off_x, off_y = config.letterbox_offset(win_w, win_h)
    return (off_x + x * scale, off_y + y * scale)


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


def test_restarting_keeps_the_settings_the_run_was_started_with(atlas) -> None:
    """`restarted()` passed the difficulty and not the preferences.

    A real bug before rebinding landed -- press R and screenshake came back on --
    and invisible enough to have gone unnoticed, because nothing about a restart
    says it should have kept anything. With the key bindings on the same object
    it stops being invisible: it would mean the keys reverting under somebody
    who pressed restart, which reads as a broken build.
    """
    settings = Settings(screenshake=False, bindings={"dodge": ["c"]})
    scene = PlayScene(campaign(), BESTIARY, atlas, settings=settings)

    again = scene.restarted()
    assert again.settings.screenshake is False
    assert keymap.keycodes(again.settings)[Action.DODGE] == (pygame.K_c,)


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
    """A scene that has just cleared a stage and stepped into the room after it."""
    scene = PlayScene(
        campaign(), BESTIARY, atlas, start_stage=start, hero_type_id=hero
    )
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    return scene


def at_a_stall(scene) -> PlayScene:
    """Walk onto a shop stall in the reward room, which is what opens the shop."""
    from hack_and_slash.core.level import PropKind

    scene.world.props[0].kind = PropKind.STALL
    scene.world.hero.pos = scene.world.props[0].pos
    scene.update(1.0)
    return scene


def out_through_a_door(scene, door: int = 0) -> PlayScene:
    """Leave the reward room, which is what starts the next arena."""
    doors = [prop for prop in scene.world.props if prop.is_door]
    scene.world.hero.pos = doors[door].pos
    scene.update(1.0)
    return scene


def test_a_run_is_saved_as_soon_as_it_is_being_played(atlas) -> None:
    scene = PlayScene(campaign(), BESTIARY, atlas, hero_type_id="priest")
    assert save.read() is None, "written before a frame had been drawn"

    scene.update(1.0)
    assert save.read()["hero_type_id"] == "priest"


def test_clearing_a_stage_saves_the_room_and_then_the_stage(atlas) -> None:
    """Two boundaries now, and both are clean.

    A save is taken on the tick a *room* begins as readily as on the tick an
    arena does, and for the same reason: `Run._enter_room` builds one out of a
    level, a seed and the health carried in, and nothing has moved yet. Quitting
    inside a fountain and being handed back the arena before it would be a stage
    replayed for nothing.
    """
    scene = cleared(atlas)
    assert scene.run.stage_number == 1, "a room does not advance the stage count"

    scene.update(1.0)
    assert save.read()["room"] == scene.run.room.value
    assert save.read()["index"] == 0

    out_through_a_door(scene)
    scene.update(1.0)
    assert save.read()["index"] == 1
    assert save.read()["room"] == "", "the arena was saved as though it were a room"


def test_nothing_is_saved_while_a_panel_is_still_open(atlas) -> None:
    """The reason the write is armed on the transition and taken afterwards.

    The panel that opens on a transition is the promotion, and it changes what
    the run is. A save taken with it still up records a run that has not
    promoted -- and loading that save takes the fork away permanently, on the
    one transition in the game where it is offered exactly once.

    The shop used to be the example here, and it is not any more: it opens on
    walking up to a stall, well after the transition has been saved. That is not
    a hole. Nothing about the shop is *unrecorded* at the moment the room is
    saved -- the purchase simply has not happened yet, and the save is taken
    again the moment the panel closes.
    """
    scene = cleared(atlas, start=jobs.PROMOTION_STAGE - 2)
    out_through_a_door(scene)

    assert scene.promoting, "the fork did not open"
    assert scene._needs_save, "the new stage was not armed to be saved"

    scene.update(1.0)
    assert save.read()["job_id"] == "", (
        "the new stage was saved with the fork still open -- the branch chosen "
        "behind that panel would be missing from it"
    )

    # And it is taken the moment the panel is answered.
    press(scene, pygame.K_1)
    scene.update(1.0)
    assert save.read()["job_id"] == "dark_knight"


def test_the_save_taken_at_the_fork_records_the_class_that_was_chosen(atlas) -> None:
    """The failure this rules out is the worst one available to this feature.

    The promotion is offered exactly once per run. Saving before it is answered
    and then loading that save takes the fork away permanently -- and the player
    finds out twenty stages later, as a difficulty problem.
    """
    scene = cleared(atlas, start=jobs.PROMOTION_STAGE - 2)
    # The fork is offered on arriving at the *next arena*, and a reward room now
    # sits between the two -- so clearing is only half of getting there.
    out_through_a_door(scene)
    assert scene.promoting

    press(scene, pygame.K_1)  # take the first branch
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


# --- the controls screen -----------------------------------------------------
def controls(**kwargs) -> ControlsScene:
    return ControlsScene(kwargs.pop("settings", Settings()), kwargs.pop("on_exit", None))


def bound(scene, action) -> tuple[int, ...]:
    return keymap.keycodes(scene.settings)[action]


def test_the_controls_row_opens_the_controls_screen(atlas) -> None:
    screen = OptionsScene(Settings(), None)
    screen.index = row_of("controls")

    assert isinstance(press(screen, pygame.K_RETURN), ControlsScene)


def test_the_controls_screen_comes_back_to_the_settings_it_was_opened_from(
    atlas,
) -> None:
    """And to the same row, because a player went to look something up.

    `OptionsScene._resume` hands back the live instance rather than rebuilding
    it, unlike `menu._back` -- nothing on the settings screen is a snapshot of
    anything, so there is nothing that could have gone stale behind it.
    """
    screen = OptionsScene(Settings(), None)
    screen.index = row_of("controls")
    opened = press(screen, pygame.K_RETURN)

    assert press(opened, pygame.K_ESCAPE) is screen
    assert screen.index == row_of("controls")


def test_arming_a_row_and_pressing_a_key_rebinds_it(atlas) -> None:
    scene = controls()
    scene.index = ROW_OF[Action.HEAVY]

    press(scene, pygame.K_RETURN)
    assert scene.armed is Action.HEAVY

    press(scene, pygame.K_v)
    assert scene.armed is None
    assert bound(scene, Action.HEAVY) == (pygame.K_v,)


def test_escape_while_armed_cancels_instead_of_leaving(atlas) -> None:
    """The one place in the game Escape does not mean "back".

    It is also the thing that makes the screen safe to use: a player who armed a
    row by accident needs a way out that is not "bind Escape to the roll", and
    Escape is the key they will reach for.
    """
    left = []
    scene = controls(on_exit=lambda: left.append(True))
    scene.index = ROW_OF[Action.DODGE]
    press(scene, pygame.K_RETURN)

    assert press(scene, pygame.K_ESCAPE) is None
    assert not left, "Escape left the screen instead of cancelling the arming"
    assert scene.armed is None
    assert bound(scene, Action.DODGE) == (
        pygame.K_SPACE,
        pygame.K_LSHIFT,
        pygame.K_RSHIFT,
    )


def test_escape_leaves_when_nothing_is_armed(atlas) -> None:
    left = []
    scene = controls(on_exit=lambda: left.append(True) or None)

    press(scene, pygame.K_ESCAPE)
    assert left, "Escape did not leave a screen with no row armed"


def test_a_refused_binding_says_why_and_changes_nothing(atlas) -> None:
    scene = controls()
    scene.index = ROW_OF[Action.DODGE]
    press(scene, pygame.K_RETURN)
    press(scene, pygame.K_1)

    assert scene.complaint, "a refusal drew no reason"
    assert scene.settings.bindings == {}


def test_moving_the_cursor_clears_the_last_complaint(atlas) -> None:
    """A refusal answers a keypress; it is not a state to be stuck in."""
    scene = controls()
    scene.index = ROW_OF[Action.DODGE]
    press(scene, pygame.K_RETURN)
    press(scene, pygame.K_1)
    assert scene.complaint

    press(scene, pygame.K_DOWN)
    assert not scene.complaint


def test_resetting_takes_two_presses(atlas) -> None:
    """The same confirmation the erase row uses, for a smaller loss."""
    scene = controls()
    scene.index = ROW_OF[Action.HEAVY]
    press(scene, pygame.K_RETURN)
    press(scene, pygame.K_v)

    scene.index = len(ROWS_C) - 1
    press(scene, pygame.K_RETURN)
    assert scene.confirming
    assert bound(scene, Action.HEAVY) == (pygame.K_v,), "one press reset it"

    press(scene, pygame.K_RETURN)
    assert bound(scene, Action.HEAVY) == (pygame.K_e,)
    assert scene.settings.bindings == {}


def test_moving_away_disarms_the_reset_row(atlas) -> None:
    scene = controls()
    scene.index = len(ROWS_C) - 1
    press(scene, pygame.K_RETURN)

    press(scene, pygame.K_UP)
    assert not scene.confirming


def test_a_rebinding_is_written_on_the_way_out(atlas) -> None:
    """Written on exit, not per keypress -- `options.py`'s rule, same reason."""
    scene = controls()
    scene.index = ROW_OF[Action.DODGE]
    press(scene, pygame.K_RETURN)
    press(scene, pygame.K_c)

    assert settings_module.load().bindings == {}, "written before leaving"

    press(scene, pygame.K_ESCAPE)
    assert settings_module.load().bindings == {"dodge": ["c"]}


def test_the_screen_draws_something(atlas, display) -> None:
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    controls().draw(surface)
    assert not is_blank(surface)


# --- layout ------------------------------------------------------------------
def test_the_menu_column_is_centred_and_nothing_else_is_on_the_screen(atlas) -> None:
    """384 pixels, one column, measured with the menu's own fonts.

    Centring is checked rather than assumed because `MENU_X` is a constant and
    the labels are not: renaming "Achievements" to something longer moves the
    block off centre and nothing headless would otherwise see it. The tolerance
    is half a row height, which is the point at which a column stops reading as
    centred and starts reading as slightly wrong.

    The second half is the harder claim. The controls used to be printed down
    the right of this screen and they are now on Settings; the tuple is gone
    from this module, and this test fails if somebody puts one back rather than
    moving it.
    """
    from hack_and_slash.scenes import menu as screen

    drawn = MenuScene(campaign(), BESTIARY, atlas)
    widest = max(drawn.body.size(label)[0] for _, label in ITEMS)

    left = screen.CARET_X
    right = screen.MENU_X + widest
    assert left >= 0 and right <= config.INTERNAL_W, "the column is off the screen"

    drift = abs((left + right) / 2 - config.INTERNAL_W / 2)
    assert drift <= 8, f"the menu column sits {drift:.0f}px off centre"

    assert widest <= screen.ROW_LABEL_W, (
        "a label is wider than the clickable row, so its right-hand end cannot "
        "be clicked"
    )
    assert not hasattr(screen, "CONTROLS"), (
        "the controls are back on the title screen -- they belong on Settings"
    )


def test_every_menu_row_fits_on_the_screen(atlas) -> None:
    from hack_and_slash.scenes import menu as screen

    last_row = screen.ROW_Y + (len(ITEMS) - 1) * screen.ROW_H
    assert last_row + 13 <= screen.DETAIL_Y, "the last row is drawn over the detail line"
    assert screen.DETAIL_Y + 11 <= config.INTERNAL_H, "the detail line is off the bottom"


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


def test_every_controls_row_fits_beside_its_keys(atlas) -> None:
    """The check that followed the tuple onto the screen it became.

    Twelve rows on a 216px surface is the tightest column in the game, and the
    value side is the half that grows: the roll ships with three keys and every
    label here is a whole phrase. Measured with the screen's own font, because a
    row that overruns is a rendering bug that reads as a wording one.
    """
    from hack_and_slash.scenes import controls as screen

    drawn = ControlsScene(Settings(), None)
    for i, row in enumerate(screen.ROWS):
        label, value, _ = drawn._row(row, selected=True)

        right = screen.LABEL_X + drawn.body.size(label)[0]
        assert right <= screen.KEY_X, f"'{label}' runs into its keys"

        value_right = screen.KEY_X + drawn.body.size(value)[0]
        assert value_right <= config.INTERNAL_W, f"the keys for '{label}' run off"

        assert screen.row_y(i) + 11 <= screen.HINT_Y, f"'{label}' crosses the hint"

    assert screen.TITLE_Y + 22 <= screen.ROW_Y, "the title is drawn over the first row"
    assert screen.HINT_Y + 11 <= config.INTERNAL_H, "the hint line is off the bottom"


def test_the_widest_thing_the_controls_screen_can_say_still_fits(atlas) -> None:
    """Every transient string, not just the resting state.

    The armed row, the reset confirmation and all three hint lines are drawn in
    the same places as the values they replace, and each is longer than what it
    covers. A screen that fits until somebody presses a key is not one that fits.
    """
    from hack_and_slash.scenes import controls as screen

    drawn = ControlsScene(Settings(), None)
    drawn.armed = list(screen.ROWS)[0]
    _, armed_value, _ = drawn._row(screen.ROWS[0], selected=True)
    assert screen.KEY_X + drawn.body.size(armed_value)[0] <= config.INTERNAL_W

    drawn.armed = None
    drawn.confirming = True
    _, confirm_value, _ = drawn._row(screen.RESET, selected=True)
    assert screen.KEY_X + drawn.body.size(confirm_value)[0] <= config.INTERNAL_W

    longest = max(
        "up / down  choose      Enter  rebind      Esc  back",
        "press a key to bind it, Esc to cancel",
        "space is the only Dodge roll key",
        key=lambda text: drawn.small.size(text)[0],
    )
    assert drawn.small.size(longest)[0] <= config.INTERNAL_W
