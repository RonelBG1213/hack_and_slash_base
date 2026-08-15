"""Draws the world onto the internal 384x216 surface.

Reads state, writes pixels, changes nothing. Everything it needs to know about
what is happening -- whether a body is flashing, how far through a windup it is,
which way it is facing -- it reads off the entity, because the sim already put
it there for its own reasons.

Bodies are drawn back to front by their y position, so something standing lower
on screen covers something standing higher. It is the only depth cue a top-down
view gets, and without it bodies flicker in front of each other as they pass.
"""

from __future__ import annotations

import math

import pygame

from .. import config
from ..core.vec2 import Vec2, from_angle
from ..game.entities import ActionState, Entity
from ..game.world import World
from .atlas import Atlas
from .camera import Camera
from .effects import Effects

#: Colour a body flashes when it takes a hit.
FLASH_COLOR = (255, 255, 255)

#: The swing arc, drawn as a fan of short rays. Cheap, and it reads at 1x where
#: an outlined wedge turns to mush.
ARC_RAYS = 9
ARC_COLOR = (246, 240, 214)
ARC_FADE = (188, 176, 140)

#: The charger's telegraph: a line along the path it has committed to.
TELEGRAPH_LENGTH = 60


class Renderer:
    def __init__(self, atlas: Atlas) -> None:
        self.atlas = atlas
        self.font = pygame.font.Font(None, 13)

    def draw(
        self,
        surface: pygame.Surface,
        world: World,
        camera: Camera,
        effects: Effects,
    ) -> None:
        surface.fill(config.LETTERBOX)

        shake = effects.shake_offset()
        view = Camera(camera.level_w, camera.level_h, camera.view_w, camera.view_h)
        view.x, view.y = camera.x + shake.x, camera.y + shake.y

        self._draw_tiles(surface, world, view)
        self._draw_shadows(surface, world, view)
        # Under the bodies. A coin is never the thing you need to see, and one
        # drawn over a charger's telegraph is a coin that got somebody killed.
        self._draw_pickups(surface, world, view)
        self._draw_projectiles(surface, world, view)
        self._draw_bodies(surface, world, view)
        self._draw_swings(surface, world, view)
        self._draw_numbers(surface, effects, view)

    # --- terrain -------------------------------------------------------------
    def _draw_tiles(self, surface: pygame.Surface, world: World, camera: Camera) -> None:
        tile = world.level.tile
        floor, wall = self.atlas["floor"], self.atlas["wall"]
        x0, y0, x1, y1 = camera.visible_tiles(tile)

        for ty in range(max(0, y0), min(world.level.height, y1)):
            for tx in range(max(0, x0), min(world.level.width, x1)):
                sprite = wall if world.level.is_solid(tx, ty) else floor
                surface.blit(
                    sprite, camera.to_screen(Vec2(tx * tile, ty * tile))
                )

    def _draw_shadows(self, surface: pygame.Surface, world: World, camera: Camera) -> None:
        base = self.atlas["shadow"]
        for entity in world.entities:
            if not camera.is_on_screen(entity.pos):
                continue
            # Scaled with the body. A boss standing on a grunt-sized shadow looks
            # like it is hovering.
            scale = entity.type.sprite_scale
            shadow = (
                base if scale == 1
                else pygame.transform.scale(
                    base, (base.get_width() * scale, base.get_height() * scale)
                )
            )
            sx, sy = camera.to_screen(entity.pos)
            surface.blit(shadow, (sx - shadow.get_width() // 2, sy - shadow.get_height() // 2))

    # --- loot ----------------------------------------------------------------
    def _draw_pickups(self, surface: pygame.Surface, world: World, camera: Camera) -> None:
        """Coins and valuables on the floor.

        There is one relic sprite for all five rarities and the colour is the
        entire difference between them, which is why this is the one thing in
        the game drawn through `Atlas.shaded`. A coin is drawn as painted --
        gold is gold, and giving it a rarity colour would imply loose change had
        tiers.
        """
        for pickup in world.pickups:
            if not camera.is_on_screen(pickup.pos):
                continue
            sprite = self.atlas[pickup.sprite]
            if pickup.rarity is not None:
                sprite = self.atlas.shaded(
                    pickup.sprite, config.RARITY_COLORS[pickup.rarity.value]
                )
            sx, sy = camera.to_screen(pickup.pos)
            surface.blit(sprite, (sx - sprite.get_width() // 2, sy - sprite.get_height() // 2))

    # --- bodies --------------------------------------------------------------
    def _draw_bodies(self, surface: pygame.Surface, world: World, camera: Camera) -> None:
        # Back to front. The only depth cue a top-down view has.
        for entity in sorted(world.entities, key=lambda e: e.pos.y):
            if not camera.is_on_screen(entity.pos):
                continue
            self._draw_telegraph(surface, entity, camera)
            self._draw_body(surface, entity, camera)
            self._draw_enemy_health(surface, entity, camera)

    def _scaled(self, name: str, entity: Entity) -> pygame.Surface:
        """The sprite for a body, flashed and sized.

        `pygame.transform.scale` is nearest-neighbour and `smoothscale` is not.
        Only the former belongs here: a blurred boss would fail `main.py --smoke`,
        which is exactly the guard doing its job.
        """
        name = entity.type.sprite
        sprite = (
            self.atlas.tinted(name, FLASH_COLOR) if entity.flash > 0 else self.atlas[name]
        )
        scale = entity.type.sprite_scale
        if scale > 1:
            sprite = pygame.transform.scale(
                sprite, (sprite.get_width() * scale, sprite.get_height() * scale)
            )
        return sprite

    def _draw_body(self, surface: pygame.Surface, entity: Entity, camera: Camera) -> None:
        sprite = self._scaled(entity.type.sprite, entity)

        sx, sy = camera.to_screen(entity.pos)
        half = sprite.get_width() // 2

        if entity.state is ActionState.DODGING:
            # A roll is drawn squashed and offset, so it reads as movement with
            # weight rather than the same sprite sliding sideways.
            squashed = pygame.transform.scale(
                sprite, (sprite.get_width(), max(4, sprite.get_height() - 4))
            )
            surface.blit(squashed, (sx - half, sy - squashed.get_height() // 2 + 2))
            if entity.is_invulnerable:
                # A pale outline for the frames that cannot be hit -- the player
                # needs to see the window they are being asked to time.
                pygame.draw.rect(
                    surface, (150, 214, 236),
                    (sx - half - 1, sy - half - 1, sprite.get_width() + 2,
                     squashed.get_height() + 2), 1,
                )
            return

        surface.blit(sprite, (sx - half, sy - half))

    def _draw_telegraph(
        self, surface: pygame.Surface, entity: Entity, camera: Camera
    ) -> None:
        """The charger's tell: the line it has committed to running along.

        Drawn only during windup, and drawn as the actual committed direction
        rather than the direction of the hero, because those are different once
        the player starts moving -- and the difference is the whole enemy.
        """
        if entity.state is not ActionState.WINDUP or not entity.weapon.is_charge:
            return

        progress = entity.state_ticks / max(1, entity.weapon.windup)
        start = camera.to_screen(entity.pos)
        end = camera.to_screen(entity.pos + entity.dash_dir * TELEGRAPH_LENGTH)
        # Brightens as the charge nears release, so "how long have I got" is
        # readable at a glance.
        shade = int(80 + 150 * progress)
        pygame.draw.line(surface, (shade, shade // 3, shade // 4), start, end, 1)

    def _draw_enemy_health(
        self, surface: pygame.Surface, entity: Entity, camera: Camera
    ) -> None:
        """A pip over anything hurt but not dead. The hero's health is on the HUD."""
        if entity.is_hero or entity.health_fraction >= 1.0:
            return
        sx, sy = camera.to_screen(entity.pos)
        width = 12
        left, top = sx - width // 2, sy - 12
        pygame.draw.rect(surface, (20, 20, 26), (left, top, width, 2))
        pygame.draw.rect(
            surface, config.BAD, (left, top, int(width * entity.health_fraction), 2)
        )

    # --- attacks -------------------------------------------------------------
    def _draw_swings(self, surface: pygame.Surface, world: World, camera: Camera) -> None:
        for entity in world.entities:
            if entity.state is not ActionState.ACTIVE:
                continue
            weapon = entity.weapon
            if weapon.projectile or weapon.reach <= 0:
                continue
            if not camera.is_on_screen(entity.pos):
                continue

            origin = camera.to_screen(entity.pos)
            # Fades over the active window so the swing reads as a sweep with a
            # beginning and an end rather than a shape that blinks on and off.
            fade = entity.state_ticks / max(1, weapon.active)
            color = ARC_COLOR if fade < 0.5 else ARC_FADE

            for i in range(ARC_RAYS):
                spread = (i / (ARC_RAYS - 1) - 0.5) * weapon.arc
                tip = entity.pos + from_angle(entity.facing + spread) * weapon.reach
                pygame.draw.line(surface, color, origin, camera.to_screen(tip), 1)

    def _draw_projectiles(
        self, surface: pygame.Surface, world: World, camera: Camera
    ) -> None:
        sprite = self.atlas["arrow"]
        for shot in world.projectiles:
            if not camera.is_on_screen(shot.pos):
                continue
            # The sprite is drawn pointing right; rotate it to its heading.
            # Negated because pygame rotates anticlockwise while screen y grows
            # downward, so an un-negated angle points arrows the wrong way.
            angle = -math.degrees(shot.velocity.angle())
            turned = pygame.transform.rotate(sprite, angle)
            sx, sy = camera.to_screen(shot.pos)
            surface.blit(turned, (sx - turned.get_width() // 2, sy - turned.get_height() // 2))

    # --- damage numbers ------------------------------------------------------
    def _draw_numbers(
        self, surface: pygame.Surface, effects: Effects, camera: Camera
    ) -> None:
        for number in effects.numbers:
            pos = number.origin + number.offset()
            if not camera.is_on_screen(pos):
                continue
            label = self.font.render(number.text, False, number.color)
            label.set_alpha(number.alpha)
            sx, sy = camera.to_screen(pos)
            surface.blit(label, (sx - label.get_width() // 2, sy - label.get_height()))
