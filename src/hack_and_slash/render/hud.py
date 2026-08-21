"""The bottom strip: health, the cooldown pips, the purse, and how many are left.

Everything here is something a player acts on. Health decides whether to press
or disengage, the pips decide what is available to press *with*, the count is
the only sense of progress a single arena gives, and the purse is what the shop
between stages will let you do about all of it.

Every cooldown is drawn the same way -- a small square that empties and refills.
Four of them in a row is a lot of pips, which is exactly why none of them is a
number: a row of shapes is read at a glance in peripheral vision, and four
numbers is a thing you stop to parse in the middle of a fight.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game import skills
from ..game.entities import Entity
from ..game.world import World

BAR_X = 8
BAR_Y_OFFSET = 18
BAR_W = 120
BAR_H = 8

#: Below this fraction the bar turns and starts pulsing. A number you have to
#: read is a number you read too late.
DANGER = 0.3

#: Where the pip row starts, and how far apart the skill pips sit. The strip is
#: 384px wide with health, its readout and the stage counter already in it, so
#: this row lives in the gap between them and the spacing is what it can afford.
PIP_X = BAR_X + BAR_W + 52
SKILL_PIP_X = PIP_X + 50
SKILL_PIP_SPACING = 26

#: One letter per skill pip, and it is the key you press. A pip labelled with
#: the attack's name would be a pip you have to read; this one answers the only
#: question being asked of it, which is "can I press that yet".
SKILL_PIP_LABELS = {
    skills.NEUTRAL: "Q",
    skills.HEAVY: "E",
    skills.ULTIMATE: "F",
}

PIP_READY = (150, 214, 236)
PIP_EMPTY = (40, 46, 58)
PIP_FILLING = (78, 118, 140)

#: A buff running down, which is the opposite state to a cooldown running down
#: and has to look like it. Warm where the rest of the row is cold, and it
#: *drains* where a cooldown *fills* -- so the one pip that means "this is
#: happening right now" cannot be mistaken for the three that mean "not yet".
PIP_ACTIVE = (236, 190, 110)


class Hud:
    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(
        self, surface: pygame.Surface, world: World, run=None, tick: int = 0
    ) -> None:
        top = config.INTERNAL_H - config.HUD_H
        pygame.draw.rect(surface, config.PANEL, (0, top, config.INTERNAL_W, config.HUD_H))
        pygame.draw.line(
            surface, config.DARK, (0, top), (config.INTERNAL_W, top)
        )

        hero = world.hero
        if hero is not None:
            self._draw_health(surface, hero, top, tick)
            self._draw_dodge(surface, hero, top)
            self._draw_skills(surface, hero, top)

        self._draw_gold(surface, world, top, run)
        self._draw_remaining(surface, world, top, run)
        self._draw_boss_bar(surface, world)

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

        label = self.small.render(f"{hero.hp}/{hero.max_hp}", False, config.WHITE)
        surface.blit(label, (BAR_X + BAR_W + 6, y - 1))

    # --- cooldowns -----------------------------------------------------------
    def _draw_pip(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        remaining: int,
        total: int,
        label: str,
        active: bool = False,
    ) -> None:
        """One cooldown, as a square that refills from the bottom.

        The shape a player checks mid-fight without wanting to think about it,
        which is why it is a shape. Filling upward rather than draining means
        "full" and "ready" are the same picture, so the row is read by how much
        of it is lit rather than by comparing four part-empty boxes.

        `active` inverts both halves of that: the square drains rather than
        fills, in `PIP_ACTIVE`, because it is now counting down something the
        player *has* rather than something they are waiting for. Same pip, same
        place, opposite reading -- and the label stays lit, which is what says
        the slot is not merely unavailable.
        """
        size = BAR_H
        ready = remaining <= 0

        pygame.draw.rect(surface, (14, 15, 20), (x - 1, y - 1, size + 2, size + 2))
        if active:
            left = int(size * (remaining / max(1, total)))
            pygame.draw.rect(surface, PIP_EMPTY, (x, y, size, size))
            if left > 0:
                pygame.draw.rect(surface, PIP_ACTIVE, (x, y + size - left, size, left))
        elif ready:
            pygame.draw.rect(surface, PIP_READY, (x, y, size, size))
        else:
            filled = int(size * (1.0 - remaining / max(1, total)))
            pygame.draw.rect(surface, PIP_EMPTY, (x, y, size, size))
            if filled > 0:
                pygame.draw.rect(surface, PIP_FILLING, (x, y + size - filled, size, filled))

        text = self.small.render(
            label, False, config.WHITE if ready or active else config.GREY
        )
        surface.blit(text, (x + size + 3, y - 1))

    def _draw_dodge(self, surface: pygame.Surface, hero: Entity, top: int) -> None:
        self._draw_pip(
            surface,
            PIP_X,
            top + BAR_Y_OFFSET - BAR_H,
            hero.dodge_cooldown,
            hero.type.dodge_cooldown,
            "DODGE",
        )

    def _draw_skills(self, surface: pygame.Surface, hero: Entity, top: int) -> None:
        """One pip per skill slot, in slot order, labelled with its key.

        Light is not drawn: it has no cooldown, so its pip would be permanently
        full, which is three pixels of information repeated sixty times a second.

        Anything with fewer attacks than the four slots simply draws fewer pips.
        A `World` can be built around any entity type -- the tools and half the
        tests do it -- and a HUD that raised an IndexError on a body without an
        ultimate would break them all.

        **The buff slot borrows its own pip while it is live.** For those ticks
        the question the pip answers changes from "can I press that yet" to
        "how long have I got", which is the more urgent of the two and the only
        one worth screen space -- the slot cannot be pressed while the buff is
        running anyway, because every buff is shorter than its own cooldown.
        Free of new HUD real estate, on a 384px strip that has none.
        """
        y = top + BAR_Y_OFFSET - BAR_H
        drawn = 0
        for slot in skills.COOLDOWN_SLOTS:
            if slot >= len(hero.type.weapons):
                continue
            weapon = hero.type.weapons[slot]
            buffing = weapon.is_buff and hero.buff_ticks > 0
            self._draw_pip(
                surface,
                SKILL_PIP_X + drawn * SKILL_PIP_SPACING,
                y,
                hero.buff_ticks if buffing else hero.cooldown_on(slot),
                weapon.buff_ticks if buffing else weapon.cooldown,
                SKILL_PIP_LABELS[slot],
                active=buffing,
            )
            drawn += 1

    # --- gold ----------------------------------------------------------------
    def _draw_gold(
        self, surface: pygame.Surface, world: World, top: int, run=None
    ) -> None:
        """The purse, under the health bar.

        Read from the run when there is one, because gold banked from earlier
        stages lives there and what is loose in this arena lives on the world --
        a readout showing only one of the two is wrong half the time. A world
        being stepped on its own (a tool, half the tests) has no run to ask, and
        shows what it collected here.

        A number rather than a shape, unlike everything else in this strip. It
        is the one thing here that is not read mid-swing: you look at your purse
        between stages, when there is time to read four digits.
        """
        amount = run.gold_total if run is not None else world.gold
        label = self.small.render(f"{amount}g", False, config.GOLD)
        surface.blit(label, (BAR_X, top + BAR_Y_OFFSET + 2))

        # The level, beside the purse and only once there is one to show.
        #
        # Hidden at level 1 rather than drawn as "Lv 1", and that is not
        # tidiness: while `data/progression.json` ships `xp_base: 0` the hero is
        # level 1 for the whole game, so this strip stays pixel-identical to the
        # one that was there before the attribute layer existed -- which is the
        # same claim the arithmetic makes, made in the one place a player looks.
        # An unspent point is worth interrupting for; a permanent "Lv 1" is the
        # sort of noise this HUD is explicitly built to keep out.
        if run is not None and run.hero_level > 1:
            level = self.small.render(f"Lv {run.hero_level}", False, config.ACCENT)
            surface.blit(level, (BAR_X + label.get_width() + 8, top + BAR_Y_OFFSET + 2))
            if run.unspent_points:
                pip = self.small.render("+", False, config.GOOD)
                surface.blit(
                    pip,
                    (
                        BAR_X + label.get_width() + 10 + level.get_width(),
                        top + BAR_Y_OFFSET + 2,
                    ),
                )

    # --- progress ------------------------------------------------------------
    def _draw_remaining(
        self, surface: pygame.Surface, world: World, top: int, run=None
    ) -> None:
        left = len(world.enemies())
        text = "stage clear" if left == 0 else f"{left} left"
        label = self.font.render(text, False, config.ACCENT if left else config.GOOD)
        right = config.INTERNAL_W - 8
        surface.blit(
            label, (right - label.get_width(), top + BAR_Y_OFFSET - BAR_H - 2)
        )

        if run is not None:
            # Which stage of how many. The only sense of progress a run gives,
            # since there is nothing to collect and no map to look at.
            stage = self.small.render(
                f"stage {run.stage_number}/{run.stage_count}", False, config.GREY
            )
            surface.blit(stage, (right - stage.get_width(), top + BAR_Y_OFFSET + 2))

    def _draw_boss_bar(self, surface: pygame.Surface, world: World) -> None:
        """A bar across the top for anything big enough to deserve one.

        Driven by `sprite_scale` rather than a name or a flag: a thing drawn
        twice the size of everything else is a thing whose health the player
        needs to be able to read, and that stays true for whatever gets added
        next. A 12px pip over a boss is not a boss.
        """
        bosses = [e for e in world.enemies() if e.type.sprite_scale > 1]
        if not bosses:
            return
        boss = bosses[0]

        width = config.INTERNAL_W - 60
        left, top = 30, 8

        pygame.draw.rect(surface, (12, 12, 16), (left - 1, top - 1, width + 2, 6))
        pygame.draw.rect(surface, (52, 26, 30), (left, top, width, 4))
        filled = int(width * boss.health_fraction)
        if filled > 0:
            pygame.draw.rect(surface, config.BAD, (left, top, filled, 4))

        label = self.small.render(boss.type.name.upper(), False, config.WHITE)
        surface.blit(label, ((config.INTERNAL_W - label.get_width()) // 2, top + 6))
