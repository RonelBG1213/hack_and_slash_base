"""The promotion, drawn over a paused arena halfway through the campaign.

Same slot and the same reasoning as `shop_panel.py`: the scene decides *when* a
thing is on screen, this decides what it looks like, and neither has to hold the
other's details.

Reads a `Run` and never writes to one. Promoting is `game.jobs.promote`, called
by the scene when a key arrives -- so the panel cannot get out of step with what
a choice actually does, because it does none of it.

What a player needs from this screen is the *difference*, not two stat blocks.
Both branches inherit the light and neutral attacks they have been using all
run, so those are not shown at all; what changes is health, the heavy and the
ultimate, and health is shown as a delta because "115" means nothing without
"you had 130".

There is no way out of this panel and so no key listed for one. That is a
change from when promotion was a capstone; `scenes/play.py` holds the reasoning.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game import jobs, skills
from .atlas import Atlas

#: Keys 1 and 2, in the order `promotions_for` returns them -- which is the order
#: `data/entities.json` lists them. The column a player reads and the key they
#: press are the same digit.
CHOICE_KEYS = (pygame.K_1, pygame.K_2)

TITLE_Y = 16
SUBTITLE_Y = 36

#: The portrait's top edge. Its framing box is drawn centred on
#: `PORTRAIT_Y + cell // 2` and is `cell + 6` tall, so at a 2x scale it occupies
#: y 55..93 -- and `NAME_Y` has to clear that, not merely follow it. Drafted at
#: 88 and the name landed inside the frame.
PORTRAIT_Y = 58
NAME_Y = 97
STAT_Y = 114
STAT_LINE_H = 14

#: Below the last stat line at 142, and clear of the HUD: the viewport is 188px
#: tall and this line is about 11.
HINT_Y = 162

#: Two columns, centred on these fractions of the 384px width. Wide enough apart
#: that the two portraits never read as one row of four things.
COLUMN_X = (108, 276)
PORTRAIT_SCALE = 2


class JobPanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, run, atlas: Atlas) -> None:
        offers = jobs.offers_for(run)
        if not offers:
            # Nothing to choose. The scene should not have opened this, but a
            # panel that draws an empty frame is better than one that indexes
            # into an empty tuple.
            return

        self._wash(surface)

        heading = self.title.render("A PATH OPENS", False, config.ACCENT)
        surface.blit(heading, ((config.INTERNAL_W - heading.get_width()) // 2, TITLE_Y))

        base = run.bestiary[run.hero_type_id]
        # Both halves counted off the campaign rather than written out, because
        # the panel used to say "nineteen stages" and "one fight left" and both
        # were wrong the moment the campaign changed length. `stage_number` is
        # the stage this panel is standing on, so the stages behind it are one
        # fewer and the stages ahead include it.
        behind = run.stage_number - 1
        ahead = run.stage_count - behind
        sub = self.small.render(
            f"{behind} stages as the {base.name}. {ahead} to go.", False, config.GREY
        )
        surface.blit(sub, ((config.INTERNAL_W - sub.get_width()) // 2, SUBTITLE_Y))

        for index, advanced in enumerate(offers[: len(COLUMN_X)]):
            self._column(surface, atlas, base, advanced, index)

        # No decline, so no key for one. See `scenes/play.py` -- with half a
        # campaign behind the fork, "stay as you are" is a run broken by habit
        # rather than a choice.
        hint = self.small.render("1-2 to choose", False, config.GREY)
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))

    def _wash(self, surface: pygame.Surface) -> None:
        """The same dim wash the shop uses, and slightly darker. The arena stays
        visible behind it, which keeps this reading as a moment in a run rather
        than as a different screen."""
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((8, 8, 12, 220))
        surface.blit(wash, (0, 0))

    def _column(self, surface: pygame.Surface, atlas: Atlas, base, advanced, index: int) -> None:
        centre = COLUMN_X[index]
        cell = config.TILE * PORTRAIT_SCALE

        sprite = pygame.transform.scale(atlas[advanced.sprite], (cell, cell))
        box = pygame.Rect(0, 0, cell + 6, cell + 6)
        box.center = (centre, PORTRAIT_Y + cell // 2)
        pygame.draw.rect(surface, config.PANEL, box)
        pygame.draw.rect(surface, config.ACCENT, box, 1)
        surface.blit(sprite, sprite.get_rect(center=box.center))

        key = self.small.render(f"{index + 1}", False, config.ACCENT)
        surface.blit(key, (box.left - 10, box.top))

        name = self.font.render(advanced.name, False, config.WHITE)
        surface.blit(name, (centre - name.get_width() // 2, NAME_Y))

        for line, (text, colour) in enumerate(self._lines(base, advanced)):
            rendered = self.small.render(text, False, colour)
            surface.blit(
                rendered,
                (centre - rendered.get_width() // 2, STAT_Y + line * STAT_LINE_H),
            )

    def _lines(self, base, advanced) -> tuple[tuple[str, tuple[int, int, int]], ...]:
        """Three lines: what changes about the body, and the two new attacks.

        Health is a delta because the absolute number cannot be read without the
        one it replaced, and it is coloured -- there is no branch here that is
        strictly better, so a player has to see which way each one traded.
        """
        delta = advanced.hp - base.hp
        if delta > 0:
            health = (f"hp {advanced.hp}  +{delta}", config.GOOD)
        elif delta < 0:
            health = (f"hp {advanced.hp}  {delta}", config.BAD)
        else:
            health = (f"hp {advanced.hp}", config.GREY)

        heavy = advanced.weapons[skills.HEAVY]
        ultimate = advanced.weapons[skills.ULTIMATE]
        return (
            health,
            (f"E  {heavy.name} {heavy.damage}", config.WHITE),
            (f"F  {ultimate.name} {self._payload(ultimate)}", config.WHITE),
        )

    @staticmethod
    def _payload(weapon) -> int:
        """Everything one use deals, fans included.

        A single Starfall bolt hits for 10 and there are nine of them; showing
        the 10 would make the Magic Archer's ultimate look like the weakest in
        the game rather than the largest.
        """
        if weapon.projectile and weapon.projectile_count > 1:
            return weapon.damage * weapon.projectile_count
        return weapon.damage
