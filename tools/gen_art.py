"""Paints `assets/sprites.png`.

The art is generated, never committed. Two reasons: nothing binary goes in the
repo, and no amount of not-being-an-artist blocks the code. Replacing this with
real art means dropping in a PNG with the same cell layout -- the game reads
cells by index and does not care what is in them.

Everything here is drawn with hard edges and no anti-aliasing. A pixel-art game
scaled up by whole numbers turns any soft edge into a smear, and `main.py
--smoke` fails the build if one appears.

    python tools/gen_art.py
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# No window is needed to paint into a surface, and asking for one on a headless
# machine fails outright.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from hack_and_slash import config  # noqa: E402

CELL = config.TILE

# Fixed seed: the speckles on the floor are decoration, but a build that
# produces a different PNG every time makes "did the art change?" unanswerable.
RNG = random.Random(20260811)

TRANSPARENT = (0, 0, 0, 0)


# --- painters ----------------------------------------------------------------
def paint_floor(surface: pygame.Surface) -> None:
    surface.fill((38, 40, 52))
    # A few darker flecks so a large room does not read as one flat colour.
    for _ in range(7):
        x, y = RNG.randrange(CELL), RNG.randrange(CELL)
        surface.set_at((x, y), (32, 34, 45))
    for _ in range(3):
        x, y = RNG.randrange(CELL), RNG.randrange(CELL)
        surface.set_at((x, y), (45, 47, 60))


def paint_wall(surface: pygame.Surface) -> None:
    surface.fill((74, 78, 96))
    # A lit top edge and a shadowed bottom one. This is the whole reason walls
    # read as solid from a top-down camera rather than as differently coloured
    # floor.
    pygame.draw.rect(surface, (98, 104, 124), (0, 0, CELL, 3))
    pygame.draw.rect(surface, (48, 51, 65), (0, CELL - 3, CELL, 3))
    pygame.draw.rect(surface, (58, 62, 78), (0, 0, 1, CELL))


def _body(
    surface: pygame.Surface,
    main: tuple[int, int, int],
    dark: tuple[int, int, int],
    light: tuple[int, int, int],
    width: int,
    height: int,
) -> pygame.Rect:
    """A blocky torso centred in the cell, lit from above."""
    rect = pygame.Rect(0, 0, width, height)
    rect.center = (CELL // 2, CELL // 2 + 1)
    pygame.draw.rect(surface, dark, rect)
    pygame.draw.rect(surface, main, rect.inflate(-2, -2))
    pygame.draw.rect(surface, light, (rect.x + 1, rect.y + 1, rect.width - 2, 2))
    return rect


def _eyes(
    surface: pygame.Surface, rect: pygame.Rect, colour: tuple[int, int, int], gap: int = 2
) -> None:
    """Two pixels, so the front of a sprite is obvious at 1x."""
    surface.set_at((rect.centerx - gap, rect.centery), colour)
    surface.set_at((rect.centerx + gap, rect.centery), colour)


# --- the roster --------------------------------------------------------------
# Five bodies that have to be told apart instantly on a character select screen
# *and* at 1x in a crowded arena. Colour does most of that work, so each class
# owns a hue nothing else in the game uses: the enemies are green, red and
# purple, and the classes take blue, teal, tan, violet and white.
def paint_knight(surface: pygame.Surface) -> None:
    # The old hero's blue, kept deliberately -- the Knight is the reference
    # class and the campaign's recorded numbers were measured on this body.
    rect = _body(surface, (86, 148, 202), (38, 74, 112), (150, 200, 236), 11, 13)
    # A helmet band across the eyes: the widest, most armoured silhouette.
    pygame.draw.rect(surface, (208, 216, 228), (rect.x, rect.centery - 2, rect.width, 4))
    _eyes(surface, rect, (38, 60, 88))


def paint_rogue(surface: pygame.Surface) -> None:
    # Narrowest body in the game. Reads as quick before anything moves.
    rect = _body(surface, (72, 176, 154), (28, 84, 74), (132, 216, 198), 8, 11)
    # A low hood, drawn down over the brow.
    pygame.draw.rect(surface, (34, 96, 86), (rect.x, rect.y - 1, rect.width, 3))
    _eyes(surface, rect, (240, 250, 246), gap=1)


def paint_archer(surface: pygame.Surface) -> None:
    rect = _body(surface, (198, 166, 106), (104, 84, 46), (232, 210, 158), 9, 12)
    # The bow itself, down one side -- the only class whose weapon is visible on
    # the sprite, because "this one shoots" is the thing worth saying at a glance.
    pygame.draw.rect(surface, (120, 88, 52), (rect.right, rect.y + 1, 1, rect.height - 2))
    surface.set_at((rect.right + 1, rect.y + 2), (120, 88, 52))
    surface.set_at((rect.right + 1, rect.bottom - 3), (120, 88, 52))
    _eyes(surface, rect, (48, 38, 24))


def paint_magician(surface: pygame.Surface) -> None:
    rect = _body(surface, (138, 118, 216), (62, 52, 116), (186, 172, 240), 9, 11)
    # A pointed hat, two tiers, so the tallest silhouette belongs to the
    # squishiest thing on the screen.
    pygame.draw.rect(surface, (86, 72, 156), (rect.x + 1, rect.y - 2, rect.width - 2, 2))
    pygame.draw.rect(surface, (86, 72, 156), (rect.centerx - 1, rect.y - 4, 2, 2))
    _eyes(surface, rect, (250, 246, 200), gap=1)


def paint_priest(surface: pygame.Surface) -> None:
    rect = _body(surface, (226, 224, 214), (128, 124, 116), (248, 248, 242), 10, 12)
    # A gold band and a chest mark. Bright, because the Priest is the class you
    # pick to still be alive in twenty stages and it may as well look like it.
    pygame.draw.rect(surface, (216, 168, 74), (rect.x, rect.y + 2, rect.width, 2))
    pygame.draw.rect(surface, (216, 168, 74), (rect.centerx - 1, rect.centery + 2, 2, 3))
    _eyes(surface, rect, (96, 92, 84))


# --- what it fights ----------------------------------------------------------
def paint_grunt(surface: pygame.Surface) -> None:
    rect = _body(surface, (126, 168, 96), (58, 84, 44), (168, 204, 136), 9, 11)
    _eyes(surface, rect, (28, 32, 26))


def paint_rat(surface: pygame.Surface) -> None:
    # The smallest body in the game, and it has to read as small -- a rat that
    # looks like a grunt is a grunt that dies in one hit, which teaches the
    # player the wrong thing about both.
    rect = _body(surface, (132, 120, 112), (64, 58, 54), (172, 160, 150), 6, 7)
    # Ears.
    surface.set_at((rect.x, rect.y - 1), (172, 160, 150))
    surface.set_at((rect.right - 1, rect.y - 1), (172, 160, 150))
    _eyes(surface, rect, (232, 108, 100), gap=1)


def paint_charger(surface: pygame.Surface) -> None:
    # Wider and heavier than the others, because the thing it does is run you
    # over and the silhouette should say so before the telegraph does.
    rect = _body(surface, (198, 96, 78), (104, 42, 36), (232, 148, 122), 13, 12)
    # Horns.
    pygame.draw.rect(surface, (240, 226, 200), (rect.x, rect.y - 2, 2, 3))
    pygame.draw.rect(surface, (240, 226, 200), (rect.right - 2, rect.y - 2, 2, 3))
    surface.set_at((rect.centerx - 3, rect.centery + 1), (250, 240, 120))
    surface.set_at((rect.centerx + 3, rect.centery + 1), (250, 240, 120))


def paint_brute(surface: pygame.Surface) -> None:
    # Fills the cell like a boss does, without the boss's 2x scale -- the
    # biggest ordinary enemy in the game and the one you cannot afford to stand
    # next to. Dark and muddy so it does not read as the bright red charger.
    rect = _body(surface, (146, 82, 62), (72, 38, 28), (186, 118, 90), 14, 13)
    # Heavy shoulders.
    pygame.draw.rect(surface, (72, 38, 28), (rect.x - 1, rect.y + 2, 2, 4))
    pygame.draw.rect(surface, (72, 38, 28), (rect.right - 1, rect.y + 2, 2, 4))
    _eyes(surface, rect, (250, 214, 120), gap=3)


def paint_bowman(surface: pygame.Surface) -> None:
    # Was 'archer' until the player got a class by that name. Same sprite -- the
    # enemy did not change, only what it is called.
    rect = _body(surface, (156, 118, 196), (78, 56, 104), (198, 168, 226), 8, 11)
    # A hood, to separate it from the grunt at a glance.
    pygame.draw.rect(surface, (98, 72, 132), (rect.x, rect.y - 1, rect.width, 4))
    _eyes(surface, rect, (250, 244, 200), gap=1)


def paint_mage(surface: pygame.Surface) -> None:
    # A bowman that stands further back, so: the same purple, darker and colder,
    # with the hex it is about to throw held in front of it.
    rect = _body(surface, (108, 84, 164), (52, 40, 84), (150, 126, 208), 8, 11)
    pygame.draw.rect(surface, (52, 40, 84), (rect.x, rect.y - 1, rect.width, 4))
    pygame.draw.rect(surface, (168, 244, 232), (rect.centerx - 1, rect.bottom - 2, 2, 2))
    _eyes(surface, rect, (168, 244, 232), gap=1)


# --- one at the end of each act ----------------------------------------------
# All four fill their cell: the renderer draws them at 2x, and anything with a
# margin would float inside a 32px footprint. Each is a different temperature
# from the ordinary enemies and from each other, so no boss ever reads as a
# large version of something already on the screen.
def paint_boss(surface: pygame.Surface) -> None:
    # The Warden. Pale and cold against the warm red charger.
    rect = _body(surface, (188, 178, 214), (78, 72, 104), (232, 226, 244), 14, 14)

    # A crown of spikes along the top.
    for x in range(rect.x + 1, rect.right - 1, 3):
        pygame.draw.rect(surface, (246, 240, 250), (x, rect.y - 2, 1, 3))

    # Wide-set eyes, low on the face -- the silhouette cue that this is not
    # another grunt even at a glance.
    pygame.draw.rect(surface, (250, 96, 88), (rect.centerx - 4, rect.centery + 1, 2, 2))
    pygame.draw.rect(surface, (250, 96, 88), (rect.centerx + 2, rect.centery + 1, 2, 2))


def paint_houndmaster(surface: pygame.Surface) -> None:
    # The fast one. Hot orange, and the only boss with a narrow waist -- it
    # should look like it can move, because it can.
    rect = _body(surface, (222, 138, 62), (112, 62, 24), (250, 190, 118), 13, 14)

    # Two forward-swept horns rather than a crown: aggressive, not regal.
    pygame.draw.rect(surface, (250, 226, 190), (rect.x + 1, rect.y - 3, 2, 4))
    pygame.draw.rect(surface, (250, 226, 190), (rect.right - 3, rect.y - 3, 2, 4))
    pygame.draw.rect(surface, (112, 62, 24), (rect.x + 3, rect.bottom - 4, rect.width - 6, 2))

    pygame.draw.rect(surface, (255, 244, 120), (rect.centerx - 4, rect.centery, 3, 2))
    pygame.draw.rect(surface, (255, 244, 120), (rect.centerx + 1, rect.centery, 3, 2))


def paint_effigy(surface: pygame.Surface) -> None:
    # The slow one, and the largest. Dead wood and cold green -- nothing else in
    # the game is that colour, and it should look like it was built rather than
    # born.
    rect = _body(surface, (104, 116, 82), (46, 54, 38), (146, 160, 118), 15, 15)

    # A lattice of grain across the body, which is what stops a shape this big
    # from reading as a flat block at 2x.
    for y in range(rect.y + 2, rect.bottom - 2, 3):
        pygame.draw.rect(surface, (72, 82, 58), (rect.x + 1, y, rect.width - 2, 1))

    pygame.draw.rect(surface, (248, 174, 72), (rect.centerx - 5, rect.centery, 3, 3))
    pygame.draw.rect(surface, (248, 174, 72), (rect.centerx + 2, rect.centery, 3, 3))


def paint_sovereign(surface: pygame.Surface) -> None:
    # The last thing in the game. Gold on white, the brightest sprite in the
    # atlas, and the only one that uses the accent colour the HUD is drawn in.
    rect = _body(surface, (238, 232, 214), (146, 128, 78), (252, 250, 240), 15, 15)

    # A full crown, taller in the middle.
    pygame.draw.rect(surface, (216, 168, 74), (rect.x + 1, rect.y - 2, rect.width - 2, 2))
    for x in (rect.x + 2, rect.centerx - 1, rect.right - 4):
        pygame.draw.rect(surface, (216, 168, 74), (x, rect.y - 4, 2, 3))

    pygame.draw.rect(surface, (146, 128, 78), (rect.x + 2, rect.bottom - 4, rect.width - 4, 2))
    pygame.draw.rect(surface, (198, 60, 54), (rect.centerx - 5, rect.centery, 3, 3))
    pygame.draw.rect(surface, (198, 60, 54), (rect.centerx + 2, rect.centery, 3, 3))


def paint_arrow(surface: pygame.Surface) -> None:
    # Drawn pointing right; the renderer rotates it to match its heading.
    mid = CELL // 2
    pygame.draw.rect(surface, (228, 202, 128), (mid - 4, mid - 1, 7, 2))
    pygame.draw.rect(surface, (250, 240, 196), (mid + 3, mid - 2, 3, 4))
    pygame.draw.rect(surface, (140, 116, 78), (mid - 5, mid - 2, 2, 4))


def paint_shadow(surface: pygame.Surface) -> None:
    # Sits under every body. Without it, things look like they are floating
    # rather than standing on the floor -- the cheapest depth cue there is.
    pygame.draw.ellipse(surface, (0, 0, 0, 90), (3, CELL - 6, CELL - 6, 5))


def paint_coin(surface: pygame.Surface) -> None:
    # Small and unmistakable. It sits on the floor under everything else in the
    # room, so it has to read at 1x from the corner of your eye without being
    # big enough to hide a rat behind.
    mid = CELL // 2
    pygame.draw.rect(surface, (150, 110, 34), (mid - 3, mid - 2, 6, 5))
    pygame.draw.rect(surface, config.GOLD, (mid - 3, mid - 2, 6, 4))
    pygame.draw.rect(surface, (250, 232, 168), (mid - 2, mid - 1, 2, 2))


def paint_relic(surface: pygame.Surface) -> None:
    # A valuable. Drawn plain white-ish so the renderer can tint it to the
    # rarity that was rolled -- there is one sprite for all five tiers, and the
    # colour is the entire difference between a common and a legendary.
    mid = CELL // 2
    pygame.draw.rect(surface, (60, 62, 78), (mid - 4, mid - 4, 8, 8))
    pygame.draw.rect(surface, (236, 239, 244), (mid - 3, mid - 3, 6, 6))
    pygame.draw.rect(surface, (150, 156, 170), (mid - 3, mid + 1, 6, 2))
    pygame.draw.rect(surface, (255, 255, 255), (mid - 2, mid - 2, 2, 2))


PAINTERS = {
    "floor": paint_floor,
    "wall": paint_wall,
    "knight": paint_knight,
    "rogue": paint_rogue,
    "archer": paint_archer,
    "magician": paint_magician,
    "priest": paint_priest,
    "grunt": paint_grunt,
    "rat": paint_rat,
    "charger": paint_charger,
    "brute": paint_brute,
    "bowman": paint_bowman,
    "mage": paint_mage,
    "boss": paint_boss,
    "houndmaster": paint_houndmaster,
    "effigy": paint_effigy,
    "sovereign": paint_sovereign,
    "arrow": paint_arrow,
    "shadow": paint_shadow,
    "coin": paint_coin,
    "relic": paint_relic,
}


def main() -> int:
    pygame.init()

    missing = [name for name in config.SPRITE_ORDER if name not in PAINTERS]
    if missing:
        print(f"no painter for: {', '.join(missing)}", file=sys.stderr)
        return 1

    columns = config.ATLAS_COLUMNS
    rows = (len(config.SPRITE_ORDER) + columns - 1) // columns
    atlas = pygame.Surface((columns * CELL, rows * CELL), pygame.SRCALPHA)
    atlas.fill(TRANSPARENT)

    for index, name in enumerate(config.SPRITE_ORDER):
        cell = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        cell.fill(TRANSPARENT)
        PAINTERS[name](cell)
        atlas.blit(cell, ((index % columns) * CELL, (index // columns) * CELL))

    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    pygame.image.save(atlas, str(config.SPRITE_ATLAS))
    pygame.quit()

    print(
        f"wrote {config.SPRITE_ATLAS.relative_to(ROOT)}  "
        f"({len(config.SPRITE_ORDER)} sprites, {columns}x{rows} cells of {CELL}px)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
