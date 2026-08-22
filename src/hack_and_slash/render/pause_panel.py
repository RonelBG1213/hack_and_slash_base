"""The pause overlay: three rows, and what quitting keeps.

The fifth panel, and the first one that is not about the run. The other four ask
a question the run has raised -- which piece, which attribute, which path, what
have I got -- and this one asks nothing. It exists because `Esc` used to end the
fight on the first press, which is the key every other game on this shelf binds
to "pause".

**A panel, not a `Scene`**, for the reason the shop is one: scenes swap by
replacement, and a pause scene would have to hand a live `Run` back to a
`PlayScene` whose constructor builds a fresh one. It reads a `Run` and an index
and writes to nothing, like `hero_panel`.

The wash is `config.VIEWPORT_H` tall and not `INTERNAL_H`, which is what leaves
the HUD strip undimmed under every panel here. That matters *most* on this one:
"should I quit" is partly "am I about to die anyway", and the health bar is the
answer.

**One thing here can lie, and it is `kept`.** Every other string is a label. That
one is a claim about what is on disk, so it is derived from the `Run` and pinned
against an actual `save.read()` rather than written down -- see
`test_the_quit_row_promises_the_stage_the_save_would_restore`.
"""

from __future__ import annotations

import pygame

from .. import config

#: The rows, in order, as `(id, label)`. Branched on by id so a relabelling is
#: never a rewiring -- the `scenes/options.py` contract, and the scene indexes
#: this same tuple so a row and its behaviour cannot come from two lists.
#:
#: Cursor-driven rather than digit-driven: three rows are a menu, not a shelf,
#: and `1`-`8` are spoken for by the three panels that have shelves.
ROWS = (
    ("resume", "Resume"),
    ("settings", "Settings"),
    ("quit", "Quit to menu"),
)

# --- layout, in the 384x216 internal space -----------------------------------
# Measured with the real fonts: the widest label is "Quit to menu" at 72px and
# the widest note "keeps stage 14" at 54px, so the block -- caret, label, note --
# is 150px and centres at x=117.
#
# **Anchored down the middle of the viewport rather than at TITLE_Y = 10, which
# is what the other four use.** They are dense: eight rows of gear or attributes
# fill the space they start at the top of. Three rows do not, and hugging the top
# leaves eighty pixels of dead arena under the hint, which reads as a panel that
# failed to finish drawing rather than as a quiet one.
TITLE_Y = 40
ROW_Y = 78
ROW_H = 20

CARET_X = 117
ROW_X = CARET_X + 12
NOTE_X = ROW_X + 84

#: Gap between the last row and the hint, and the ceiling the hint never passes.
GAP = 12
HINT_Y = 158

HINT = "up / down  choose     Enter  select     Esc  resume"


def row_y(index: int) -> int:
    """Where a row sits. Module level so the fit test can ask without drawing."""
    return ROW_Y + index * ROW_H


def hint_y(count: int) -> int:
    """Where the hint sits under `count` rows, clamped at `HINT_Y`.

    The `level_panel.hint_y` shape, deliberately re-stated here rather than
    imported. `hero_panel` imports that one because it is literally the same
    eight-row geometry; a three-row overlay borrowing an eight-row plinth's
    spacing would be a coincidence waiting to become a bug.
    """
    return min(HINT_Y, ROW_Y + count * ROW_H + GAP)


def kept(run) -> str:
    """What quitting keeps, as the player will read it.

    The autosave is written on the tick a room begins (`game/save.py`), and
    quitting neither writes nor deletes anything -- so what survives is that
    snapshot, and this is the only place in the game that says so out loud.

    The number is `Run.stage_number`, which counts arenas: a reward room does not
    get one of its own, so pausing in the room before stage 14 also reads
    "keeps stage 14". That is the right number -- loading returns the player to
    the room, and the room belongs to that stage. Asserted against a real
    `save.read()` rather than argued, because a promise about a file is worth
    exactly what the file says.
    """
    return f"keeps stage {run.stage_number}"


class PausePanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, run, index: int = 0) -> None:
        """The overlay. `index` defaults so a bare panel draws for the tools."""
        self._wash(surface)

        heading = self.title.render("PAUSED", False, config.ACCENT)
        surface.blit(
            heading, ((config.INTERNAL_W - heading.get_width()) // 2, TITLE_Y)
        )

        for i, (row, label) in enumerate(ROWS):
            y = row_y(i)
            selected = i == index

            surface.blit(
                self.font.render(
                    label, False, config.WHITE if selected else config.GREY
                ),
                (ROW_X, y),
            )
            if selected:
                surface.blit(
                    self.font.render(">", False, config.ACCENT), (CARET_X, y)
                )
            if row == "quit":
                # Grey, and to the right of the label rather than under the
                # title: it is a reassurance about a decision being considered,
                # not a reward for taking it.
                surface.blit(
                    self.small.render(kept(run), False, config.GREY),
                    (NOTE_X, y + 3),
                )

        hint = self.small.render(HINT, False, config.GREY)
        surface.blit(
            hint, ((config.INTERNAL_W - hint.get_width()) // 2, hint_y(len(ROWS)))
        )

    def _wash(self, surface: pygame.Surface) -> None:
        """The sheet's wash, not the result screen's.

        `(8, 8, 12, 220)` is what the three panels that stop the game use; the
        death screen's lighter `(10, 10, 14, 150)` is for glancing at what killed
        you. A pause is a full stop, and the arena behind it should recede.
        """
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((8, 8, 12, 220))
        surface.blit(wash, (0, 0))
