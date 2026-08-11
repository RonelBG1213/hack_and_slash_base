"""The bottom strip: health, the dodge pip, and how many are left.

Three numbers, because those are the three a player acts on. Health decides
whether to press or disengage, the dodge pip decides whether the next telegraph
is survivable, and the count is the only sense of progress a single arena gives.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game.entities import Entity
from ..game.world import World

BAR_X = 8
BAR_Y_OFFSET = 18
BAR_W = 120
BAR_H = 8

#: Below this fraction the bar turns and starts pulsing. A number you have to
#: read is a number you read too late.
DANGER = 0.3


class Hud:
    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, world: World, tick: int) -> None:
        top = config.INTERNAL_H - config.HUD_H
        pygame.draw.rect(surface, config.PANEL, (0, top, config.INTERNAL_W, config.HUD_H))
        pygame.draw.line(
            surface, config.DARK, (0, top), (config.INTERNAL_W, top)
        )

        hero = world.hero
        if hero is not None:
            self._draw_health(surface, hero, top, tick)
            self._draw_dodge(surface, hero, top)

        self._draw_remaining(surface, world, top)

    # --- health --------------------------------------------------------------
    def _draw_health(
        self, surface: pygame.Surface, hero: Entity, top: int, tick: int
    ) -> None:
        y = top + BAR_Y_OFFSET - BAR_H
        fraction = hero.health_fraction

        pygame.draw.rect(surface, (14, 15, 20), (BAR_X - 1, y - 1, BAR_W + 2, BAR_H + 2))
        pygame.draw.rect(surface, (44, 26, 30), (BAR_X, y, BAR_W, BAR_H))

        color = config.GOOD
        if fraction <= DANGER:
            # Pulsing, not just red: at a glance in a crowded fight, motion is
            # what gets noticed.
            color = config.BAD if (tick // 12) % 2 == 0 else (240, 140, 130)
        elif fraction <= 0.6:
            color = config.ACCENT

        width = int(BAR_W * fraction)
        if width > 0:
            pygame.draw.rect(surface, color, (BAR_X, y, width, BAR_H))

        label = self.small.render(f"{hero.hp}/{hero.type.hp}", False, config.WHITE)
        surface.blit(label, (BAR_X + BAR_W + 6, y - 1))

    # --- dodge ---------------------------------------------------------------
    def _draw_dodge(self, surface: pygame.Surface, hero: Entity, top: int) -> None:
        """A pip that empties while the roll is on cooldown and fills when ready.

        The one piece of state a player checks mid-fight without wanting to
        think about it, so it is drawn as a shape rather than a number.
        """
        x = BAR_X + BAR_W + 52
        y = top + BAR_Y_OFFSET - BAR_H
        size = BAR_H

        ready = hero.dodge_cooldown <= 0
        pygame.draw.rect(surface, (14, 15, 20), (x - 1, y - 1, size + 2, size + 2))

        if ready:
            pygame.draw.rect(surface, (150, 214, 236), (x, y, size, size))
        else:
            remaining = hero.dodge_cooldown / max(1, hero.type.dodge_cooldown)
            filled = int(size * (1.0 - remaining))
            pygame.draw.rect(surface, (40, 46, 58), (x, y, size, size))
            if filled > 0:
                pygame.draw.rect(surface, (78, 118, 140), (x, y + size - filled, size, filled))

        label = self.small.render("DODGE", False, config.WHITE if ready else config.GREY)
        surface.blit(label, (x + size + 4, y - 1))

    # --- progress ------------------------------------------------------------
    def _draw_remaining(self, surface: pygame.Surface, world: World, top: int) -> None:
        left = len(world.enemies())
        text = "arena clear" if left == 0 else f"{left} left"
        label = self.font.render(text, False, config.ACCENT if left else config.GOOD)
        surface.blit(
            label, (config.INTERNAL_W - label.get_width() - 8, top + BAR_Y_OFFSET - BAR_H - 2)
        )
