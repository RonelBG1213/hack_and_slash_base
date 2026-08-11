"""Pixel-fidelity check: every sprite must survive the upscale with hard edges.

The whole look of the game rests on scaling the internal surface by a whole
number with nearest-neighbour sampling. Get a smooth scale in there instead --
`pygame.transform.smoothscale`, a fractional factor, a stray `convert` on the
wrong surface -- and the art turns to mush in a way that is easy to miss on a
laptop screen and obvious on a monitor.

This renders a frame, blows it up, and fails if any edge has been blended.

    python main.py --smoke
"""

from __future__ import annotations

import pygame

from .. import config
from ..render.atlas import Atlas


def check(atlas: Atlas) -> list[str]:
    """Returns the problems found. Empty means the pipeline is clean."""
    problems: list[str] = []

    for name in config.SPRITE_ORDER:
        sprite = atlas[name]
        colors_before = _distinct_colors(sprite)

        scaled = pygame.transform.scale(
            sprite, (sprite.get_width() * 3, sprite.get_height() * 3)
        )
        colors_after = _distinct_colors(scaled)

        # A nearest-neighbour upscale invents no colours. Any new one is a
        # blend, which means something smoothed the image.
        invented = colors_after - colors_before
        if invented:
            problems.append(
                f"{name}: upscaling invented {len(invented)} colour(s) -- "
                "something in the pipeline is smoothing instead of duplicating pixels"
            )

    return problems


def _distinct_colors(surface: pygame.Surface) -> set[tuple[int, int, int, int]]:
    width, height = surface.get_size()
    return {
        tuple(surface.get_at((x, y)))
        for y in range(height)
        for x in range(width)
    }


def run() -> int:
    """Entry point for `main.py --smoke`."""
    from ..render import atlas as atlas_module

    pygame.init()
    loaded = atlas_module.load()
    problems = check(loaded)
    pygame.quit()

    if problems:
        print("pixel fidelity check FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"pixel fidelity OK -- {len(config.SPRITE_ORDER)} sprites scale with hard edges")
    return 0
