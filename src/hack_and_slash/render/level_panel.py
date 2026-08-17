"""Spending a level's points, drawn over a paused arena.

Same slot and the same reasoning as `shop_panel.py` and `job_panel.py`: the
scene decides *when* this is on screen, this decides what it looks like, and
neither holds the other's details.

Reads a `Run` and never writes to one. Spending is `progression.spend`, called
by the scene when a key arrives, so the panel cannot get out of step with what a
keypress actually does -- it does none of it.

Seven rows on keys 1-7, and unlike the shop this panel can be opened repeatedly
until the points run out. It closes on Enter with points still unspent, which is
deliberate: banking them for a boss is a decision worth being able to make, and
`Run.unspent_points` carries between stages so nothing is lost by declining.

That is the one place this differs from the promotion panel, which has no exit
key at all. The difference is recoverability -- a level held back can be spent
later, where a fork declined by habit would throw away a run.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game import progression
from ..game.attributes import PER_MILLE, REGEN_SCALE

#: Keys 1..7, in `progression.SPENDABLE` order -- which is the order the fields
#: are declared on `Attributes`. The row a player reads and the key they press
#: are the same digit.
ROW_KEYS = (
    pygame.K_1,
    pygame.K_2,
    pygame.K_3,
    pygame.K_4,
    pygame.K_5,
    pygame.K_6,
    pygame.K_7,
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
    "regen": "Health regen",
}

TITLE_Y = 10
SUBTITLE_Y = 28

#: Seven rows at 18px from y=46 ends at 172, and the viewport is 188 tall -- so
#: the hint below clears the HUD. Drafted at ROW_H 22 and the last row sat under
#: the health bar.
ROW_Y = 46
ROW_H = 18
HINT_Y = 174

LEFT = 40
VALUE_X = 210
GAIN_X = 300


class LevelPanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, run) -> None:
        self._wash(surface)

        heading = self.title.render(f"LEVEL {run.hero_level}", False, config.ACCENT)
        surface.blit(heading, ((config.INTERNAL_W - heading.get_width()) // 2, TITLE_Y))

        points = run.unspent_points
        sub = self.small.render(
            f"{points} point{'' if points == 1 else 's'} to spend", False, config.GREY
        )
        surface.blit(sub, ((config.INTERNAL_W - sub.get_width()) // 2, SUBTITLE_Y))

        table = progression.table()
        for index, name in enumerate(progression.SPENDABLE):
            self._row(surface, run, table, index, name, affordable=points > 0)

        hint = self.small.render(
            "1-7 to spend    Enter to keep the rest", False, config.GREY
        )
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))

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
        """A stored integer as the thing a player thinks they are buying.

        The internals are per-mille and hundredths-per-tick because integers
        replay exactly and floats accumulate -- but nobody reads "150 per mille"
        as fifteen percent, so the conversion happens here, at the edge, and
        nowhere in the arithmetic.
        """
        if name in ("crit_chance", "evasion"):
            return f"{value * 100 / PER_MILLE:g}%"
        if name == "crit_damage":
            return f"{value * 100 / PER_MILLE:g}%"
        if name == "regen":
            return f"{value / REGEN_SCALE:g}/tick"
        return str(value)
