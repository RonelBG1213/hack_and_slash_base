"""The run.

Three jobs, in order: turn real input into an `Intent`, feed the fixed-timestep
accumulator, and draw. The scene never reasons about combat -- it cannot, since
everything that decides a fight lives behind `sim.step`, which takes an Intent
and nothing else. It does not reason about progression either: `Run` owns what
carries between stages and when one is cleared.

Hitstop is run here rather than in the sim. On a solid connect the world simply
stops being stepped for a few frames while the renderer keeps drawing, which is
what gives a hit weight without changing a single number in the fight.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..core.campaign import Campaign
from ..core.vec2 import ZERO, Vec2
from ..game.entities import Bestiary
from ..game.intent import Intent
from ..game.run import Run, RunOutcome
from ..game.sim import Accumulator, step
from ..render.atlas import Atlas
from ..render.camera import Camera
from ..render.effects import Effects
from ..render.hud import Hud
from ..render.renderer import Renderer
from .base import Scene

MOVE_KEYS = {
    pygame.K_w: Vec2(0, -1),
    pygame.K_UP: Vec2(0, -1),
    pygame.K_s: Vec2(0, 1),
    pygame.K_DOWN: Vec2(0, 1),
    pygame.K_a: Vec2(-1, 0),
    pygame.K_LEFT: Vec2(-1, 0),
    pygame.K_d: Vec2(1, 0),
    pygame.K_RIGHT: Vec2(1, 0),
}

DODGE_KEYS = (pygame.K_SPACE, pygame.K_LSHIFT, pygame.K_RSHIFT)

#: How long the between-stage banner stays up, in frames. Long enough to read
#: what you recovered, short enough that it never feels like a loading screen --
#: the next stage is already running underneath it.
BANNER_FRAMES = 110


class PlayScene(Scene):
    def __init__(
        self,
        campaign: Campaign,
        bestiary: Bestiary,
        atlas: Atlas,
        seed: int = 0,
        on_exit=None,
        start_stage: int = 0,
    ) -> None:
        self.campaign = campaign
        self.bestiary = bestiary
        self.atlas = atlas
        self.seed = seed
        self.on_exit = on_exit
        self.start_stage = start_stage

        self.renderer = Renderer(atlas)
        self.hud = Hud()
        self.accumulator = Accumulator()
        self.effects = Effects()

        self.run = Run.start(campaign, bestiary, seed=seed, at_stage=start_stage)

        # Replaced immediately by _enter_stage, which needs the stage's real
        # size. A placeholder rather than an Optional so nothing downstream has
        # to cope with the camera briefly not existing.
        self.camera = Camera(1, 1, config.INTERNAL_W, config.VIEWPORT_H)
        self.freeze = 0
        self.banner = 0
        self._enter_stage()

        #: Dodge is edge-triggered. Held as a flag rather than read from the key
        #: state, so a tap between two frames is never swallowed -- at 60fps a
        #: press and release can both land inside one frame.
        self._dodge_pressed = False

    @property
    def world(self):
        return self.run.world

    def _enter_stage(self) -> None:
        """Point the camera at the stage now in play.

        Rebuilt rather than reused: stages are different sizes, and a camera
        still clamping to the previous stage's bounds shows the edge of the map.
        """
        self.camera = Camera(
            *self.world.level.pixel_size, config.INTERNAL_W, config.VIEWPORT_H
        )
        hero = self.world.hero
        if hero is not None:
            self.camera.snap_to(hero.pos)

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return self.on_exit() if self.on_exit else None
            if event.key == pygame.K_r:
                return self.restarted()
            if event.key in DODGE_KEYS:
                self._dodge_pressed = True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._dodge_pressed = True
        return None

    def restarted(self) -> "PlayScene":
        """A fresh run from stage one. Restarting a stage would let a player
        grind the run's hardest fight at full health, which is the tension the
        carry-over exists to create."""
        return PlayScene(
            self.campaign,
            self.bestiary,
            self.atlas,
            seed=self.seed,
            on_exit=self.on_exit,
            start_stage=self.start_stage,
        )

    def _read_intent(self) -> Intent:
        keys = pygame.key.get_pressed()

        move = ZERO
        for key, direction in MOVE_KEYS.items():
            if keys[key]:
                move = move + direction

        aim = self._aim_direction()
        attacking = pygame.mouse.get_pressed()[0] or keys[pygame.K_j]

        intent = Intent(
            move=move.clamped(1.0),
            aim=aim,
            attack=attacking,
            dodge=self._dodge_pressed,
        )
        self._dodge_pressed = False
        return intent

    def _aim_direction(self) -> Vec2:
        """From the hero toward the cursor, in world terms.

        The mouse arrives in window coordinates, so it has to come back through
        the same integer scale and letterbox the picture went out through --
        skip that and the aim is off by the size of the black bars.
        """
        hero = self.world.hero
        if hero is None:
            return ZERO

        window = pygame.display.get_surface()
        if window is None:
            return ZERO

        mx, my = pygame.mouse.get_pos()
        win_w, win_h = window.get_size()
        internal = config.window_to_internal(mx, my, win_w, win_h)

        hero_screen = self.camera.to_screen(hero.pos)
        aim = Vec2(internal[0] - hero_screen[0], internal[1] - hero_screen[1])
        # A cursor sitting exactly on the hero has no direction in it; keeping
        # the old facing is better than snapping to an arbitrary one.
        return aim.normalized() if aim.length() > 2.0 else ZERO

    # --- update --------------------------------------------------------------
    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        intent = self._read_intent()

        for _ in range(self.accumulator.ticks_for(elapsed_seconds)):
            if self.freeze > 0:
                # Frozen on a connect. The renderer keeps drawing; the world
                # simply does not advance.
                self.freeze -= 1
                continue

            step(self.world, intent)
            self.effects.feed(self.world.drain_events(), self.world.hitstop)
            if self.world.hitstop > 0:
                self.freeze = self.world.hitstop

            self.run.settle()
            if self.run.just_advanced:
                # A new stage means a new arena and new bounds; the damage
                # numbers from the last one would hang over empty floor.
                self.effects.clear()
                self._enter_stage()
                self.banner = BANNER_FRAMES
                break

        self.effects.tick()
        if self.banner > 0:
            self.banner -= 1

        hero = self.world.hero
        if hero is not None:
            self.camera.follow(hero.pos, self._aim_direction())

        return None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.LETTERBOX)

        viewport = surface.subsurface((0, 0, config.INTERNAL_W, config.VIEWPORT_H))
        self.renderer.draw(viewport, self.world, self.camera, self.effects)
        self.hud.draw(surface, self.world, self.run, self.world.tick)

        if self.banner > 0:
            self._draw_banner(surface)

        if self.run.is_over:
            self._draw_result(surface)

    def _draw_banner(self, surface: pygame.Surface) -> None:
        """Announces the stage just entered, over a fight already in progress.

        Not a pause: the arena is live behind it, so walking into the next stage
        badly positioned is a real thing that can happen.
        """
        font = pygame.font.Font(None, 26)
        small = pygame.font.Font(None, 15)

        title = font.render(
            f"STAGE {self.run.stage_number} OF {self.run.stage_count}", False, config.ACCENT
        )
        name = small.render(self.world.level.name, False, config.WHITE)

        top = 26
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, top))
        surface.blit(name, ((config.INTERNAL_W - name.get_width()) // 2, top + 22))

        if self.run.healed > 0:
            healed = small.render(f"+{self.run.healed} recovered", False, config.GOOD)
            surface.blit(
                healed, ((config.INTERNAL_W - healed.get_width()) // 2, top + 38)
            )

    def _draw_result(self, surface: pygame.Surface) -> None:
        won = self.run.outcome is RunOutcome.WON
        font = pygame.font.Font(None, 34)
        small = pygame.font.Font(None, 16)

        banner = font.render(
            "RUN COMPLETE" if won else "YOU DIED", False,
            config.GOOD if won else config.BAD,
        )
        detail = small.render(
            f"cleared all {self.run.stage_count} stages" if won
            else f"stage {self.run.stage_number} of {self.run.stage_count}",
            False, config.GREY,
        )
        hint = small.render("R for a new run    Esc for the menu", False, config.GREY)

        # A dim wash rather than a solid panel, so the arena stays visible behind
        # the result -- seeing what killed you is part of the message.
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((10, 10, 14, 150))
        surface.blit(wash, (0, 0))

        centre = config.INTERNAL_W // 2
        surface.blit(banner, (centre - banner.get_width() // 2, config.VIEWPORT_H // 2 - 32))
        surface.blit(detail, (centre - detail.get_width() // 2, config.VIEWPORT_H // 2 + 2))
        surface.blit(hint, (centre - hint.get_width() // 2, config.VIEWPORT_H // 2 + 22))
