"""Spending a level's points, drawn over a paused arena.

Same slot and the same reasoning as `shop_panel.py` and `job_panel.py`: the
scene decides *when* this is on screen, this decides what it looks like, and
neither holds the other's details.

Reads a `Run` and never writes to one. Spending is `progression.spend`, called
by the scene when a key arrives, so the panel cannot get out of step with what a
keypress actually does -- it does none of it.

**It draws the attributes it is handed, not all eight.** A shrine rolls three of
the eight from its own stateless stream (`progression.offers`), so a point is a
decision about what is standing in front of you rather than a menu that is
identical at every shrine in the game. Handed an empty tuple it falls back to
every attribute, which is what `shrine.offers: 8` in `data/rooms.json` means and
is the rollback to the panel this used to be.

The rows can be opened repeatedly until the points run out. It closes on Enter
with points still unspent, which is deliberate: banking them for a boss is a
decision worth being able to make, and `Run.unspent_points` carries between
stages so nothing is lost by declining.

That is the one place this differs from the promotion panel, which has no exit
key at all. The difference is recoverability -- a level held back can be spent
later, where a fork declined by habit would throw away a run.
"""

from __future__ import annotations

import pygame

from .. import config
from ..core.level import RoomKind
from ..game import progression
from ..game.attributes import PER_MILLE, REGEN_SCALE

#: Keys 1..8. The row a player reads and the key they press are the same digit.
#:
#: **The digit indexes the offer, not `SPENDABLE`.** It used to index the field
#: order on `Attributes` directly, and this comment used to warn that inserting
#: an attribute rather than appending one silently moved what every digit spent.
#: That hazard is gone: `rows()` below is the one list both the drawing and the
#: scene's key handling go through, and it is whatever the shrine rolled.
#:
#: Still eight keys, because the fallback draws all eight and because
#: `shrine.offers` is a number in a data file that somebody may raise.
ROW_KEYS = (
    pygame.K_1,
    pygame.K_2,
    pygame.K_3,
    pygame.K_4,
    pygame.K_5,
    pygame.K_6,
    pygame.K_7,
    pygame.K_8,
)

#: What each attribute is called on screen. `evasion` is shown as "Dodge"
#: because that is what a player calls it -- the code cannot use that word,
#: since `dodge_ticks` and `Intent.dodge` are the roll, but a panel has no
#: other meaning to collide with.
LABELS = {
    "max_hp": "Health",
    "damage": "Damage",
    "defense": "Defense",
    "crit_chance": "Crit rate",
    "crit_damage": "Crit damage",
    "evasion": "Dodge",
    # The unit lives in the label rather than on the value, so the two panels
    # that show this attribute call it the same thing -- `game/equipment.py`
    # prints "+0.18 Regen/tick" on a stall's blurb and could not put a "/tick"
    # anywhere else. `test_equipment.py` holds the two vocabularies together.
    "regen": "Regen/tick",
    "move_speed": "Move speed",
}

TITLE_Y = 10
SUBTITLE_Y = 28

#: Eight rows at 16px from y=46 puts the last one at 158, clear of the hint at
#: 174 and of the 188-tall viewport below it. Drafted at ROW_H 22 for seven rows
#: and the last row sat under the health bar; at 18 an eighth row starts two
#: pixels above the hint and draws straight through it.
#:
#: Note the fit test measures `len(ROW_KEYS) - 1`, so it would have passed at 18
#: while the pixels overlapped -- the arithmetic below is the real constraint.
#:
#: Measured against eight even though a shrine shows three. The panel has to fit
#: the tallest version it can ever be asked to draw, not the one on screen --
#: the same argument `shop_panel.py` makes, and the reason its geometry is now
#: these three numbers.
ROW_Y = 46
ROW_H = 16
HINT_Y = 174

#: The gap between the last row and the hint line under it.
GAP = 12


def hint_y(count: int) -> int:
    """Where the hint sits under `count` rows.

    Follows the rows up rather than staying pinned at the bottom, because the
    two panels this is in are both variable now -- a shrine draws three of eight
    and a stall seven or eight -- and a hint marooned five rows below the last
    one reads as a panel that failed to finish drawing.

    **Clamped at `HINT_Y`, which is the ceiling and not the default.** At the
    tallest the arithmetic would put it under the HUD, and that number has been
    a failing test twice rather than a bug report from somebody playing act V.
    """
    return min(HINT_Y, ROW_Y + count * ROW_H + GAP)


