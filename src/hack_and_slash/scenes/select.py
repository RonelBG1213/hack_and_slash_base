"""Choosing a class, which is the only decision the game asks for outside a fight.

There are no upgrades and no inventory -- this screen is the whole of character
building, so it has one job: make the five readable enough that the choice is
informed rather than a coin toss. Hence the stat row and the one-line role. A
grid of five names would be a menu; this is supposed to be a decision.

The roster comes from `bestiary.hero_classes`, which is every entity whose
faction is `hero`, in the order `data/entities.json` lists them. Adding a class
is an entry in that file and a painter in `tools/gen_art.py`; nothing here needs
touching, and there is no second list that can fall out of step with the data.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..core.campaign import Campaign
from ..game.entities import Bestiary, EntityType
from ..render.atlas import Atlas
from .base import Scene
from .play import PlayScene

#: One line per class, spoken as a question the class answers. Keyed by type id
#: and looked up with a fallback, so a class added to the JSON without one shows
#: up playable rather than crashing the screen it is meant to appear on.
ROLES = {
    "knight": "slow, heavy, hard to kill",
    "rogue": "fragile and very fast",
    "archer": "fights at range",
    "magician": "one big hit, long commitment",
    "priest": "recovers twice as much between stages",
}

#: How far apart the five portraits sit, and how big they are drawn. The atlas
#: is a 16px grid, so the scale is a whole number -- a fractional one would
#: smear exactly the pixels this screen exists to show off.
PORTRAIT_SCALE = 3
COLUMN_WIDTH = 62


class CharacterSelectScene(Scene):
    def __init__(
        self,
        campaign: Campaign,
        bestiary: Bestiary,
        atlas: Atlas,
        seed: int = 0,
        on_exit=None,
        start_stage: int = 0,
        index: int = 0,
    ) -> None:
        self.campaign = campaign
        self.bestiary = bestiary
        self.atlas = atlas
        self.seed = seed
        self.on_exit = on_exit
        self.start_stage = start_stage

        self.classes: tuple[EntityType, ...] = bestiary.hero_classes
        self.index = max(0, min(index, len(self.classes) - 1))

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.tick = 0

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return self.on_exit() if self.on_exit else None
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self._move(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._move(1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self._begin()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self._column_at(event.pos)
            if hit is None:
                return None
            # Click to select, click again to commit. A single click starting
            # the run means a misclick costs a whole run rather than a keypress.
            if hit == self.index:
                return self._begin()
            self.index = hit
        return None

    def _move(self, step: int) -> None:
        # Wraps, because five items in a row have two ends and stopping dead at
        # them is worse than the one moment of surprise wrapping costs.
        self.index = (self.index + step) % len(self.classes)

    def _column_at(self, window_pos: tuple[int, int]) -> Optional[int]:
        """Which portrait a window-space click landed on, if any.

        The mouse arrives in window coordinates and everything here is laid out
        in the 384x216 internal space, so it has to come back through the same
        integer scale and letterbox the picture went out through.
        """
        window = pygame.display.get_surface()
        if window is None:
            return None

        win_w, win_h = window.get_size()
        x, y = config.window_to_internal(*window_pos, win_w, win_h)
        if not 60 <= y <= 130:
            return None

        left = self._first_column_x()
        column = (x - left + COLUMN_WIDTH // 2) // COLUMN_WIDTH
        if 0 <= column < len(self.classes):
            return int(column)
        return None

    def _first_column_x(self) -> int:
        span = COLUMN_WIDTH * (len(self.classes) - 1)
        return (config.INTERNAL_W - span) // 2

    def _begin(self) -> PlayScene:
        return PlayScene(
            self.campaign,
            self.bestiary,
            self.atlas,
            seed=self.seed,
            start_stage=self.start_stage,
            hero_type_id=self.chosen.id,
            on_exit=self.on_exit,
        )

    @property
    def chosen(self) -> EntityType:
        return self.classes[self.index]

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("CHOOSE YOUR HERO", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, 22))

        self._draw_roster(surface)
        self._draw_details(surface)

        if (self.tick // 30) % 2 == 0:
            prompt = self.small.render(
                "left / right  choose        enter  begin", False, config.GOOD
            )
            surface.blit(
                prompt,
                ((config.INTERNAL_W - prompt.get_width()) // 2, config.INTERNAL_H - 22),
            )

    def _draw_roster(self, surface: pygame.Surface) -> None:
        left = self._first_column_x()
        cell = config.TILE * PORTRAIT_SCALE

        for i, entity_type in enumerate(self.classes):
            centre_x = left + i * COLUMN_WIDTH
            selected = i == self.index

            sprite = self.atlas[entity_type.sprite]
            portrait = pygame.transform.scale(sprite, (cell, cell))
            box = pygame.Rect(0, 0, cell + 6, cell + 6)
            box.center = (centre_x, 84)

            # The unselected four are dimmed rather than shrunk. Changing size on
            # selection makes the whole row twitch as the cursor moves; changing
            # brightness leaves the layout still and reads just as clearly.
            pygame.draw.rect(surface, config.PANEL, box)
            if selected:
                pygame.draw.rect(surface, config.ACCENT, box, 1)
            else:
                portrait.set_alpha(90)

            surface.blit(portrait, portrait.get_rect(center=box.center))

            label = self.small.render(
                entity_type.name, False, config.WHITE if selected else config.GREY
            )
            surface.blit(label, (centre_x - label.get_width() // 2, 112))

    def _draw_details(self, surface: pygame.Surface) -> None:
        chosen = self.chosen
        centre = config.INTERNAL_W // 2

        role = self.body.render(
            ROLES.get(chosen.id, chosen.name), False, config.WHITE
        )
        surface.blit(role, (centre - role.get_width() // 2, 136))

        # Four numbers rather than a bar chart. Bars invite comparing lengths,
        # and these are not on comparable scales -- the weapon's name says more
        # about how a class plays than any of them.
        stats = "   ".join(
            (
                f"hp {chosen.hp}",
                f"speed {chosen.speed:g}",
                f"heal {chosen.heal_between_stages}",
                chosen.weapon.name.lower(),
            )
        )
        line = self.small.render(stats, False, config.GREY)
        surface.blit(line, (centre - line.get_width() // 2, 156))
