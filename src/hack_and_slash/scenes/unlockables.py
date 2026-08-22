"""Unlockables -- what a lost run leaves behind, and what it does not.

This screen shipped empty, and the reason it did is worth keeping now that it is
not: unlocks were chosen to be **gameplay-affecting**, and the moment a run can
begin with anything the reference bot did not have, the recorded class-by-stage
grid stops describing the game being played.

`game/unlocks.py` is that objection answered rather than overruled. Every entry
here grants **access** -- a difficulty tier, a run modifier -- and never a
number, which the grid is indifferent to: it measures a specified class over a
specified stage and does not care how the player got the right to pick it. The
rule is enforced by the schema and not by this paragraph.

**Nothing on this screen is stored.** What is unlocked is derived from the four
counters in `game/profile.py` every time the screen opens, so there is no unlock
state to migrate, to corrupt, or to disagree with the scoreboard next door.

What is still *not* an unlock, and is worth saying here so nobody implements it
twice: the ten advanced classes. They are earned by reaching stage 21, gated by
`promotes_from`, inside a run rather than across runs.

**The run modifiers are switched on here, and that placement is deliberate.**
`scenes/options.py` is drawn on the line that nothing on it may change how a
fight resolves, so a champions row there would be a balance decision worn as a
preference -- the same argument that put the difficulty tiers on the character
select instead. The select screen has no room for a fourth line under the tiers
(its blurb already sits 6px above the prompt), and this screen has both the room
and the better claim: it is where the player just read that they earned the
thing. Escape leaves, as everywhere; Enter turns the row under the cursor on.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from .. import settings as settings_module
from ..game import profile, unlocks
from ..settings import Settings
from .base import Scene

# --- layout, in the 384x216 internal space -----------------------------------
# An entry is two rows -- the name and its state on one, the blurb under it --
# so the pitch is what decides how many fit. At `ROW_PITCH` 26 the three shipped
# entries end at 146 of 216, which leaves room for two more before they reach
# the hint. `test_menu.py` measures the widest name and state against the real
# fonts rather than trusting these numbers to stay true.
TITLE_Y = 22
ROW_Y = 62
ROW_PITCH = 26
BLURB_DY = 12
NAME_X = 40
STATE_X = 232

#: Where the empty-table message goes: centred, where a row is not. A table with
#: nothing in it is not a list of zero rows, it is a different screen.
EMPTY_Y = 92

HINT_Y = 186


class UnlockablesScene(Scene):
    def __init__(self, on_exit, settings: Optional[Settings] = None) -> None:
        self.on_exit = on_exit

        #: Held, not copied -- the arrangement `OptionsScene` and
        #: `ControlsScene` both have, so a modifier switched on here is in force
        #: for the run started immediately afterwards. Defaulted so every caller
        #: that predates the toggle, and every test, still builds a screen.
        self.settings = settings or Settings()

        #: Which row the cursor is on. Only some rows do anything when it is
        #: pressed, which is why there is no wrapping and no skipping: the
        #: cursor is for reading as much as for pressing.
        self.index = 0

        #: Read once, at open. The screen has no way to earn anything while it
        #: is up -- a run is what earns things -- so re-reading per frame would
        #: be a file read sixty times a second for a number that cannot move.
        self.profile = profile.load()
        self.table = unlocks.table()
        self.earned = unlocks.earned(self.profile, self.table)

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 15)
        self.small = pygame.font.Font(None, 14)
        self.tick = 0

    def is_switch(self, entry) -> bool:
        """Whether this row is something the player can turn on.

        A modifier that has been earned. A difficulty unlock is not a switch --
        it is picked on the character select, beside the class, where a decision
        about a run belongs.
        """
        return entry.kind is unlocks.Grant.MODIFIER and entry.id in self.earned

    def is_on(self, entry) -> bool:
        return bool(getattr(self.settings, entry.target, False))

    @property
    def rows(self) -> tuple[tuple[str, str, str, bool], ...]:
        """Every entry as `(name, state, blurb, earned)`, top to bottom.

        A property rather than a field, in `achievements.rows`' image and for
        the same reason: it keeps the phrasing beside the thing it phrases, and
        it gives a test something to assert against that is not a pixel.

        The state column says what the row *wants* while it is locked and says
        so plainly when it is not: a padlock with no rule behind it is what this
        screen refused to be when it was a stub.
        """
        return tuple(
            (entry.name, self._state(entry), entry.blurb, entry.id in self.earned)
            for entry in self.table.entries
        )

    def _state(self, entry) -> str:
        """The right-hand column: what it wants, or what it is doing.

        A switch says on or off rather than "earned", because once it is earned
        the interesting fact about it is which way it is set -- and a row that
        can be pressed has to say what pressing it did."""
        if entry.id not in self.earned:
            return entry.requires.describe()
        if self.is_switch(entry):
            return "on" if self.is_on(entry) else "off"
        return "earned"

    @property
    def is_empty(self) -> bool:
        """Whether the table offers nothing at all.

        Not a defect and not a stub: `"unlocks": []` in `data/unlocks.json` is
        the documented rollback, and a screen that crashed or drew a bare title
        on it would make the rollback something nobody dares use.
        """
        return not self.table.entries

    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return self._leave()

        if self.is_empty:
            # Nothing to move over and nothing to press, so every key that
            # means "done" still means it -- which is the screen this was
            # before there was a table, kept for the run where the table is
            # empty by choice.
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self._leave()
            return None

        if event.key in (pygame.K_UP, pygame.K_w):
            self._move(-1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._move(1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate()
        return None

    def _move(self, step: int) -> None:
        # Clamped rather than wrapping. The rows are an ordered list of things
        # to read, not a carousel, and the same argument the difficulty row
        # makes applies: there is nothing at either end worth arriving at by
        # surprise.
        self.index = max(0, min(self.index + step, len(self.table.entries) - 1))

    def _activate(self) -> None:
        """Turn the row under the cursor on or off, if it is a switch.

        A row that is not a switch does nothing at all rather than leaving the
        screen. Enter has meant "back" here since this was a stub, but it cannot
        mean both -- and of the two, leaving is the one Escape already does
        everywhere in the game.
        """
        entry = self.table.entries[self.index]
        if not self.is_switch(entry):
            return
        setattr(self.settings, entry.target, not self.is_on(entry))

    def _leave(self) -> Optional[Scene]:
        # Written on the way out, exactly as the options, controls and
        # accessibility screens write theirs -- one save per visit rather than
        # one per keypress.
        settings_module.save(self.settings)
        return self.on_exit() if self.on_exit else None

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("UNLOCKABLES", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, TITLE_Y))

        if self.is_empty:
            self._draw_empty(surface)
        else:
            self._draw_rows(surface)

        switches = any(self.is_switch(entry) for entry in self.table.entries)
        text = "up / down  choose     enter  toggle     Esc  back" if switches else "Esc  back"
        hint = self.small.render(text, False, config.GREY)
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))

    def _draw_rows(self, surface: pygame.Surface) -> None:
        switches = any(self.is_switch(entry) for entry in self.table.entries)

        for i, (name, state, blurb, earned) in enumerate(self.rows):
            y = ROW_Y + i * ROW_PITCH

            # A cursor only where there is something to press. On a table of
            # nothing but difficulty unlocks this screen is a list, and a list
            # with a highlight on it claims an interaction it does not have.
            if switches and i == self.index:
                pygame.draw.rect(
                    surface,
                    config.PANEL,
                    pygame.Rect(NAME_X - 8, y - 3, config.INTERNAL_W - 2 * NAME_X + 16, 22),
                )

            # Three colour states rather than two, the same way the menu greys a
            # row it cannot open: an earned row is white and its state accented,
            # a locked one is grey throughout so the eye can sort the column
            # without reading a word of it.
            surface.blit(
                self.body.render(name, False, config.WHITE if earned else config.GREY),
                (NAME_X, y),
            )
            surface.blit(
                self.small.render(state, False, config.GOOD if earned else config.GREY),
                (STATE_X, y + 1),
            )
            if blurb:
                surface.blit(
                    self.small.render(blurb, False, config.GREY),
                    (NAME_X, y + BLURB_DY),
                )

    def _draw_empty(self, surface: pygame.Surface) -> None:
        deepest = self.profile.deepest_stage
        lines = (
            ("nothing to unlock yet", config.WHITE),
            ("", config.GREY),
            (
                f"deepest stage reached: {deepest}" if deepest else "no run recorded yet",
                config.ACCENT if deepest else config.GREY,
            ),
        )
        for i, (text, color) in enumerate(lines):
            if not text:
                continue
            line = self.small.render(text, False, color)
            surface.blit(
                line,
                ((config.INTERNAL_W - line.get_width()) // 2, EMPTY_Y + i * 18),
            )
