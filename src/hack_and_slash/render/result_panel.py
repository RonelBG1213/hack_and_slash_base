"""How a run ended, and what it was.

The sixth panel and the last screen of every run. It replaces four centred lines
that `scenes/play.py` drew inline -- a verdict, a depth, a purse and a hint --
with the thing the genre uses to turn a loss into another attempt.

**The wash is the panels' `(8, 8, 12, 220)`, not the lighter one this screen
used to have.** That overturns a recorded choice, and the reason it was recorded
is worth answering rather than deleting: "seeing what killed you is part of the
message". Two things changed. There is no longer anything to see -- `sim._settle`
culls the corpse on the death tick, so the lighter wash was showing an empty
arena -- and there are now nine lines of numbers on this screen, which need the
contrast. `docs/limits.md` records the overturn.

**Half of what is here can lie, so the honest half is pure and tested.**
`stats`, `earned_line` and `purchase_line` are module-level functions of a `Run`
and a `Tally`, assertable with no surface. What they may and may not claim:

* **`Gold left`, never "collected".** `Run.gold_total` is `gold + world.gold`,
  and buying subtracts from `gold` -- so on any run that spent, it is what
  remains. Gold *collected* is not derivable at all: chest gold goes straight
  into `run.gold` and its `PROP` event carries `amount=0`. The old wording was
  wrong; this does not inherit it.
* **Gear is counted, not named.** `run.purchases` keys equipment as
  `eq:{index}:{slot}` and the `Offer` carrying the name is derived per room and
  thrown away. Re-deriving it would mean rewinding `run.index` and re-running
  every stall's stream, which yields names that are wrong-but-plausible the
  moment the gear pool is edited. What the piece *did* is not lost -- it is in
  `run.earned`, which the line above prints.
* **A resumed run says so.** The tally is not in the save file, so a run picked
  up off disk has counted only this session. `Tally.partial` is what makes the
  screen admit it instead of quietly under-reporting a campaign.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game import shop
from ..game.progression import SPENDABLE
from ..game.run import RunOutcome
from .level_panel import LABELS, format_value
from .tally import Tally, format_time

# --- layout, in the 384x216 internal space -----------------------------------
# Nine lines against a 188px viewport, so this one is measured tightly. The two
# variable-length blocks -- the build and the receipt -- are the only things
# that can grow, and both are wrapped and capped at two lines. Everything else
# is fixed height.
TITLE_Y = 12
WHO_Y = 40
DEPTH_Y = 58

#: The 2x2 grid of numbers. Labels left, values right-aligned against the inner
#: edge of each column, the `hero_panel` shape.
ROW_Y = 78
ROW_H = 16
LABEL_L = 46
VALUE_L = 178
LABEL_R = 206
VALUE_R = config.INTERNAL_W - LABEL_L

#: The two wrapped blocks. Each may take a second line and no more.
EARNED_Y = 114
BOUGHT_Y = 142
WRAP_H = 12

#: Four attributes to a line: all eight in one row measures 459px against a
#: 384px screen, four is 256px at worst.
PER_LINE = 4

HINT_Y = 168


def row_y(index: int) -> int:
    """Where a grid row sits. Module level so the fit test needs no surface."""
    return ROW_Y + index * ROW_H


def hint_y() -> int:
    return HINT_Y


def verdict(run) -> tuple[str, tuple[int, int, int]]:
    won = run.outcome is RunOutcome.WON
    return ("RUN COMPLETE" if won else "YOU DIED",
            config.GOOD if won else config.BAD)


def who(run) -> str:
    """The class, and the branch it took if it took one."""
    base = run.bestiary[run.hero_type_id].name
    if not run.job_id or run.job_id == run.hero_type_id:
        return base
    # `--`, not an arrow: `pygame.font.Font(None, ...)` has no glyph for U+2192
    # and renders it as a filled box. `hero_panel` already separates a name from
    # what follows it this way.
    return f"{base}  --  {run.hero_type.name}"


def depth_line(run, tally: Tally) -> str:
    """Where it ended and how long the fighting took.

    The clock counts ticks the world was live, so it excludes hitstop and every
    panel -- and on a resumed run it excludes everything before the load, which
    is what `this session` is admitting.
    """
    won = run.outcome is RunOutcome.WON
    where = (f"all {run.stage_count} stages cleared" if won
             else f"stage {run.stage_number} of {run.stage_count}")
    clock = format_time(tally.ticks)
    if tally.partial:
        clock = f"{clock} this session"
    return f"{where}   --   {clock}"


def stats(run, tally: Tally) -> tuple[tuple[str, str], ...]:
    """The four numbers, in reading order: left column then right, top then bottom.

    `Gold left` and not "collected" -- see the module docstring. `Taken` folds
    the floor back in, because a player counting what a run cost them does not
    care whether it was a spike or a sword; the split lives on the `Tally` for
    anything that does.
    """
    return (
        ("Gold left", f"{run.gold_total:,}"),
        ("Slain", f"{tally.kills:,}"),
        ("Dealt", f"{tally.dealt:,}"),
        ("Taken", f"{tally.hurt:,}"),
    )


def earned_lines(run, lines: int = 2) -> tuple[str, ...]:
    """What the run built, as up to `lines` lines of `Label +value`.

    Only the attributes that actually moved, and through `level_panel`'s
    `LABELS` and `format_value` rather than a third copy -- that function's own
    docstring warns that a third vocabulary for the eight attributes inside
    `render/` "would be the one that starts disagreeing", because the internals
    are per-mille and hundredths-per-tick and only it knows that.
    """
    parts = [
        f"{LABELS[name]} +{format_value(name, value)}"
        for name in SPENDABLE
        if (value := getattr(run.earned, name))
    ]
    if not parts:
        return ("no attributes gained",)
    return _wrap(parts, lines)


def purchase_line(run) -> str:
    """Everything bought: goods by name, gear by the count.

    Named where a name exists and counted where one does not -- see the module
    docstring for why gear cannot be named. Never prints a raw `eq:` key, and
    never guesses.
    """
    names = {good.id: good.name for good in shop.stock()}
    parts = [
        f"{names[key]} x{count}" if count > 1 else names[key]
        for key, count in run.purchases.items()
        if key in names
    ]

    gear = sum(1 for key in run.purchases if key.startswith("eq:"))
    if gear:
        parts.append(f"{gear} piece{'s' if gear > 1 else ''} of gear")

    return "   ".join(parts) if parts else "nothing"


def unlock_line(unlocked) -> str:
    """What this run earned across runs, or empty if it earned nothing.

    Pure, like every other derivation on this screen, and it takes the unlocks
    rather than a `Profile` because *what crossed the line* is a comparison of
    two readings and only `scenes/play.py` is holding both.

    Access, never numbers -- so this line can say what it says without the
    result screen becoming a place where the balance grid is decided. See
    `game/unlocks.py`.
    """
    names = [entry.name for entry in unlocked]
    if not names:
        return ""
    return "Unlocked: " + ", ".join(names)


def _wrap(parts: list[str], lines: int = 2) -> tuple[str, ...]:
    """At most `lines` lines of `PER_LINE`, the remainder as a count.

    Capped rather than scrolled or shrunk: this screen has 188 pixels and a
    third line would land on the hint, which is the one thing that may never be
    covered -- it is how the player leaves.

    `lines` is 1 on the runs that earned an unlock, and that is a deliberate
    trade rather than a shortage: the receipt already has a "+N more" idiom for
    exactly this, and an unlock is news where a fourth purchase is a detail.
    """
    first = "   ".join(parts[:PER_LINE])
    rest = parts[PER_LINE:]
    if not rest:
        return (first,)
    if lines < 2:
        return ("   ".join(parts[:PER_LINE - 1]) + f"   +{len(parts) - PER_LINE + 1} more",)
    if len(rest) <= PER_LINE:
        return (first, "   ".join(rest))
    return (first, "   ".join(rest[:PER_LINE - 1]) + f"   +{len(rest) - PER_LINE + 1} more")


class ResultPanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 28)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(
        self,
        surface: pygame.Surface,
        run,
        tally: Tally,
        restart: str = "R",
        unlocked=(),
    ) -> None:
        """The summary. `restart` is asked for because that key is rebindable.

        `unlocked` defaults to nothing, so every caller written before unlocks
        existed -- and every test -- draws exactly the screen it drew before.
        """
        self._wash(surface)

        text, colour = verdict(run)
        self._centre(surface, self.title, text, TITLE_Y, colour)
        self._centre(surface, self.font, who(run), WHO_Y, config.WHITE)
        self._centre(surface, self.small, depth_line(run, tally), DEPTH_Y, config.GREY)

        for index, (label, value) in enumerate(stats(run, tally)):
            left = index % 2 == 0
            y = row_y(index // 2)
            surface.blit(
                self.small.render(label, False, config.GREY),
                (LABEL_L if left else LABEL_R, y + 3),
            )
            rendered = self.font.render(value, False, config.WHITE)
            right = VALUE_L if left else VALUE_R
            surface.blit(rendered, (right - rendered.get_width(), y))

        # The two wrapped blocks give up their second line to make room for the
        # unlock, and only on the runs that earned one. Measured rather than
        # assumed: at one line each the unlock sits at BOUGHT_Y + WRAP_H, which
        # is the last row that clears the hint.
        news = unlock_line(unlocked)
        budget = 1 if news else 2

        for i, line in enumerate(earned_lines(run, budget)):
            self._centre(surface, self.small, line, EARNED_Y + i * WRAP_H, config.GOOD)

        parts = purchase_line(run).split("   ")
        bought = _wrap(parts, budget) if run.purchases else ("nothing",)
        for i, line in enumerate(bought):
            self._centre(surface, self.small, line, BOUGHT_Y + i * WRAP_H, config.GREY)

        if news:
            self._centre(
                surface, self.small, news, BOUGHT_Y + WRAP_H, config.ACCENT
            )

        self._centre(
            surface,
            self.small,
            f"{restart} for a new run    Esc for the menu",
            HINT_Y,
            config.GREY,
        )

    def _centre(self, surface, font, text: str, y: int, colour) -> None:
        rendered = font.render(text, False, colour)
        surface.blit(rendered, ((config.INTERNAL_W - rendered.get_width()) // 2, y))

    def _wash(self, surface: pygame.Surface) -> None:
        """The panels' wash. See the module docstring for why it is no longer
        the lighter one this screen used to have."""
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((8, 8, 12, 220))
        surface.blit(wash, (0, 0))
