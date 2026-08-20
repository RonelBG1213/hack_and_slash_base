"""The stall, drawn over a paused reward room.

Lives here rather than in `scenes/play.py` for the same reason `hud.py` does:
the scene decides *when* a thing is on screen, and this decides what it looks
like. The scene keeps the two lines that say "the stall is open" and none of the
sixty that say where the third price goes.

Two sections under one title. **Gear** on top -- three pieces rolled for this
room, at a rarity that scaled both the block and the price, gone when you walk
out. **Goods** underneath -- the five consumables that are on every shelf of
every run. One continuous run of keys across both, because a player pressing 4
is counting rows and does not know the sections are two different systems.

**A row that can never be bought again is not drawn.** Both halves used to stay
and say so -- `taken` in red on a bought piece, `sold out` in the tally column on
a good at its cap -- which was honest and was also a receipt: by act V it was
eight rows to read to find the two that still did anything. The consequence is
that the digits renumber under the player as they buy, and that is the price of
the feature rather than an oversight -- a row that is not shown cannot hold its
key. `PlayScene` swallows the frames right after a purchase for it.

Neither filter lives here. `equipment.available` and `shop.available` decide what
is on the shelf, for the same reason the offers are passed in below: what a
player can still buy is a question about a run, and this module knows pixels.

Reads a `Run` and an offer tuple, and writes to neither. Buying is
`game.equipment.buy` and `game.shop.buy`, called by the scene when a key arrives
-- so the panel cannot get out of step with what a purchase actually does,
because it does not do any of it.

**The offers are passed in rather than re-derived here.** `equipment.offers` is
deterministic, so calling it in `draw` would give the same answer -- but then the
tuple the keys index and the tuple the rows are drawn from would be two calls
that merely happen to agree, and the day one of them is given a different index
a player buys a row they cannot see.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game import equipment, loot, shop

#: Keys 1..8, spanning both sections. Three rolled pieces above five goods is
#: the tallest the panel ever gets, and it is exactly eight.
#:
#: The row number a player reads and the key they press are the same digit,
#: which is the whole reason the stock order is content rather than something
#: sorted at load -- and why `rows()` below is the single list both the drawing
#: and the scene's key handling go through.
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

TITLE_Y = 10
PURSE_Y = 28

#: Was 56/20 when the shelf was five goods and nothing else. Three gear rows on
#: top makes eight, and eight at 20px put the hint forty pixels under the HUD.
#:
#: These are `level_panel.py`'s numbers, which have already been proved to fit
#: eight rows above a 188px viewport: the last row starts at 158 and the hint at
#: 174 clears it. Drafted at 18 first, which fits the arithmetic in the fit test
#: and draws the eighth row straight through the hint -- the same trap that file
#: records.
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

#: Columns, as offsets from `LEFT`. Fixed rather than measured from the widest
#: name, so the rows line up whatever `data/loot.json` and `data/equipment.json`
#: call things.
NAME_X = 16
PRICE_X = 92
BLURB_X = 142

#: Where the rarity word and the sold-out tally are right-aligned to, and
#: therefore how much room a blurb has: about 150px between `LEFT + BLURB_X` and
#: here. The two never collide because the column is free on a gear row and the
#: tally column is free on a goods row.
#:
#: `equipment.MAX_ATTRIBUTES` is the rule that keeps a rolled blurb inside it,
#: and `shop.py` keeps its templates short for the same reason.
TALLY_RIGHT = config.INTERNAL_W - LEFT

#: What each rarity is drawn in. Anything the map does not name falls back to
#: grey rather than raising -- a tier added to `data/loot.json` should look
#: unremarkable, not crash somebody's thirtieth stage.
RARITY_COLOURS = {
    loot.Rarity.COMMON: config.GREY,
    loot.Rarity.UNCOMMON: config.GOOD,
    loot.Rarity.RARE: config.ACCENT,
    loot.Rarity.EPIC: config.GOLD,
    loot.Rarity.LEGENDARY: config.GOLD,
}


def _hint_for(count: int) -> str:
    """The line under the shelf, which now has to survive a shelf that shrinks.

    "1-8 to buy" was true while the row count was a property of the campaign. It
    is a property of what is left to buy now, and both ends of that are worth
    spelling out: "1-1 to buy" reads as a typo and "1-0 to buy" reads as a bug.

    Zero cannot happen with the shipped data -- the Poultice is uncapped -- so
    this is a branch rather than a comment explaining why it is unreachable.
    """
    if count == 0:
        return "Nothing left    Enter to press on"
    if count == 1:
        return "1 to buy    Enter to press on"
    return f"1-{count} to buy    Enter to press on"


def rows(run, offers: tuple[equipment.Offer, ...]) -> tuple[tuple[str, object], ...]:
    """Every row on the shelf, in the order the keys index them.

    **This, and nothing else, is what the panel draws and what a keypress means.**
    The scene calls it too, so a row and its key cannot come from two different
    lists -- the contract `shop.available` already carries for the goods half,
    now covering both halves.

    Tagged rather than duck-typed: an `Offer` and a `Good` are two different
    things bought through two different functions, and a caller guessing which
    it holds from the attributes it happens to have is the shape that breaks
    silently when one of them grows a `price`.
    """
    return tuple(
        [("gear", offer) for offer in equipment.available(run, offers)]
        + [("good", good) for good in shop.available(run)]
    )


class ShopPanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, run, offers=()) -> None:
        self._wash(surface)

        # Named for the room it stands in. It used to say THE ROAD BETWEEN,
        # which was written when the shop opened on all thirty-nine transitions
        # rather than in a room you gave up a fountain to reach.
        heading = self.title.render("THE STALL", False, config.ACCENT)
        surface.blit(heading, ((config.INTERNAL_W - heading.get_width()) // 2, TITLE_Y))

        purse = self.font.render(f"{run.gold}g", False, config.GOLD)
        surface.blit(purse, ((config.INTERNAL_W - purse.get_width()) // 2, PURSE_Y))

        shelf = rows(run, offers)
        for index, (kind, item) in enumerate(shelf):
            y = ROW_Y + index * ROW_H
            if kind == "gear":
                self._gear_row(surface, run, item, index, y)
            else:
                self._good_row(surface, run, item, index, y)

        hint = self.small.render(_hint_for(len(shelf)), False, config.GREY)
        surface.blit(
            hint, ((config.INTERNAL_W - hint.get_width()) // 2, hint_y(len(shelf)))
        )

    def _wash(self, surface: pygame.Surface) -> None:
        """A dim wash, not a solid panel -- the same treatment the result screen
        gets. The room stays visible behind it, which is what keeps the stall
        feeling like a pause in a run rather than a different screen."""
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((10, 10, 14, 205))
        surface.blit(wash, (0, 0))

    def _key(self, surface, index: int, y: int, live: bool) -> None:
        key = self.font.render(
            f"{index + 1}", False, config.ACCENT if live else config.GREY
        )
        surface.blit(key, (LEFT, y))

    def _gear_row(self, surface, run, offer: equipment.Offer, index: int, y: int) -> None:
        """One rolled piece, greyed out when pressing its key would do nothing.

        `equipment.can_buy` decides that, and it is the same call the scene makes
        when the key actually arrives -- so what a player is shown and what
        happens cannot disagree. It has one job left here: a piece that is merely
        unaffordable. A piece already bought is not on the shelf to grey.

        Which is why nothing asks `taken` any more. If the filter in `rows()`
        were ever bypassed the row would come back grey and unbuyable rather than
        claiming to be for sale, because `can_buy` still refuses it -- a missing
        word, not a lie.
        """
        live = equipment.can_buy(run, offer)
        colour = config.WHITE if live else config.GREY

        self._key(surface, index, y, live)

        name = self.font.render(offer.name, False, colour)
        surface.blit(name, (LEFT + NAME_X, y))

        price = self.font.render(
            f"{offer.price}g", False, config.GOLD if live else config.GREY
        )
        surface.blit(price, (LEFT + PRICE_X, y))

        blurb = self.small.render(offer.blurb, False, config.GREY)
        surface.blit(blurb, (LEFT + BLURB_X, y + 3))

        # The rarity sits where a good puts its tally. Two things never on the
        # same row, so one column serves both.
        tally = self.small.render(
            offer.rarity.value,
            False,
            RARITY_COLOURS.get(offer.rarity, config.GREY),
        )
        surface.blit(tally, (TALLY_RIGHT - tally.get_width(), y + 3))

    def _good_row(self, surface, run, good: shop.Good, index: int, y: int) -> None:
        """One line of stock, greyed out when pressing its key would do nothing.

        `shop.can_buy` decides that, and it is the same call the scene makes when
        the key actually arrives. That matters most for the Poultice, which is
        refused at full health rather than sold for nothing -- and which is now
        the only thing this greys, since a good at its cap has left the shelf.
        """
        live = shop.can_buy(run, good)
        colour = config.WHITE if live else config.GREY

        self._key(surface, index, y, live)

        name = self.font.render(good.name, False, colour)
        surface.blit(name, (LEFT + NAME_X, y))

        price = self.font.render(
            f"{good.price}g", False, config.GOLD if live else config.GREY
        )
        surface.blit(price, (LEFT + PRICE_X, y))

        blurb = self.small.render(good.blurb, False, config.GREY)
        surface.blit(blurb, (LEFT + BLURB_X, y + 3))

        if good.limit > 0:
            # Only the capped goods say how many are left; a count beside the
            # Poultice would imply a limit it does not have.
            #
            # A count and never "sold out": the purchase that reaches the cap
            # takes the row with it, so the highest this reads is one short.
            tally = self.small.render(
                f"{shop.bought(run, good)}/{good.limit}", False, config.GREY
            )
            surface.blit(tally, (TALLY_RIGHT - tally.get_width(), y + 3))