LEFT = 40
VALUE_X = 210
GAIN_X = 300


def rows(offers: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The attribute names on the plinth, in the order the keys index them.

    **This, and nothing else, is what the panel draws and what a keypress means.**
    The scene calls it too, so a row and its key cannot come from two different
    lists -- the same contract `shop_panel.rows` carries for the stall.

    An empty offer falls back to every attribute. That is what makes this panel
    still correct on the day `xp_base` is turned on and a level is reached
    outside a reward room, where there is no shrine to have rolled anything.
    """
    return tuple(offers) if offers else progression.SPENDABLE


def format_value(name: str, value: int) -> str:
    """A stored integer as the thing a player reads.

    The internals are per-mille and hundredths-per-tick because integers replay
    exactly and floats accumulate -- but nobody reads "150 per mille" as fifteen
    percent, so the conversion happens here, at the edge, and nowhere in the
    arithmetic.

    Module-level rather than a method on the panel because there are two panels
    now: this one and `hero_panel.py`, which shows the same eight attributes as
    base-plus-earned. `game/equipment.py` already carries its own copy of these
    branches for the reason its docstring gives -- `game/` may not import
    `render/` -- and its docstring is also what warns that two vocabularies for
    eight attributes is a thing a player would have to learn twice. Two is the
    number the architecture forces; a third, inside `render/`, would be the one
    that starts disagreeing.
    """
    if name in ("crit_chance", "evasion", "move_speed"):
        return f"{value * 100 / PER_MILLE:g}%"
    if name == "crit_damage":
        return f"{value * 100 / PER_MILLE:g}%"
    if name == "regen":
        # Unit-less: "Regen/tick" is the label. See LABELS above.
        return f"{value / REGEN_SCALE:g}"
    return str(value)


class LevelPanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, run, offers: tuple[str, ...] = ()) -> None:
        self._wash(surface)

        # Named for the room when there is one. `LEVEL n` is kept for the day
        # `xp_base` is turned on and this opens on a stage boundary instead,
        # where "THE SHRINE" would be naming a room the player is not in.
        title = "THE SHRINE" if run.room is RoomKind.SHRINE else f"LEVEL {run.hero_level}"
        heading = self.title.render(title, False, config.ACCENT)
        surface.blit(heading, ((config.INTERNAL_W - heading.get_width()) // 2, TITLE_Y))

        points = run.unspent_points
        sub = self.small.render(
            f"{points} point{'' if points == 1 else 's'} to spend", False, config.GREY
        )
        surface.blit(sub, ((config.INTERNAL_W - sub.get_width()) // 2, SUBTITLE_Y))

        plinth = rows(offers)
        table = progression.table()
        for index, name in enumerate(plinth):
            self._row(surface, run, table, index, name, affordable=points > 0)

        # Counted from the rows rather than written out, so the hint cannot go
        # on saying 1-8 the day `shrine.offers` is changed.
        hint = self.small.render(
            f"1-{len(plinth)} to spend    Enter to keep the rest",
            False,
            config.GREY,
        )
        surface.blit(
            hint, ((config.INTERNAL_W - hint.get_width()) // 2, hint_y(len(plinth)))
        )

    def _wash(self, surface: pygame.Surface) -> None:
        """The same dim wash the other two panels use. The arena stays visible,
        which keeps this reading as a moment in a run rather than a screen."""
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((8, 8, 12, 220))
        surface.blit(wash, (0, 0))

    def _row(self, surface, run, table, index: int, name: str, affordable: bool) -> None:
        y = ROW_Y + index * ROW_H
        colour = config.WHITE if affordable else config.GREY

        key = self.small.render(f"{index + 1}", False, config.ACCENT if affordable else config.GREY)
        surface.blit(key, (LEFT - 14, y + 2))

        label = self.font.render(LABELS[name], False, colour)
        surface.blit(label, (LEFT, y))

        current = self.small.render(
            self._format(name, getattr(run.earned, name)), False, config.GREY
        )
        surface.blit(current, (VALUE_X, y + 2))

        gain = self.small.render(
            f"+{self._format(name, table.points[name])}", False, config.GOOD if affordable else config.GREY
        )
        surface.blit(gain, (GAIN_X, y + 2))

    @staticmethod
    def _format(name: str, value: int) -> str:
        """Kept as a method because this panel's rows read better through it."""
        return format_value(name, value)
