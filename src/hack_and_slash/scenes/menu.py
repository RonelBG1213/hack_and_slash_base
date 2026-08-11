"""The title screen. Start a run, read the controls, leave.

Deliberately thin. Everything it knows how to do is hand over to `PlayScene`.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..core.level import Level
from ..game.entities import Bestiary
from ..render.atlas import Atlas
from .base import Scene
from .play import PlayScene

CONTROLS = [
    ("WASD / arrows", "move"),
    ("mouse", "aim"),
    ("left click", "swing"),
    ("space / right click", "dodge roll"),
    ("R", "restart the run"),
    ("Esc", "back here"),
]


class MenuScene(Scene):
    def __init__(self, level: Level, bestiary: Bestiary, atlas: Atlas, seed: int = 0) -> None:
        self.level = level
        self.bestiary = bestiary
        self.atlas = atlas
        self.seed = seed

        self.title = pygame.font.Font(None, 44)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.tick = 0

    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return None
            return self._start()
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._start()
        return None

    def _start(self) -> PlayScene:
        return PlayScene(
            self.level,
            self.bestiary,
            self.atlas,
            seed=self.seed,
            on_exit=lambda: MenuScene(self.level, self.bestiary, self.atlas, self.seed),
        )

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("HACK AND SLASH", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, 28))

        subtitle = self.small.render(self.level.name, False, config.GREY)
        surface.blit(subtitle, ((config.INTERNAL_W - subtitle.get_width()) // 2, 66))

        left = 96
        y = 96
        for key, action in CONTROLS:
            key_label = self.small.render(key, False, config.WHITE)
            action_label = self.small.render(action, False, config.GREY)
            surface.blit(key_label, (left, y))
            surface.blit(action_label, (left + 110, y))
            y += 15

        # Blinks, because a static screen gives no sign it is waiting for you.
        if (self.tick // 30) % 2 == 0:
            prompt = self.body.render("press any key", False, config.GOOD)
            surface.blit(
                prompt,
                ((config.INTERNAL_W - prompt.get_width()) // 2, config.INTERNAL_H - 34),
            )
