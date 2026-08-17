"""Achievements -- a stub, and honest about being one.

There are no achievements. What there is is `game/profile.py`: four counters the
run layer already knew and now writes down. This screen draws them and says
plainly that nothing has been defined yet.

The alternative was a screen full of invented achievements with no rules behind
them, which is worse than an empty one in a specific way this project cares
about: it would look finished. A row saying "Slay 100 Goblins -- 0/100" that
nothing anywhere counts is a lie told in the interface, and the day somebody
implements it they will be implementing it against a design they inferred from a
mockup rather than one anybody chose.

So: real numbers, no fictional rows, and a line saying which is which.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..game import profile
from .base import Scene

TITLE_Y = 22
LEAD_Y = 56
ROW_Y = 88
ROW_H = 20
LABEL_X = 76
VALUE_X = 268
HINT_Y = 186


class AchievementsScene(Scene):
    def __init__(self, on_exit) -> None:
        self.on_exit = on_exit
        self.profile = profile.load()

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.tick = 0

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        """The four counters, phrased as a player would say them.

        A property rather than a field: the profile is read when the screen is
        built, and building the rows from it here keeps the phrasing beside the
        numbers instead of in a dict that has to be kept in step with `Profile`.
        """
        return (
            ("Runs begun", str(self.profile.runs_started)),
            ("Runs completed", str(self.profile.runs_won)),
            ("Deepest stage", str(self.profile.deepest_stage or "--")),
            ("Best purse", f"{self.profile.best_gold}g" if self.profile.best_gold else "--"),
        )

    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type == pygame.KEYDOWN and event.key in (
            pygame.K_ESCAPE,
            pygame.K_RETURN,
            pygame.K_KP_ENTER,
            pygame.K_SPACE,
        ):
            # Enter leaves as well as Escape. There is nothing to choose on this
            # screen, so every key that means "done" anywhere else means it here.
            return self.on_exit() if self.on_exit else None
        return None

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("ACHIEVEMENTS", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, TITLE_Y))

        lead = self.small.render(
            "none defined yet -- this is what the game has counted so far",
            False,
            config.GREY,
        )
        surface.blit(lead, ((config.INTERNAL_W - lead.get_width()) // 2, LEAD_Y))

        for i, (label, value) in enumerate(self.rows):
            y = ROW_Y + i * ROW_H
            surface.blit(self.body.render(label, False, config.GREY), (LABEL_X, y))
            surface.blit(self.body.render(value, False, config.WHITE), (VALUE_X, y))

        hint = self.small.render("Esc  back", False, config.GREY)
        surface.blit(hint, ((config.INTERNAL_W - hint.get_width()) // 2, HINT_Y))
