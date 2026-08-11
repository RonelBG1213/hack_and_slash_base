"""Maps world pixels to viewport pixels, and keeps the view inside the arena.

Free of pygame on purpose, so the clamping rules can be asserted directly --
"the camera never shows past the edge of the level" is a rule worth a test, and
it is the one that otherwise gets discovered as a strip of void along one wall.

The camera follows with a lag rather than snapping. A camera locked exactly to
the hero makes a fast game feel jittery, because every dodge yanks the whole
world sideways; easing toward the target keeps the motion legible.
"""

from __future__ import annotations

from ..core.vec2 import Vec2

#: Fraction of the remaining distance closed per tick. Higher snaps harder.
#: 0.18 keeps a dodge on screen without the arena lurching after it.
FOLLOW = 0.18

#: How far ahead of the hero the view leans, in pixels of aim direction. Small:
#: enough to show a little more of where you are pointing, not so much that the
#: hero drifts off centre.
LOOK_AHEAD = 14.0


class Camera:
    def __init__(
        self, level_w: int, level_h: int, view_w: int, view_h: int
    ) -> None:
        self.view_w = view_w
        self.view_h = view_h
        self.level_w = level_w
        self.level_h = level_h
        self.x = 0.0
        self.y = 0.0

    # --- movement ------------------------------------------------------------
    def snap_to(self, target: Vec2, aim: Vec2 | None = None) -> None:
        """Jump straight to the target. For the first frame of a scene, where
        easing in from the origin would look like a camera flying across the map."""
        self.x, self.y = self._ideal(target, aim)
        self.clamp()

    def follow(self, target: Vec2, aim: Vec2 | None = None) -> None:
        ideal_x, ideal_y = self._ideal(target, aim)
        self.x += (ideal_x - self.x) * FOLLOW
        self.y += (ideal_y - self.y) * FOLLOW
        self.clamp()

    def _ideal(self, target: Vec2, aim: Vec2 | None) -> tuple[float, float]:
        lead = (aim.normalized() * LOOK_AHEAD) if aim is not None else Vec2(0.0, 0.0)
        return (
            target.x + lead.x - self.view_w / 2,
            target.y + lead.y - self.view_h / 2,
        )

    def clamp(self) -> None:
        """Keep the level filling the viewport.

        A level smaller than the viewport is centred instead, so it never drifts
        against one edge leaving a band of nothing on the other.
        """
        if self.level_w <= self.view_w:
            self.x = -(self.view_w - self.level_w) / 2
        else:
            self.x = max(0.0, min(self.x, self.level_w - self.view_w))

        if self.level_h <= self.view_h:
            self.y = -(self.view_h - self.level_h) / 2
        else:
            self.y = max(0.0, min(self.y, self.level_h - self.view_h))

    # --- conversion ----------------------------------------------------------
    def to_screen(self, pos: Vec2) -> tuple[int, int]:
        """World pixel -> viewport pixel, rounded to whole pixels.

        Rounding here and nowhere else is what keeps sprites on the pixel grid.
        A sprite blitted at a fractional offset lands on a half pixel and the
        integer upscale turns that into a visible wobble.
        """
        return (int(round(pos.x - self.x)), int(round(pos.y - self.y)))

    def to_world(self, screen_x: float, screen_y: float) -> Vec2:
        return Vec2(screen_x + self.x, screen_y + self.y)

    def visible_tiles(self, tile: int) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) tile range covering the viewport, end-exclusive.

        Only these get drawn, so a large arena costs no more per frame than a
        small one.
        """
        x0 = int(self.x // tile)
        y0 = int(self.y // tile)
        x1 = int((self.x + self.view_w) // tile) + 1
        y1 = int((self.y + self.view_h) // tile) + 1
        return (x0, y0, x1, y1)

    def is_on_screen(self, pos: Vec2, margin: float = 16.0) -> bool:
        sx, sy = pos.x - self.x, pos.y - self.y
        return -margin < sx < self.view_w + margin and -margin < sy < self.view_h + margin
