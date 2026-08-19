"""The Settings screen: six preferences on the left, the controls on the right.

The controls used to be printed down the side of the title screen. They are a
reference and the title screen is a decision, and a player who wants to look up
which key rolls is not a player who is choosing what to do next -- they are
already in a run, and Escape brings them here. This is the screen you arrive at
knowing what you want to find out.

They are drawn, not editable. Rebinding is a real feature and this is not it; the
column would be the same column with a cursor in it, and the day that lands it
takes `CONTROLS` with it rather than replacing anything here.

Six rows, and the discipline behind them is worth stating once: **five of them
change how the game looks and the sixth changes what is remembered. None of them
changes how a fight resolves.** That is not an accident of what happened to be
easy -- it is the line this screen is drawn on. A difficulty row, a damage
slider, a "start with more health" toggle would each be a balance decision worn
as a preference, and the project's whole measurement culture rests on balance
decisions being made in `data/` where they can be swept.

The seed row is the apparent exception and is not one. Choosing a seed chooses
*which* fight; it does not change one. It exists because `--seed` is a command
line flag and not everybody who plays this has a terminal open.

The screen edits a live `Settings` in place and writes it on the way out, so a
toggle applies to the run started immediately afterwards. Scale and fullscreen
are applied on the keypress instead, because a window setting you cannot see
until you have quit and reopened the game is one you will set wrong twice.

Named `options.py` while the values live in `settings.py`, for the reason
`progression` is not `levels`: one word, one meaning, per project.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config, settings as settings_module
from ..game import profile, save
from ..settings import SCALES, Settings
from .base import Scene

#: The rows, in order, as `(id, label)`. Branched on by id so a relabelling is
#: never a rewiring.
ROWS = (
    ("scale", "Window scale"),
    ("fullscreen", "Fullscreen"),
    ("screenshake", "Screenshake"),
    ("damage_numbers", "Damage numbers"),
    ("seed", "Run seed"),
    ("erase", "Erase saved run"),
)

#: The three that are simply on or off, and are toggled by the same key that
#: activates any other row. Derived into a set rather than repeated, so adding a
#: fourth toggle is one entry in `ROWS` and one name here.
TOGGLES = frozenset({"fullscreen", "screenshake", "damage_numbers"})

#: What each key does, as `(key, action)`. Moved here from the title screen
#: unchanged. Prose rather than key names on the right -- "dodge roll" is what
#: the player is looking for and `space` is the answer, not the question.
CONTROLS = (
    ("WASD", "move"),
    ("mouse", "aim"),
    ("left click", "swing"),
    ("space", "dodge roll"),
    ("Q E F", "the other attacks"),
    ("R", "restart the run"),
    # "back here" while this list lived on the title screen, which it does not
    # any more. Escape means the menu from inside a run and it means the menu
    # from this screen, so the wording is true from wherever it is being read.
    ("Esc", "back to the menu"),
)

# --- layout, in the 384x216 internal space -----------------------------------
# Two columns now, so the preferences give up the right-hand half they had. The
# widest value is "press twice" at 61px and the widest label "Damage numbers" at
# 95px, which is what sets `VALUE_X`; `test_menu.py` measures both against the
# real fonts rather than trusting these numbers to stay true.
TITLE_Y = 18
ROW_Y = 54
ROW_H = 20
LABEL_X = 30
VALUE_X = 136

CONTROLS_X = 224
CONTROLS_ACTION_X = CONTROLS_X + 46
CONTROLS_HEAD_Y = 54
CONTROLS_Y = 70
CONTROLS_H = 15

HINT_Y = 186


class OptionsScene(Scene):
    def __init__(self, settings: Settings, on_exit) -> None:
        #: Held, not copied. See the note in `menu._activate`.
        self.settings = settings
        self.on_exit = on_exit

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.index = 0
        self.tick = 0

        #: True once the erase row has been pressed and is waiting to be pressed
        #: again. Cleared by *any* other key, including a cursor move -- see
        #: `_move`. A confirmation that survives navigation is not a
        #: confirmation, it is a trap left armed behind the player.
        self.confirming = False

        #: Set for the rest of the visit once something has been erased, so the
        #: row can say it happened. There is nothing else to show: the thing it
        #: would have described is gone.
        self.erased = False

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return self._leave()

        if event.key in (pygame.K_UP, pygame.K_w):
            self._move(-1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self._move(1)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._nudge(-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._nudge(1)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate()
        elif ROWS[self.index][0] == "seed":
            # Typing only reaches the seed row, so no other row has to defend
            # itself against a digit.
            self._type_seed(event)
        return None

    def _move(self, step: int) -> None:
        self.index = (self.index + step) % len(ROWS)
        # Moving off the erase row disarms it. A player who navigated away has
        # said no as clearly as one who pressed Escape.
        self.confirming = False

    def _nudge(self, step: int) -> None:
        """Left and right on the two rows that have more than two values."""
        row = ROWS[self.index][0]
        self.confirming = False

        if row == "scale":
            # Cycles rather than clamping, matching the character select's
            # roster. Setting an explicit scale is also what retires
            # `AUTO_SCALE` for this player -- they have now expressed an opinion.
            current = self.settings.scale
            if current in SCALES:
                nxt = SCALES[(SCALES.index(current) + step) % len(SCALES)]
            else:
                nxt = SCALES[0] if step > 0 else SCALES[-1]
            self.settings.scale = nxt
            self._apply_display()
        elif row == "seed":
            # Never negative: `Run._stage_seed` adds a per-stage offset and a
            # negative seed is a perfectly good `Random` key, but the number is
            # shown to a player and typed back in, and a minus sign in a field
            # with no minus key is a value that cannot be re-entered.
            self.settings.seed = max(0, self.settings.seed + step)
        elif row in TOGGLES:
            # Left and right toggle too. On a row with two values there is no
            # meaningful difference between "next" and "the other one", and a
            # player pressing right on a checkbox expects something to happen.
            self._activate()

    def _activate(self) -> None:
        row = ROWS[self.index][0]

        if row in TOGGLES:
            setattr(self.settings, row, not getattr(self.settings, row))
            self.confirming = False
            if row == "fullscreen":
                self._apply_display()
            return

        if row == "erase":
            if not self.confirming:
                self.confirming = True
                return
            # Both, together. They are presented as one row because they are one
            # idea -- "forget that I played this" -- and erasing the run while
            # keeping the scoreboard of it would be a strange half-answer.
            save.delete()
            profile.reset()
            self.confirming = False
            self.erased = True

    def _type_seed(self, event: pygame.event.Event) -> None:
        """Digits and backspace, on the one row that holds a number.

        Capped at nine digits. Python integers do not overflow, but the field is
        384 pixels wide and a seed long enough to run into the label is a seed
        nobody typed on purpose.
        """
        if event.key == pygame.K_BACKSPACE:
            self.settings.seed //= 10
            return

        # `getattr` rather than `event.unicode`: a real KEYDOWN always carries
        # one, but a synthesised event need not, and a scene that raises on an
        # event it was handed is a scene that cannot be driven by a test.
        typed = getattr(event, "unicode", "")
        if typed.isdigit() and self.settings.seed < 100_000_000:
            self.settings.seed = self.settings.seed * 10 + int(typed)

    def _apply_display(self) -> None:
        """Re-open the window at the size now chosen.

        Immediate rather than on exit: a scale you cannot see until you restart
        is a scale you will set wrong twice. `App._present` asks the display for
        its surface every frame rather than holding the one it opened with,
        which is what makes calling `set_mode` from here safe.
        """
        if pygame.display.get_surface() is None:
            # Headless -- a test, or the smoke check. Nothing to re-open, and
            # the setting is still recorded.
            return
        if self.settings.fullscreen:
            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode(self.settings.window_size, pygame.RESIZABLE)

    def _leave(self) -> Optional[Scene]:
        """Write the settings and go back.

        Written here rather than on every keypress. A settings file rewritten
        once per arrow press is forty writes to hold down a key, and the only
        thing it would buy is surviving a crash mid-menu.
        """
        settings_module.save(self.settings)
        return self.on_exit() if self.on_exit else None

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("SETTINGS", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, TITLE_Y))

        for i, (row, label) in enumerate(ROWS):
            y = ROW_Y + i * ROW_H
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

            text, color = self._value(row, selected)
            surface.blit(self.body.render(text, False, color), (VALUE_X, y))

        self._draw_controls(surface)

        hint = self.small.render(
            "up / down  choose      left / right  change      Esc  back",
            False,
            config.GREY,
        )
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))

    def _draw_controls(self, surface: pygame.Surface) -> None:
        """The right-hand column: a reference, headed so it is not read as a row.

        Without the heading this is six settings and then seven more lines in the
        same grid, and the first thing a player tries is pressing right on one of
        them.
        """
        head = self.small.render("CONTROLS", False, config.ACCENT)
        surface.blit(head, (CONTROLS_X, CONTROLS_HEAD_Y))

        for i, (key, action) in enumerate(CONTROLS):
            y = CONTROLS_Y + i * CONTROLS_H
            surface.blit(self.small.render(key, False, config.WHITE), (CONTROLS_X, y))
            surface.blit(
                self.small.render(action, False, config.GREY), (CONTROLS_ACTION_X, y)
            )

    def _value(self, row: str, selected: bool) -> tuple[str, tuple[int, int, int]]:
        """What to draw in the right-hand column, and in what colour."""
        if row == "erase":
            if self.confirming:
                return "press again", config.BAD
            if self.erased:
                return "erased", config.GREY
            return "press twice", config.GREY if not selected else config.WHITE

        if row == "scale":
            if self.settings.scale == settings_module.AUTO_SCALE:
                return f"auto ({config.DEFAULT_SCALE}x)", config.WHITE
            return f"{self.settings.scale}x", config.WHITE

        if row == "seed":
            return str(self.settings.seed), config.WHITE

        on = getattr(self.settings, row)
        return ("on", config.GOOD) if on else ("off", config.GREY)
