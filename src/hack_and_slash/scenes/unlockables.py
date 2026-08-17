"""Unlockables -- a stub, and the one with a decision still open behind it.

Nothing is unlockable yet, and this screen says so rather than showing a grid of
padlocks with no rules behind them.

The reason it is empty is worth writing down here, because it is not "nobody got
round to it". Unlocks were chosen to be **gameplay-affecting** -- a class, a
head start, something that changes a run rather than recolouring it. That is a
coherent choice and it has a price attached: the moment a run can begin with
anything the reference bot did not have, the recorded class-by-stage balance
grid stops describing the game being played, and re-establishing it is a sweep
rather than a test.

That is the same shape as the two decisions already recorded against this
project -- teaching `autoplay` to spend gold, and teaching it to sidestep. Each
would buy a real instrument and would cost the grid's standing as a fixed
reference on the same day. None of the three is a thing to do by accident on the
way to building a menu, so this screen ships empty and the decision stays where
it belongs.

What already exists and is *not* an unlock: the ten advanced classes. They are
earned by reaching stage 21 and they are gated by `promotes_from`, inside a run
rather than across runs. Worth saying on the screen so nobody implements them
twice.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..game import profile
from .base import Scene

TITLE_Y = 22
LINE_Y = 68
LINE_H = 18
HINT_Y = 186


class UnlockablesScene(Scene):
    def __init__(self, on_exit) -> None:
        self.on_exit = on_exit
        self.profile = profile.load()

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.tick = 0

    @property
    def lines(self) -> tuple[tuple[str, tuple[int, int, int]], ...]:
        """What the screen has to say, top to bottom.

        The last line is the only one that changes, and it changes for the same
        reason the whole screen is empty: there is no unlock to report, so the
        honest thing to report is progress toward the campaign itself.
        """
        deepest = self.profile.deepest_stage
        return (
            ("nothing to unlock yet", config.WHITE),
            ("", config.GREY),
            ("the ten advanced classes are earned inside a run,", config.GREY),
            ("at stage 21, and are not held here", config.GREY),
            ("", config.GREY),
            (
                f"deepest stage reached: {deepest}" if deepest else "no run recorded yet",
                config.ACCENT if deepest else config.GREY,
            ),
        )

    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_ESCAPE,
            pygame.K_RETURN,
            pygame.K_KP_ENTER,
            pygame.K_SPACE,
        ):
            return self.on_exit() if self.on_exit else None
        return None

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("UNLOCKABLES", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, TITLE_Y))

        for i, (text, color) in enumerate(self.lines):
            if not text:
                continue
            line = self.small.render(text, False, color)
            surface.blit(
                line,
                ((config.INTERNAL_W - line.get_width()) // 2, LINE_Y + i * LINE_H),
            )

        hint = self.small.render("Esc  back", False, config.GREY)
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))
