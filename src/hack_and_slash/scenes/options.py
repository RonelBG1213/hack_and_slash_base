"""The Settings screen: seven preferences, two of which open another screen.

The controls used to be printed down the side of the title screen, then down the
side of this one. They are a reference and the title screen is a decision, and a
player who wants to look up which key rolls is not a player who is choosing what
to do next -- they are already in a run, and Escape brings them here.

**They are editable now, and they left.** This module used to say that rebinding
"would be the same column with a cursor in it, and the day that lands it takes
`CONTROLS` with it rather than replacing anything here". That is what happened:
eleven actions and a reset row do not fit in a column beside the settings, so
`scenes/controls.py` is a screen and the Controls row is how you reach it. The
prediction was right about the tuple and wrong about the column.

Seven rows, and the discipline behind them is worth stating once: **three of them
change how the game presents itself, one chooses which fight, one changes what is
remembered, and two open a screen of their own. None of them changes how a fight
resolves.**
That is not an accident of what happened to be easy -- it is the line this
screen is drawn on. A difficulty row, a damage slider, a "start with more
health" toggle would each be a balance decision worn as a preference, and the
project's whole measurement culture rests on balance decisions being made in
`data/` where they can be swept.

The bindings row is that line holding rather than bending, and it is worth being
explicit about why, because it is the first row here that a player uses *during*
a fight: which key swings is not how hard the swing lands. The sim takes an
`Intent` and never learns a key was involved.

The volume row is the same line holding for the same reason the effect toggles
did while they were still here. `audio/` is fed by events the sim emits and never
reads back, and `test_audio.py` runs one seeded fight at every volume from silent
to full and demands a single answer -- so this row is safe by construction rather
than by care.

**Screenshake and Damage numbers left, and the screen got shorter.** They were
accessibility settings on the wrong screen; `scenes/accessibility.py` took them
and added three of its own. That is the Controls move for a second time, and it
is the answer to a problem this screen had been solving the other way: eight rows
at `ROW_H 16` cleared the hint line by seven pixels, and `docs/roadmap.md` priced
the next row at "a layout, not a row". Moving a related group out cost one row
net and *bought back* two pixels per row, which is four pixels of slack under the
last one: seven to eleven. See the layout note below.

**The game now has difficulty tiers, and they are still not here.** They live in
`data/difficulty.json` -- swept by `tools/balance.py --difficulty`, with the
default tier structurally pinned to the arithmetic the recorded grid was
measured against -- and they are chosen on the character select, beside the
class, which is the other decision taken once per run. That is this paragraph
being followed rather than overturned: the objection was never to difficulty, it
was to a balance decision reached through a preferences screen.

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
from ..audio import cues
from ..game import profile, save
from ..settings import SCALES, Settings
from .base import Scene
from .accessibility import AccessibilityScene
from .controls import ControlsScene

#: The rows, in order, as `(id, label)`. Branched on by id so a relabelling is
#: never a rewiring.
ROWS = (
    ("scale", "Window scale"),
    ("fullscreen", "Fullscreen"),
    ("accessibility", "Accessibility"),
    ("volume", "Sound volume"),
    ("controls", "Controls"),
    ("seed", "Run seed"),
    ("erase", "Erase saved run"),
)

#: The rows that answer with a scene rather than with a value. Two now, which is
#: what turned a special case in `_activate` into a set -- and what a third
#: would arrive through unchanged.
SCREENS = frozenset({"accessibility", "controls"})

#: The ones that are simply on or off, and are toggled by the same key that
#: activates any other row. One, since the two effect toggles moved to
#: `scenes/accessibility.py`.
#:
#: **Still a set for one member**, which is deliberate: it is what makes adding
#: a toggle one entry in `ROWS` and one name here rather than an `if` somebody
#: has to find, and the whole reason the two that left could leave without
#: touching `_activate` or `_nudge` at all.
TOGGLES = frozenset({"fullscreen"})

#: Rows that only mean anything from the title screen.
#:
#: The pause overlay made this screen reachable from inside a run, and "Erase
#: saved run" does not survive the trip: `save.delete()` is undone at the next
#: stage boundary, where `_needs_save` re-arms and the autosave writes the file
#: back, and `profile.reset()` leaves `runs_started` at zero while a run is
#: still going -- so the `record_end` at the end of it counts a win against a
#: scoreboard that never saw it begin.
#:
#: The row's own comment already contains the argument: it is "one idea --
#: 'forget that I played this'", which is not an idea that applies while you are
#: playing it.
OUT_OF_RUN_ONLY = frozenset({"erase"})


def rows(in_run: bool = False) -> tuple[tuple[str, str], ...]:
    """The rows to draw and to take keys for.

    One list, read by both, for the reason `shop_panel.rows` is one list: a row
    and the thing it does may never come from two places that can disagree about
    how many there are.
    """
    if not in_run:
        return ROWS
    return tuple(row for row in ROWS if row[0] not in OUT_OF_RUN_ONLY)

#: What each key does, as `(key, action)`. Moved here from the title screen
#: unchanged. Prose rather than key names on the right -- "dodge roll" is what
#: the player is looking for and `space` is the answer, not the question.
# --- layout, in the 384x216 internal space -----------------------------------
# One column again. The controls had the right-hand half and took it with them
# when they became a screen of their own, so the widest thing on this one is now
# the "Damage numbers" label at 95px against the "press twice" value at 61px,
# which is what sets `VALUE_X`.
#
# `ROW_H` came down from 20 when the Controls row made this seven rows: at 20
# the seventh sat at y=174 and its 13px of text crossed the hint line at 186.
# The row spacing is the dial rather than the hint's position, because the hint
# is the last line on the screen and has nowhere below it to go.
#
# It came down again, 18 to 16, when the volume row made it eight. The same
# arithmetic and the same answer: at 18 the eighth row sat at y=180 and its
# 13px crossed the hint at 186. Sixteen puts it at 166 with 7px to spare.
#
# **And it has now gone back up, 16 to 18, which is the first time this number
# has moved in that direction.** The Accessibility screen took Screenshake and
# Damage numbers with it, so seven rows: at 18 the seventh sits at y=162 and
# clears the hint by 11px, against the 7px eight rows had.
#
# That is the point worth keeping rather than the number. This screen had been
# paying for each new row by tightening, and tightening is a dial with an end --
# 16 was two pixels of slack from being a rendering fault. Moving a *group* out
# is the move that gives some back, and it is available exactly once per group
# that turns out to have been mis-filed.
#
# `test_menu.py` measures all of it against the real fonts rather than trusting
# these numbers to stay true.
TITLE_Y = 18
ROW_Y = 54
ROW_H = 18
# Shifted right by 78 when the controls left: the rows used to be the left
# column of two and are now the only one, and a block hard against the left edge
# under a centred title reads as a screen that lost something. The pair moves
# together so the gap between a label and its value is the one that was
# measured -- `LABEL_X` to the widest value's right edge is 167px, centred in
# 384.
LABEL_X = 108
VALUE_X = 214

HINT_Y = 186


class OptionsScene(Scene):
    def __init__(self, settings: Settings, on_exit, in_run: bool = False) -> None:
        #: Held, not copied. See the note in `menu._activate`.
        self.settings = settings
        self.on_exit = on_exit

        #: The rows this visit offers. Defaulted, so every existing caller --
        #: the title screen -- gets the whole list it always had.
        self.rows = rows(in_run)

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

        #: What the volume was before Enter muted it, so a second Enter can put
        #: it back. Deliberately *not* on `Settings`: a player who quits while
        #: muted has chosen to be muted, and restoring a level they last heard
        #: two sessions ago would be this screen overruling the file it writes.
        #: Zero until something is muted, which is why `_activate` falls back to
        #: the shipped default rather than trusting it.
        self._muted = 0

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
            # The only row that answers with a scene is Controls. Returned
            # rather than swallowed, because a row that opens a screen is the
            # one thing this handler could not do before.
            return self._activate()
        elif self.rows[self.index][0] == "seed":
            # Typing only reaches the seed row, so no other row has to defend
            # itself against a digit.
            self._type_seed(event)
        return None

    def _move(self, step: int) -> None:
        self.index = (self.index + step) % len(self.rows)
        # Moving off the erase row disarms it. A player who navigated away has
        # said no as clearly as one who pressed Escape.
        self.confirming = False

    def _nudge(self, step: int) -> None:
        """Left and right on the three rows that have more than two values."""
        row = self.rows[self.index][0]
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
        elif row == "volume":
            # Clamps rather than cycling, unlike scale. A dial has ends: a
            # player holding left wants silence and should get it, not full
            # volume one press later.
            self.settings.volume = max(
                0, min(cues.MAX_VOLUME, self.settings.volume + step)
            )
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

    def _activate(self) -> Optional[Scene]:
        row = self.rows[self.index][0]

        if row in SCREENS:
            # Both write the settings on their own way out, and both come back
            # through `_resume`, which brings the cursor to this row rather than
            # to the top -- a player who went to look at the keys is a player
            # who was in the middle of something here.
            #
            # Branched on the id rather than on the class, so a third screen is
            # one entry in `SCREENS` and one line in this map.
            opens = {
                "controls": ControlsScene,
                "accessibility": AccessibilityScene,
            }
            return opens[row](self.settings, self._resume)

        if row in TOGGLES:
            setattr(self.settings, row, not getattr(self.settings, row))
            self.confirming = False
            if row == "fullscreen":
                self._apply_display()
            return None

        if row == "volume":
            # Enter is mute, and it remembers. A row that only moved on left and
            # right would leave the most common thing anybody wants from a
            # volume control -- "off, now" -- as ten presses.
            if self.settings.volume > 0:
                self._muted = self.settings.volume
                self.settings.volume = 0
            else:
                self.settings.volume = self._muted or cues.DEFAULT_VOLUME
            return None

        if row == "erase":
            if not self.confirming:
                self.confirming = True
                return None
            # Both, together. They are presented as one row because they are one
            # idea -- "forget that I played this" -- and erasing the run while
            # keeping the scoreboard of it would be a strange half-answer.
            save.delete()
            profile.reset()
            self.confirming = False
            self.erased = True
        return None

    def _resume(self) -> "OptionsScene":
        """This screen again, with the cursor where it was left.

        Returned rather than rebuilt, unlike `menu._back`. That one is rebuilt
        because the menu reads the save file when it is constructed and a screen
        behind it may have deleted the run; nothing on this screen is a snapshot
        of anything, so handing back the live instance keeps the cursor, the
        erase row's state and the settings object all as they were.
        """
        return self

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

        for i, (row, label) in enumerate(self.rows):
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

        hint = self.small.render(
            "up / down  choose      left / right  change      Esc  back",
            False,
            config.GREY,
        )
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))

    def _value(self, row: str, selected: bool) -> tuple[str, tuple[int, int, int]]:
        """What to draw in the right-hand column, and in what colour."""
        if row in SCREENS:
            # Nothing. These rows open a screen rather than holding a value, and
            # a summary of eleven bindings -- or of five toggles -- in 61 pixels
            # would be a worse answer than the screen it is standing in front of.
            return "", config.GREY

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

        if row == "volume":
            # "off" rather than "0", matching the toggles above it: zero is a
            # state a player chose, not a number they are part-way through.
            if self.settings.volume <= 0:
                return "off", config.GREY
            return f"{self.settings.volume}", config.WHITE

        if row == "seed":
            return str(self.settings.seed), config.WHITE

        on = getattr(self.settings, row)
        return ("on", config.GOOD) if on else ("off", config.GREY)
