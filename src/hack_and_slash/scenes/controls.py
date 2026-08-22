"""The Controls screen: eleven actions, and the key each one answers to.

`scenes/options.py` used to draw this list down its right-hand side and said, in
its own docstring, what would happen the day rebinding landed:

    They are drawn, not editable. Rebinding is a real feature and this is not
    it; the column would be the same column with a cursor in it, and the day
    that lands it takes `CONTROLS` with it rather than replacing anything here.

This is that day, and the column moved out rather than growing a cursor. Eleven
actions and a reset row is twelve rows; at the spacing the Settings screen uses
they run off the bottom of a 216px surface and through the hint line on the way.
So the settings keep their six rows and this is its own screen, one row per
action, reached from a Controls row on the one it left.

**Only the gameplay keys are here**, which is a decision rather than a first
pass -- see `docs/limits.md`. Escape, Enter and the digits that buy at a stall
and choose at the fork are how a player reaches this screen and leaves it, and
`keymap.RESERVED` refuses to hand any of them out.

The screen edits a live `Settings` in place and writes it on the way out, the
way `scenes/options.py` does and for the same reason: a settings file rewritten
on every keypress is a write per arrow press, and the only thing it buys is
surviving a crash mid-menu.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config, settings as settings_module
from ..bindings import LABELS, Action
from ..settings import Settings
from . import keymap
from .base import Scene

#: The reset row, which is not an action. A string beside the `Action` members
#: rather than a twelfth enum member: `Action` is what a key can be bound *to*,
#: and "put everything back" is not one of those.
RESET = "reset"

#: Every row, in order. The actions come from `bindings.LABELS`, so the screen
#: cannot fall out of step with the thing it edits -- an action added there
#: appears here with no change at all, which is the property that matters when
#: the controller arrives and the list grows.
ROWS: tuple[Action | str, ...] = tuple(LABELS) + (RESET,)

# --- layout, in the 384x216 internal space -----------------------------------
# Twelve rows leave less room than the six on the Settings screen, so the
# spacing is measured rather than inherited: at `pygame.font.Font(None, 15)` the
# widest label is "Character sheet" at 82px and the widest value is the roll's
# three shipped keys at 132px, which is what sets `KEY_X` and leaves the value
# column ending at 268 of 384. `test_menu.py` measures both against the real
# fonts rather than trusting these numbers to stay true.
TITLE_Y = 14
ROW_Y = 40
ROW_H = 13
LABEL_X = 40
KEY_X = 136

#: A gap above the reset row, because it is not one of the eleven and a player
#: scanning the column should not have to read it to know that.
RESET_GAP = 4

HINT_Y = 202


class ControlsScene(Scene):
    def __init__(self, settings: Settings, on_exit) -> None:
        #: Held, not copied -- the same arrangement `OptionsScene` has, so a
        #: rebinding is in force for the run started immediately afterwards.
        self.settings = settings
        self.on_exit = on_exit

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 15)
        self.small = pygame.font.Font(None, 14)
        self.index = 0

        #: The action waiting for a key, or `None`. While this is set the screen
        #: is listening rather than navigating, and **Escape means cancel**.
        #: That is the one place in the game Escape does not mean "back", and it
        #: is what makes the screen safe: a player who armed a row by accident
        #: needs a way out that is not "bind Escape to the roll".
        self.armed: Optional[Action] = None

        #: Why the last attempt was refused, drawn in place of the hint. Cleared
        #: by the next thing the player does, so it reads as an answer to what
        #: they just tried rather than as a state the screen is stuck in.
        self.complaint = ""

        #: True once the reset row has been pressed and is waiting to be pressed
        #: again. The same two-press confirmation as the Settings screen's erase
        #: row, cleared by any cursor move for the same reason: a confirmation
        #: that survives navigation is not a confirmation, it is a trap left
        #: armed behind the player.
        self.confirming = False

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type != pygame.KEYDOWN:
            return None

        if self.armed is not None:
            self._take(event)
            # Never a scene change, Escape included. See `armed`.
            return None

        if event.key == pygame.K_ESCAPE:
            return self._leave()

        if event.key in (pygame.K_UP, pygame.K_w):
            self._move(-1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._move(1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate()
        return None

    def _take(self, event: pygame.event.Event) -> None:
        """The armed row's next keypress. Escape cancels; anything else binds."""
        action, self.armed = self.armed, None

        if event.key == pygame.K_ESCAPE:
            self.complaint = ""
            return

        name = keymap.name_of(event.key)
        if name is None:
            # A key SDL cannot name back to itself. Rare, and the alternative is
            # writing down a binding that stops working when the game restarts.
            self.complaint = "that key cannot be bound"
            return

        self.complaint = keymap.assign(self.settings, action, name) or ""

    def _move(self, step: int) -> None:
        self.index = (self.index + step) % len(ROWS)
        self.confirming = False
        self.complaint = ""

    def _activate(self) -> None:
        row = ROWS[self.index]
        self.complaint = ""

        if row == RESET:
            if not self.confirming:
                self.confirming = True
                return
            keymap.reset(self.settings)
            self.confirming = False
            return

        self.armed = row
        self.confirming = False

    def _leave(self) -> Optional[Scene]:
        settings_module.save(self.settings)
        return self.on_exit() if self.on_exit else None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("CONTROLS", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, TITLE_Y))

        for i, row in enumerate(ROWS):
            y = row_y(i)
            selected = i == self.index
            label, value, color = self._row(row, selected)

            surface.blit(
                self.body.render(
                    label, False, config.WHITE if selected else config.GREY
                ),
                (LABEL_X, y),
            )
            if selected:
                surface.blit(
                    self.body.render(">", False, config.ACCENT), (LABEL_X - 12, y)
                )
            if value:
                surface.blit(self.body.render(value, False, color), (KEY_X, y))

        self._draw_hint(surface)

    def _row(self, row: Action | str, selected: bool) -> tuple[str, str, tuple]:
        """Label, value, and the value's colour."""
        if row == RESET:
            if self.confirming:
                return "Reset to defaults", "press again", config.BAD
            return "Reset to defaults", "", config.GREY

        if self.armed == row:
            return LABELS[row], "press a key", config.ACCENT

        return (
            LABELS[row],
            keymap.describe(row, self.settings),
            config.WHITE if selected else config.GREY,
        )

    def _draw_hint(self, surface: pygame.Surface) -> None:
        """One line, and it says the most specific true thing available.

        A refusal displaces the hint rather than sitting beside it: the player
        has just pressed a key and been told no, and the general instructions
        are not what they are looking for in that moment.
        """
        if self.complaint:
            text, color = self.complaint, config.BAD
        elif self.armed is not None:
            text, color = "press a key to bind it, Esc to cancel", config.ACCENT
        else:
            text, color = (
                "up / down  choose      Enter  rebind      Esc  back",
                config.GREY,
            )

        hint = self.small.render(text, False, color)
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))


def row_y(index: int) -> int:
    """Where a row sits, so the layout test can ask without drawing.

    Module level rather than a method for the reason `shop_panel.hint_y` is:
    the drawing and the test that checks the drawing fits have to be reading one
    source, and a helper on the instance is one the test has to build a scene to
    reach.
    """
    gap = RESET_GAP if ROWS[index] == RESET else 0
    return ROW_Y + index * ROW_H + gap
