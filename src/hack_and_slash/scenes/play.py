"""The fight.

Three jobs, in order: turn real input into an `Intent`, feed the fixed-timestep
accumulator, and draw. The scene never reasons about combat -- it cannot, since
everything that decides a fight lives behind `sim.step`, which takes an Intent
and nothing else.

Hitstop is run here rather than in the sim. On a solid connect the world simply
stops being stepped for a few frames while the renderer keeps drawing, which is
what gives a hit weight without changing a single number in the fight.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..core import level_io
from ..core.level import Level
from ..core.vec2 import ZERO, Vec2
from ..game.entities import Bestiary
from ..game.intent import Intent
from ..game.sim import Accumulator, step
from ..game.world import Outcome, World
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


class PlayScene(Scene):
    def __init__(
        self,
        level: Level,
        bestiary: Bestiary,
        atlas: Atlas,
        seed: int = 0,
        on_exit=None,
    ) -> None:
        self.level = level
        self.bestiary = bestiary
        self.atlas = atlas
        self.seed = seed
        self.on_exit = on_exit

        self.renderer = Renderer(atlas)
        self.hud = Hud()
        self.accumulator = Accumulator()
        self.effects = Effects()

        self.camera = Camera(
            *level.pixel_size, config.INTERNAL_W, config.VIEWPORT_H
        )
        self.freeze = 0
        self.result_ticks = 0

        self.world = World(level, bestiary, seed=seed)
        hero = self.world.hero
        if hero is not None:
            self.camera.snap_to(hero.pos)

        #: Dodge is edge-triggered. Held as a flag rather than read from the key
        #: state, so a tap between two frames is never swallowed -- at 60fps a
        #: press and release can both land inside one frame.
        self._dodge_pressed = False

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
        return PlayScene(
            self.level, self.bestiary, self.atlas, seed=self.seed, on_exit=self.on_exit
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

            if self.world.outcome is not Outcome.RUNNING:
                self.result_ticks += 1

        self.effects.tick()

        hero = self.world.hero
        if hero is not None:
            self.camera.follow(hero.pos, self._aim_direction())

        return None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.LETTERBOX)

        viewport = surface.subsurface((0, 0, config.INTERNAL_W, config.VIEWPORT_H))
        self.renderer.draw(viewport, self.world, self.camera, self.effects)
        self.hud.draw(surface, self.world, self.world.tick)

        if self.world.outcome is not Outcome.RUNNING:
            self._draw_result(surface)

    def _draw_result(self, surface: pygame.Surface) -> None:
        won = self.world.outcome is Outcome.WON
        font = pygame.font.Font(None, 34)
        small = pygame.font.Font(None, 16)

        banner = font.render(
            "ARENA CLEAR" if won else "YOU DIED", False,
            config.GOOD if won else config.BAD,
        )
        hint = small.render("R to try again    Esc for the menu", False, config.GREY)

        # A dim wash rather than a solid panel, so the arena stays visible behind
        # the result -- seeing what killed you is part of the message.
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((10, 10, 14, 150))
        surface.blit(wash, (0, 0))

        surface.blit(
            banner,
            ((config.INTERNAL_W - banner.get_width()) // 2, config.VIEWPORT_H // 2 - 26),
        )
        surface.blit(
            hint, ((config.INTERNAL_W - hint.get_width()) // 2, config.VIEWPORT_H // 2 + 12)
        )


def load_arena() -> Level:
    return level_io.load(config.LEVELS_DIR / "arena.json")
