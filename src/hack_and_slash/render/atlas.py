"""Loads `assets/sprites.png` and hands out cells by name.

Names, not indices, everywhere outside this module. `data/entities.json` says
`"sprite": "charger"`, and the cell that ends up on screen is decided here --
so reordering the atlas is a change to one tuple in config.py rather than a hunt
through the renderer for magic numbers.
"""

from __future__ import annotations

import pygame

from .. import config


class MissingAtlasError(RuntimeError):
    """The atlas has not been generated yet.

    Its own error type because the fix is a specific command, and a bare
    `FileNotFoundError` on a PNG says nothing about which one to run.
    """


class Atlas:
    def __init__(self, surface: pygame.Surface, cell: int = config.TILE) -> None:
        self.cell = cell
        self.surface = surface
        self._cells: dict[str, pygame.Surface] = {}

        columns = config.ATLAS_COLUMNS
        needed_rows = (len(config.SPRITE_ORDER) + columns - 1) // columns
        needed_columns = min(columns, len(config.SPRITE_ORDER))
        # Both dimensions: a stale atlas built before a sprite was added is
        # usually too narrow rather than too short, and slicing past the edge
        # raises a ValueError that says nothing about which command fixes it.
        if (
            surface.get_height() < needed_rows * cell
            or surface.get_width() < needed_columns * cell
        ):
            raise MissingAtlasError(
                f"{config.SPRITE_ATLAS.name} is too small for "
                f"{len(config.SPRITE_ORDER)} sprites -- it needs "
                f"{needed_columns}x{needed_rows} cells of {cell}px. "
                "Rerun `python tools/gen_art.py`"
            )

        for index, name in enumerate(config.SPRITE_ORDER):
            rect = pygame.Rect(
                (index % columns) * cell, (index // columns) * cell, cell, cell
            )
            self._cells[name] = surface.subsurface(rect).copy()

    def __getitem__(self, name: str) -> pygame.Surface:
        try:
            return self._cells[name]
        except KeyError:
            known = ", ".join(config.SPRITE_ORDER)
            raise KeyError(f"no sprite '{name}' in the atlas; it holds: {known}") from None

    def __contains__(self, name: str) -> bool:
        return name in self._cells

    def tinted(self, name: str, color: tuple[int, int, int]) -> pygame.Surface:
        """A copy flooded with `color`, keeping the sprite's own shape.

        Used for the white flash on a hit. Built on demand and not cached: it
        happens for a handful of bodies for six ticks, and a cache keyed by
        colour is more bookkeeping than the blits cost.
        """
        flashed = self[name].copy()
        flashed.fill((*color, 255), special_flags=pygame.BLEND_RGB_MAX)
        return flashed

    def shaded(self, name: str, color: tuple[int, int, int]) -> pygame.Surface:
        """A copy multiplied by `color`, keeping the sprite's shading.

        The opposite end of `tinted`, and needed for a different job: the relic
        is drawn pale so that one sprite can serve all five rarities, and MAX
        against a pale sprite gives back the pale sprite. MULT darkens toward
        the colour instead, so the highlight stays a highlight.

        Not cached, for the same reason `tinted` is not: this runs for the
        handful of things lying on the floor of one room.
        """
        shaded = self[name].copy()
        shaded.fill((*color, 255), special_flags=pygame.BLEND_RGB_MULT)
        return shaded


def load(path=None) -> Atlas:
    path = path or config.SPRITE_ATLAS
    if not path.exists():
        raise MissingAtlasError(
            f"{path} does not exist -- run `python tools/gen_art.py` to build it"
        )
    # convert_alpha needs a display; the caller sets one up first when there is
    # a window. Headless tools get the unconverted surface, which draws fine.
    surface = pygame.image.load(str(path))
    if pygame.display.get_surface() is not None:
        surface = surface.convert_alpha()
    return Atlas(surface)
