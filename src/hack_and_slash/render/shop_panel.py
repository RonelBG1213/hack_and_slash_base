"""The shop, drawn over a paused arena between stages.

Lives here rather than in `scenes/play.py` for the same reason `hud.py` does:
the scene decides *when* a thing is on screen, and this decides what it looks
like. The scene keeps the two lines that say "the shop is open" and none of the
sixty that say where the third price goes.

Reads a `Run` and never writes to one. Buying is `game.shop.buy`, called by the
scene when a key arrives -- so the panel cannot get out of step with what a
purchase actually does, because it does not do any of it.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game import shop

#: Keys 1..5 in the order the shop stocks them. The row number a player reads
#: and the key they press are the same digit, which is the whole reason the
#: stock order is content rather than something sorted at load.
#:
#: Five keys for a shop that shows four rows for the first twenty stages. The
#: fifth is a late shelf, and both the rows and the hint line are counted from
#: `shop.available(run)` rather than assumed -- so the panel is right in both
#: halves of the campaign without knowing which half it is in.
ROW_KEYS = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5)

TITLE_Y = 26

#: Was 68/24, when the shop had three rows for the whole game, then 62/24 for
#: four. A fifth row put the hint line nineteen pixels under the HUD, so the
#: rows tightened rather than the panel starting higher -- the title has to keep
#: its air or the whole thing reads as a list rather than a shop.
#:
#: `test_the_shop_rows_and_hint_fit_above_the_hud` measures the tallest the
#: panel ever gets rather than the version that happens to be on screen, which
#: is why this has twice been a failing test rather than a bug report from
#: somebody playing act V.
ROW_Y = 56
ROW_H = 20
LEFT = 40

#: Columns, as offsets from `LEFT`. Fixed rather than measured from the widest
#: name, so the three rows line up whatever `data/loot.json` calls things.
NAME_X = 16
PRICE_X = 92
BLURB_X = 142

#: Where the sold-out tally is right-aligned to, and therefore how much room a
#: blurb has: about 150px between `LEFT + BLURB_X` and here. `game/shop.py` keeps
#: its templates short for exactly this reason.
TALLY_RIGHT = config.INTERNAL_W - LEFT


class ShopPanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, run) -> None:
        self._wash(surface)

        heading = self.title.render("THE ROAD BETWEEN", False, config.ACCENT)
        surface.blit(heading, ((config.INTERNAL_W - heading.get_width()) // 2, TITLE_Y))

        purse = self.font.render(f"{run.gold}g", False, config.GOLD)
        surface.blit(purse, ((config.INTERNAL_W - purse.get_width()) // 2, TITLE_Y + 20))

        rows = shop.available(run)
        for index, good in enumerate(rows):
            self._row(surface, run, good, index, ROW_Y + index * ROW_H)

        hint = self.small.render(
            f"1-{len(rows)} to buy    Enter to press on", False, config.GREY
        )
        surface.blit(
            hint,
            ((config.INTERNAL_W - hint.get_width()) // 2, ROW_Y + len(rows) * ROW_H + 12),
        )

    def _wash(self, surface: pygame.Surface) -> None:
        """A dim wash, not a solid panel -- the same treatment the result screen
        gets. The arena stays visible behind it, which is what keeps the shop
        feeling like a pause in a run rather than a different screen."""
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((10, 10, 14, 205))
        surface.blit(wash, (0, 0))

    def _row(self, surface: pygame.Surface, run, good: shop.Good, index: int, y: int) -> None:
        """One line of stock, greyed out when pressing its key would do nothing.

        `shop.can_buy` decides that, and it is the same call the scene makes when
        the key actually arrives -- so what a player is shown and what happens
        cannot disagree. That matters most for the Poultice, which is refused at
        full health rather than sold for nothing.
        """
        available = shop.can_buy(run, good)
        sold_out = shop.sold_out(run, good)
        color = config.WHITE if available else config.GREY

        key = self.font.render(f"{index + 1}", False, config.ACCENT if available else config.GREY)
        surface.blit(key, (LEFT, y))

        name = self.font.render(good.name, False, color)
        surface.blit(name, (LEFT + NAME_X, y))

        price = self.font.render(
            f"{good.price}g", False, config.GOLD if available else config.GREY
        )
        surface.blit(price, (LEFT + PRICE_X, y))

        blurb = self.small.render(good.blurb, False, config.GREY)
        surface.blit(blurb, (LEFT + BLURB_X, y + 3))

        if good.limit > 0:
            # Only the capped goods say how many are left; a count beside the
            # Poultice would imply a limit it does not have.
            tally = self.small.render(
                "sold out" if sold_out else f"{shop.bought(run, good)}/{good.limit}",
                False,
                config.BAD if sold_out else config.GREY,
            )
            surface.blit(tally, (TALLY_RIGHT - tally.get_width(), y + 3))
