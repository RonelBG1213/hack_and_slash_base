"""The title screen: six things you can do, and nothing else.

This used to be a splash. `handle_event` took *any* key as "start" and Escape as
"quit", which is two answers to a screen that now has to ask six -- so the whole
input half is new. What is unchanged is the principle it was written under:
**this screen still knows nothing about how a run works.** It picks a
destination and hands over. `CharacterSelectScene` builds a run; `save.restore`
rebuilds one; neither of them is understood here.

One centred column, because the screen asks one question. It was two columns for
a while, with the key bindings printed down the right-hand side, and the argument
for that was real: a reference stacked *under* a decision gets buried. But the
controls were not a second column of the same question -- they were a different
kind of thing sharing a screen with a menu, and the six rows read as the left
half of something rather than as the whole of it.

They now live on the Settings screen, which is where a player goes to look
something up rather than to start. Nothing was deleted: `options.CONTROLS` is the
same tuple, moved.

The highlighted row explains itself on one line at the bottom -- the same shape
`select.py` uses for the class it is sitting on, and for the same reason: a grid
of names is a menu, and a line of prose is the difference between choosing and
guessing.

Two of the six are honest stubs. Achievements and Unlockables open real screens
that draw real numbers and define nothing, which is what they are.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..core.campaign import Campaign
from ..game import save
from ..game.entities import Bestiary
from ..render.atlas import Atlas
from ..settings import Settings
from .achievements import AchievementsScene
from .base import Scene
from .options import OptionsScene
from .play import PlayScene
from .select import CharacterSelectScene
from .unlockables import UnlockablesScene

#: The rows, in order, as `(id, label)`. The id is what `_activate` branches on
#: and what `DETAILS` is keyed by, so renaming a label is a change to one string
#: and never to the wiring behind it.
ITEMS = (
    ("new", "New Game"),
    ("load", "Load Game"),
    ("settings", "Settings"),
    ("achievements", "Achievements"),
    ("unlockables", "Unlockables"),
    ("quit", "Quit Game"),
)

#: One line per row, shown for whichever is highlighted. Load Game is absent on
#: purpose -- its line is the save itself, and there is no fixed sentence that
#: says as much as "Knight -- stage 14 -- 3120g" does.
DETAILS = {
    "new": "choose a class and begin at stage one",
    "settings": "window, effects, seed",
    "achievements": "what you have done so far",
    "unlockables": "what is still to earn",
    "quit": "close the game",
}

# --- layout, in the 384x216 internal space -----------------------------------
# Named rather than inlined so `test_menu.py` can measure the real fonts against
# the real numbers. A label that runs off its column is a rendering bug that
# looks like a wording one, which is the failure `test_render.py` already catches
# for the shop and the job panel.
TITLE_Y = 14
SUBTITLE_Y = 52

#: The column is centred as a *block* -- caret included -- rather than each row
#: being centred on its own. Centring the rows individually puts the caret in a
#: different place on every row, and the caret is the thing the eye tracks while
#: the arrow keys are held. Widest label is "Achievements" at 79px in `body`;
#: with the 12px caret that is a 91px block, so 146 leaves 146 on the far side.
MENU_X = 158
ROW_Y = 78
ROW_H = 17
CARET_X = MENU_X - 12

#: How far right of `MENU_X` a click still counts as a row. Not measured off the
#: font: the mouse handler runs before anything is drawn on the very first frame
#: and a click target that depends on a rendered label is a click target that
#: does not exist yet.
ROW_LABEL_W = 84

DETAIL_Y = 188


class MenuScene(Scene):
    def __init__(
        self,
        campaign: Campaign,
        bestiary: Bestiary,
        atlas: Atlas,
        seed: int = 0,
        settings: Optional[Settings] = None,
        index: int = 0,
    ) -> None:
        self.campaign = campaign
        self.bestiary = bestiary
        self.atlas = atlas
        self.seed = seed

        # Defaulted, so every existing construction of this scene -- the tests,
        # `--stage`, the `on_exit` lambdas in main.py -- goes on working.
        self.settings = settings or Settings()

        #: Remembered across a visit to Settings and back, so leaving a screen
        #: puts the cursor where it was rather than at the top. Wrapped by
        #: `_move`, so an out-of-range value from a caller cannot break drawing.
        self.index = max(0, min(index, len(ITEMS) - 1))

        self.title = pygame.font.Font(None, 44)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.tick = 0

        #: The saved run, read once when this screen is built. Every route back
        #: here constructs a fresh `MenuScene`, so "once" is also "every time" --
        #: a run that just ended has already deleted its save and the row is
        #: correctly dead by the time the player is looking at it.
        self.saved: Optional[dict] = None

        #: Set when there *is* a file and it cannot be read. Distinct from
        #: `saved is None`, which is the ordinary state of a fresh install: one
        #: greys the row silently and the other has something to say.
        self.save_error = ""
        self._read_save()

    def _read_save(self) -> None:
        try:
            self.saved = save.read()
        except save.SaveFormatError as exc:
            self.saved = None
            self.save_error = str(exc)

    @property
    def can_load(self) -> bool:
        return self.saved is not None

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # Still quits, as it always has. Escape is "back" everywhere in
                # this game and there is nothing behind the title screen.
                return self._quit()
            if event.key in (pygame.K_UP, pygame.K_w):
                self._move(-1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._move(1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self._activate()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self._row_at(event.pos)
            if hit is None:
                return None
            # Click to highlight, click again to commit -- the character
            # select's rule, and it matters more here: one of these six rows
            # closes the game.
            if hit == self.index:
                return self._activate()
            self.index = hit
        return None

    def _move(self, step: int) -> None:
        # Wraps, for the reason `select.py` gives: a list with two ends that
        # stops dead at them is worse than the one moment of surprise wrapping
        # costs. A disabled Load Game row is still landed on rather than skipped
        # -- a cursor that jumps over a row leaves the player wondering what
        # they missed, and the row explains itself once they are on it.
        self.index = (self.index + step) % len(ITEMS)

    def _row_at(self, window_pos: tuple[int, int]) -> Optional[int]:
        """Which row a window-space click landed on, if any.

        The mouse arrives in window coordinates and this screen is laid out in
        the 384x216 internal space, so it comes back through the same integer
        scale and letterbox the picture went out through -- exactly as
        `select.py:_column_at` does it.
        """
        window = pygame.display.get_surface()
        if window is None:
            return None

        win_w, win_h = window.get_size()
        x, y = config.window_to_internal(*window_pos, win_w, win_h)
        # Bounded by the block itself now that there is nothing to its right.
        # A generous right edge rather than a per-label one: a click two pixels
        # past the end of "Settings" meant that row and nothing else.
        if x < CARET_X or x > MENU_X + ROW_LABEL_W:
            return None

        row = (y - ROW_Y) // ROW_H
        if 0 <= row < len(ITEMS) and y >= ROW_Y:
            return int(row)
        return None

    # --- what the rows do ----------------------------------------------------
    def _activate(self) -> Optional[Scene]:
        """Take the highlighted row. None means "nothing happened", which is a
        real answer here: a Load Game row with no save behind it."""
        action = ITEMS[self.index][0]

        if action == "new":
            return self._start_at(0)
        if action == "load":
            return self._load()
        if action == "settings":
            # The live `Settings` object, not a copy. The options screen edits it
            # in place and `_back` hands the same one to the next `MenuScene`, so
            # a toggle is in force for the run started immediately afterwards
            # without anything having to be re-read from disk.
            return OptionsScene(self.settings, self._back)
        if action == "achievements":
            return AchievementsScene(self._back)
        if action == "unlockables":
            return UnlockablesScene(self._back)
        if action == "quit":
            return self._quit()
        return None

    def _back(self) -> "MenuScene":
        """Come back here, on the row that was left, with the save re-read.

        A fresh scene rather than the same object: the options screen can delete
        the save file, and a `MenuScene` held across that would go on drawing a
        row for a run that no longer exists.
        """
        return MenuScene(
            self.campaign,
            self.bestiary,
            self.atlas,
            seed=self.seed,
            settings=self.settings,
            index=self.index,
        )

    def _quit(self) -> None:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        return None

    def _load(self) -> Optional[Scene]:
        """Pick a saved run back up, or do nothing if there is not one.

        Nothing is the right answer rather than a message: the row was greyed
        out before it was pressed, and greying it is what said so.
        """
        if self.saved is None:
            return None

        try:
            run = save.restore(self.saved, self.campaign, self.bestiary)
        except save.SaveFormatError as exc:
            # Only reachable if the file changed between `read` and here, or if
            # it parses as JSON and describes nothing coherent. Reported on the
            # row rather than raised -- a bad save is not a reason the game
            # stops.
            self.saved = None
            self.save_error = str(exc)
            return None

        return PlayScene(
            self.campaign,
            self.bestiary,
            self.atlas,
            run=run,
            settings=self.settings,
            on_exit=self._back,
        )

    def _start_at(self, stage_index: int) -> CharacterSelectScene:
        """Hand over to the character select, which hands over to the run.

        `--stage` passes straight through, so jumping to a stage still asks
        which class to jump there as.
        """
        return CharacterSelectScene(
            self.campaign,
            self.bestiary,
            self.atlas,
            seed=self.seed,
            start_stage=stage_index,
            settings=self.settings,
            on_exit=self._back,
        )

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("HACK AND SLASH", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, TITLE_Y))

        subtitle = self.small.render(
            f"{self.campaign.name}  --  {len(self.campaign)} stages", False, config.GREY
        )
        surface.blit(subtitle, ((config.INTERNAL_W - subtitle.get_width()) // 2, SUBTITLE_Y))

        self._draw_rows(surface)
        self._draw_detail(surface)

    def _draw_rows(self, surface: pygame.Surface) -> None:
        for i, (action, label) in enumerate(ITEMS):
            y = ROW_Y + i * ROW_H
            selected = i == self.index
            enabled = action != "load" or self.can_load

            # Three states, and they have to be three: a greyed row that is also
            # the highlighted one still has to look highlighted, or the cursor
            # vanishes when it lands on Load Game with no save.
            if not enabled:
                color = config.GREY if selected else (70, 74, 84)
            else:
                color = config.WHITE if selected else config.GREY

            surface.blit(self.body.render(label, False, color), (MENU_X, y))

            if selected:
                caret = self.body.render(">", False, config.ACCENT)
                surface.blit(caret, (CARET_X, y))

    def _draw_detail(self, surface: pygame.Surface) -> None:
        """One line about the highlighted row, centred at the foot of the screen.

        Full width is available down here, which is the reason the saved run's
        description lives on this line rather than beside its own row: it is the
        longest string on the screen and it would not fit in the column.
        """
        action = ITEMS[self.index][0]

        if action == "load":
            if self.saved is not None:
                text, color = save.describe(self.saved, self.bestiary), config.GOOD
            elif self.save_error:
                text, color = "the saved run could not be read", config.BAD
            else:
                text, color = "no saved run yet", config.GREY
        else:
            text, color = DETAILS.get(action, ""), config.GREY

        if not text:
            return
        line = self.small.render(text, False, color)
        surface.blit(line, ((config.INTERNAL_W - line.get_width()) // 2, DETAIL_Y))
