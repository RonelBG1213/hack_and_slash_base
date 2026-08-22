"""The Accessibility screen: five toggles, and none of them touches a fight.

The third screen to come out of Settings, and it arrived the way Controls did
rather than the way the volume row did. `scenes/options.py` had reached eight
rows at `ROW_H 16` with seven pixels between the last one and the hint line, and
`docs/roadmap.md` priced the next row at "a layout, not a row". It was right --
but the layout it costs is *smaller* than that, because two of the eight rows
were already accessibility settings filed on the wrong screen.

**So this screen took Screenshake and Damage numbers with it.** Settings went
eight rows to seven, `ROW_H` went back up 16 to 18, and the arithmetic that had
been squeezed twice unwound once. That is the same trade Controls made and it is
worth naming: a screen that grows by moving a related group out is cheaper than
one that grows by tightening, and the second kind can only be done twice.

**Every row here is safe with a fight paused behind it**, which is the bar
`docs/limits.md#the-options-screen-is-now-reachable-mid-run` sets for anything
added from now on. Three of the five are fed by events the sim emits and never
reads back. `colourblind` picks a table of colours. `reduce_motion` is the one
that needed an argument rather than a citation, and the argument is in
`scenes/play.py` where the line it gates lives: the hitstop freeze drains
*without stepping the sim*, so skipping it removes frames in which nothing
happened. So `OUT_OF_RUN_ONLY` does not grow and this screen needs no `in_run`.

What is deliberately **not** here is recorded in `docs/limits.md`: there is no
text scale, because 384x216 has nowhere to put larger glyphs and the window
scale row already upscales every one of them by a whole number; and there is no
assist mode, because the difficulty tiers are the assist mechanism and they live
in `data/difficulty.json` where they can be swept, chosen on the character
select beside the class.

Edits a live `Settings` in place and writes it on the way out, the way both
screens it sits behind do, and for the same reason: a settings file rewritten on
every keypress is a write per arrow press.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config, settings as settings_module
from ..settings import Settings
from .base import Scene

#: The rows, in order, as `(id, label)`. Branched on by id so a relabelling is
#: never a rewiring -- the `scenes/options.py` contract, kept.
#:
#: Ordered by what a player who cannot otherwise play reaches for first, not
#: alphabetically and not by when each was written. The palette is the row that
#: makes the game readable at all; the two motion rows make it bearable; the two
#: that moved here from Settings are last because they were already reachable
#: and nobody is looking for them.
ROWS = (
    ("colourblind", "Colourblind"),
    ("reduce_flashing", "Reduce flashing"),
    ("reduce_motion", "Reduce motion"),
    ("screenshake", "Screenshake"),
    ("damage_numbers", "Damage numbers"),
)

# --- layout, in the 384x216 internal space -----------------------------------
# Five rows is not a tight screen, so the spacing is *inherited* rather than
# measured: `ROW_Y`, `ROW_H` and `HINT_Y` are the Settings screen's, which is
# what makes the two feel like one screen a player stepped further into rather
# than two that were laid out by different people.
#
# The widest label is "Damage numbers" at 95px -- the same string that sets the
# Settings screen's `VALUE_X` -- and the widest value is "off" at 20px, so the
# columns are that screen's too. `test_menu.py` measures all of it against the
# real fonts rather than trusting these numbers to stay true.
TITLE_Y = 18
ROW_Y = 54
ROW_H = 18
LABEL_X = 108
VALUE_X = 214

HINT_Y = 186


def row_y(index: int) -> int:
    """Where a row sits, so the layout test can ask without drawing.

    Module level rather than a method, for the reason `controls.row_y` is: the
    drawing and the test that checks the drawing fits have to read one source,
    and a helper on the instance is one the test has to build a scene to reach.
    """
    return ROW_Y + index * ROW_H


class AccessibilityScene(Scene):
    def __init__(self, settings: Settings, on_exit) -> None:
        #: Held, not copied -- the arrangement both screens above this one have,
        #: so a toggle is in force for the fight that is paused behind it.
        self.settings = settings
        self.on_exit = on_exit

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.index = 0

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return self._leave()

        if event.key in (pygame.K_UP, pygame.K_w):
            self.index = (self.index - 1) % len(ROWS)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.index = (self.index + 1) % len(ROWS)
        elif event.key in (
            pygame.K_RETURN,
            pygame.K_KP_ENTER,
            pygame.K_SPACE,
            pygame.K_LEFT,
            pygame.K_a,
            pygame.K_RIGHT,
            pygame.K_d,
        ):
            # Left and right toggle as well as Enter. Every row here has two
            # values, and on a row with two there is no meaningful difference
            # between "next" and "the other one" -- the same reasoning
            # `options._nudge` gives for its own toggles, and the reason this
            # screen needs no `_nudge` of its own.
            self._toggle()
        return None

    def _toggle(self) -> None:
        row = ROWS[self.index][0]
        setattr(self.settings, row, not getattr(self.settings, row))

    def _leave(self) -> Optional[Scene]:
        settings_module.save(self.settings)
        return self.on_exit() if self.on_exit else None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("ACCESSIBILITY", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, TITLE_Y))

        for i, (row, label) in enumerate(ROWS):
            y = row_y(i)
            selected = i == self.index

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

            text, color = self._value(row)
            surface.blit(self.body.render(text, False, color), (VALUE_X, y))

        hint = self.small.render(
            "up / down  choose      left / right  change      Esc  back",
            False,
            config.GREY,
        )
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))

    def _value(self, row: str) -> tuple[str, tuple[int, int, int]]:
        """What to draw in the right-hand column, and in what colour.

        **Deliberately the Settings screen's rule, unchanged**: on is green, off
        is grey. A first draft coloured a row by whether it still matched the
        shipped game, which is a more informative thing to know and was the wrong
        answer anyway -- a player walks between these two screens in one visit,
        and the same widget meaning "this is on" in one place and "you have not
        touched this" in the other is worse than either meaning on its own.

        The green also has to survive its own screen: it is `config.GOOD`, which
        is the palette entry `colourblind` moves. A player who has just switched
        that row on is looking at the one green thing this screen draws, so it is
        drawn from `config` rather than through the palette -- the menus are not
        repainted, and a row that recoloured itself as you set it would look like
        a bug rather than like a confirmation.
        """
        on = getattr(self.settings, row)
        return ("on", config.GOOD) if on else ("off", config.GREY)
