"""The scene contract and the shell that runs one.

A scene handles events, updates, and draws to the internal surface. It never
touches the window: scaling, letterboxing and the frame clock belong to `App`,
so a scene cannot accidentally depend on the size of the display.

Scenes swap by returning a new one from `update`. Returning None means "carry on".
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config


class Scene:
    def handle_event(self, event: pygame.event.Event) -> Optional["Scene"]:
        return None

    def update(self, elapsed_seconds: float) -> Optional["Scene"]:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        raise NotImplementedError


class App:
    """Window, clock, and the integer upscale from the internal surface.

    Everything is drawn at 384x216 and blown up by a whole number. Fractional
    scaling is what makes pixel art look smeared, so the window gets black bars
    rather than a stretched picture.
    """

    def __init__(self, scene: Scene, caption: str = config.CAPTION) -> None:
        pygame.init()
        pygame.display.set_caption(caption)
        self.window = pygame.display.set_mode(
            (config.WINDOW_W, config.WINDOW_H), pygame.RESIZABLE
        )
        self.surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
        self.clock = pygame.time.Clock()
        self.scene = scene
        self.running = True

    def run(self) -> None:
        while self.running:
            elapsed = self.clock.tick(config.FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
                replacement = self.scene.handle_event(event)
                if replacement is not None:
                    self.scene = replacement

            if not self.running:
                break

            replacement = self.scene.update(elapsed)
            if replacement is not None:
                self.scene = replacement

            self.scene.draw(self.surface)
            self._present()

        pygame.quit()

    def _present(self) -> None:
        width, height = self.window.get_size()
        scale = config.integer_scale(width, height)
        scaled = pygame.transform.scale(
            self.surface, (config.INTERNAL_W * scale, config.INTERNAL_H * scale)
        )
        self.window.fill(config.LETTERBOX)
        self.window.blit(scaled, config.letterbox_offset(width, height))
        pygame.display.flip()

    def quit(self) -> None:
        self.running = False
