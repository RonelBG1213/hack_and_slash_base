"""Choosing a class, which is the first decision the game asks for.

There is no inventory and nothing to equip: the shop between stages sells three
goods and none of them changes what a class *is*. So this screen is still the
whole of character building, and it has one job -- make the five readable enough
that the choice is informed rather than a coin toss. Hence the stat row and the
one-line role. A grid of five names would be a menu; this is supposed to be a
decision, and it is the only one that cannot be revisited for the rest of a run.

The roster comes from `bestiary.hero_classes`, which is every entity whose
faction is `hero`, in the order `data/entities.json` lists them. Adding a class
is an entry in that file and a painter in `tools/gen_art.py`; nothing here needs
touching, and there is no second list that can fall out of step with the data.

**The difficulty row is here rather than on the Settings screen, and that is a
deliberate placement rather than a convenient one.** `scenes/options.py` is
drawn on the line that nothing on it may change how a fight resolves -- a
difficulty row there would be a balance decision worn as a preference. Here it
is what it actually is: a decision taken once, beside the other decision taken
once, on the screen whose whole job is to be a decision rather than a
reference. The tiers themselves live in `data/difficulty.json` where they can
be swept, which is the other half of the same argument.

Up and down move it, left and right move the roster. Two axes rather than a
focus cursor: with exactly two things to choose there is nothing a cursor would
disambiguate, and it would put a mode between the player and a screen that has
never had one.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..core.campaign import Campaign
from ..game import difficulty as difficulty_module
from ..game.entities import Bestiary, EntityType
from ..render.atlas import Atlas
from ..settings import Settings
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

#: Baseline of the difficulty row, under the class's stat line and above the
#: prompt. Named because both the drawing and the mouse band read it, and two
#: copies of a y coordinate is how a clickable row drifts off the thing it
#: claims to click.
DIFFICULTY_Y = 174


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
        settings: Optional[Settings] = None,
    ) -> None:
        self.campaign = campaign
        self.bestiary = bestiary
        self.atlas = atlas
        self.seed = seed
        self.on_exit = on_exit
        self.start_stage = start_stage

        #: Carried through rather than used here -- this screen has no opinion
        #: about screenshake. It is on the road between the menu that owns the
        #: settings and the run that reads them, and dropping them here would
        #: mean a player's toggles applied to a loaded run and not to a new one.
        self.settings = settings or Settings()

        self.classes: tuple[EntityType, ...] = bestiary.hero_classes
        self.index = max(0, min(index, len(self.classes) - 1))

        #: The tiers, and where the cursor starts. `index_of_default` rather
        #: than zero: the default tier is the one every recorded number in the
        #: project was measured against, and a screen that opened on anything
        #: else would quietly make the unmeasured tier the normal way to play.
        self.difficulties = difficulty_module.table()
        self.difficulty_index = self.difficulties.index_of_default

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
            elif event.key in (pygame.K_UP, pygame.K_w):
                self._move_difficulty(-1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._move_difficulty(1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self._begin()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._on_difficulty_row(event.pos):
                # Cycles rather than selecting a tier by its x position. The
                # row is one line of text three items long; hit-testing each
                # name would be three moving targets where one band does.
                self._move_difficulty(1)
                return None

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

    def _move_difficulty(self, step: int) -> None:
        # Clamped, where the roster wraps. Difficulty is an ordered scale and
        # wrapping one puts Relentless one keypress below Forgiving, which is
        # the single worst misread available on this screen.
        count = len(self.difficulties.tiers)
        self.difficulty_index = max(0, min(self.difficulty_index + step, count - 1))

    def _on_difficulty_row(self, window_pos: tuple[int, int]) -> bool:
        window = pygame.display.get_surface()
        if window is None:
            return False
        win_w, win_h = window.get_size()
        _, y = config.window_to_internal(*window_pos, win_w, win_h)
        return DIFFICULTY_Y - 6 <= y <= DIFFICULTY_Y + 12

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
            settings=self.settings,
            on_exit=self.on_exit,
            difficulty=self.difficulty,
        )

    @property
    def chosen(self) -> EntityType:
        return self.classes[self.index]

    @property
    def difficulty(self) -> difficulty_module.Difficulty:
        return self.difficulties.tiers[self.difficulty_index]

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
        self._draw_difficulty(surface)

        if (self.tick // 30) % 2 == 0:
            prompt = self.small.render(
                "left / right  hero     up / down  difficulty     enter  begin",
                False,
                config.GOOD,
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
                f"hp {chosen.full_hp}",
                f"speed {chosen.speed:g}",
                f"heal {chosen.heal_between_stages}",
                chosen.weapon.name.lower(),
            )
        )
        line = self.small.render(stats, False, config.GREY)
        surface.blit(line, (centre - line.get_width() // 2, 156))

    def _draw_difficulty(self, surface: pygame.Surface) -> None:
        """The tier, with the ones either side of it shown greyed.

        Drawn as a scale rather than as the selected name alone, because what
        this row is asking is *how hard*, and a single word answers that only
        for somebody who already knows what the other words are. The arrows are
        omitted at the ends, which is the whole of how the row says it is
        clamped rather than wrapping.
        """
        chosen = self.difficulty
        centre = config.INTERNAL_W // 2

        names = [tier.name for tier in self.difficulties.tiers]
        row = "   ".join(names)
        width = self.small.size(row)[0]
        x = centre - width // 2

        for i, name in enumerate(names):
            selected = i == self.difficulty_index
            label = self.small.render(
                name, False, config.WHITE if selected else config.GREY
            )
            if selected:
                # A box rather than a brighter colour alone: this row sits
                # between two other centred lines of small grey text, and
                # brightness on its own does not read as "this one is armed".
                box = pygame.Rect(x - 3, DIFFICULTY_Y - 3, label.get_width() + 6, 13)
                pygame.draw.rect(surface, config.PANEL, box)
                pygame.draw.rect(surface, config.ACCENT, box, 1)
            surface.blit(label, (x, DIFFICULTY_Y))
            x += label.get_width() + self.small.size("   ")[0]

        blurb = chosen.blurb
        if not chosen.measured:
            # Said on the screen, not only in the data file. Every other
            # unmeasured number in this project is flagged where it lives, and
            # for a tier the place it lives, as far as a player is concerned,
            # is here.
            blurb = f"{blurb}  (untuned)" if blurb else "untuned"
        if blurb:
            line = self.small.render(blurb, False, config.GREY)
            surface.blit(line, (centre - line.get_width() // 2, DIFFICULTY_Y + 14))
