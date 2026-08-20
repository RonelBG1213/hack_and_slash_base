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


# --- the promoted classes ----------------------------------------------------
# Each keeps its base's body dimensions exactly, so the silhouette is unchanged
# and a promoted hero still reads as what it was at 1x. Only the palette moves,
# plus one mark that says which of the two branches it is. That is the whole
# budget: a 16px cell has room for a shape or a story, not both, and the shape
# is already spoken for.
def paint_dark_knight(surface: pygame.Surface) -> None:
    rect = _body(surface, (78, 72, 116), (32, 28, 54), (122, 114, 164), 11, 13)
    # The Knight's helmet band, gone dark, and the only red eyes on a hero.
    pygame.draw.rect(surface, (44, 40, 70), (rect.x, rect.centery - 2, rect.width, 4))
    _eyes(surface, rect, (214, 84, 74))


def paint_holy_knight(surface: pygame.Surface) -> None:
    rect = _body(surface, (222, 220, 208), (138, 132, 118), (250, 248, 240), 11, 13)
    # The same band in gold, and a cross on the chest -- the widest, brightest
    # thing the player can be.
    pygame.draw.rect(surface, (216, 168, 74), (rect.x, rect.centery - 2, rect.width, 4))
    pygame.draw.rect(surface, (216, 168, 74), (rect.centerx - 1, rect.centery + 2, 2, 4))
    _eyes(surface, rect, (86, 82, 74))


def paint_assassin(surface: pygame.Surface) -> None:
    rect = _body(surface, (162, 58, 68), (70, 22, 30), (208, 106, 114), 8, 11)
    # The Rogue's hood, in blood. Narrow body, so the colour does all the work.
    pygame.draw.rect(surface, (94, 28, 38), (rect.x, rect.y - 1, rect.width, 3))
    _eyes(surface, rect, (252, 226, 220), gap=1)


def paint_shadow_rogue(surface: pygame.Surface) -> None:
    rect = _body(surface, (66, 58, 100), (24, 20, 42), (112, 100, 154), 8, 11)
    pygame.draw.rect(surface, (34, 28, 58), (rect.x, rect.y - 1, rect.width, 3))
    # Pale violet eyes: the darkest hero in the game needs its front edge to
    # still be findable against a dark floor.
    _eyes(surface, rect, (198, 178, 250), gap=1)


def paint_hunter(surface: pygame.Surface) -> None:
    rect = _body(surface, (110, 152, 88), (48, 74, 38), (156, 196, 130), 9, 12)
    # The Archer's bow, kept -- it is still the thing worth saying at a glance.
    pygame.draw.rect(surface, (74, 96, 56), (rect.right, rect.y + 1, 1, rect.height - 2))
    surface.set_at((rect.right + 1, rect.y + 2), (74, 96, 56))
    surface.set_at((rect.right + 1, rect.bottom - 3), (74, 96, 56))
    _eyes(surface, rect, (30, 44, 26))


def paint_magic_archer(surface: pygame.Surface) -> None:
    rect = _body(surface, (94, 164, 190), (38, 78, 96), (148, 210, 232), 9, 12)
    pygame.draw.rect(surface, (48, 92, 112), (rect.right, rect.y + 1, 1, rect.height - 2))
    surface.set_at((rect.right + 1, rect.y + 2), (48, 92, 112))
    surface.set_at((rect.right + 1, rect.bottom - 3), (48, 92, 112))
    # One lit pixel on the bow: the arrow that is not an arrow.
    surface.set_at((rect.right + 1, rect.centery), (226, 246, 255))
    _eyes(surface, rect, (24, 54, 68))


def paint_sage(surface: pygame.Surface) -> None:
    rect = _body(surface, (206, 190, 232), (114, 100, 142), (238, 228, 250), 9, 11)
    # The Magician's two-tier hat, kept: it is the tallest silhouette in the
    # game and both branches have earned it.
    pygame.draw.rect(surface, (146, 128, 184), (rect.x + 1, rect.y - 2, rect.width - 2, 2))
    pygame.draw.rect(surface, (146, 128, 184), (rect.centerx - 1, rect.y - 4, 2, 2))
    _eyes(surface, rect, (86, 70, 118), gap=1)


def paint_wizard(surface: pygame.Surface) -> None:
    rect = _body(surface, (74, 62, 158), (30, 24, 78), (124, 108, 208), 9, 11)
    pygame.draw.rect(surface, (44, 34, 106), (rect.x + 1, rect.y - 2, rect.width - 2, 2))
    pygame.draw.rect(surface, (44, 34, 106), (rect.centerx - 1, rect.y - 4, 2, 2))
    # A lit tip: the hardest single hit in the game is worth one bright pixel.
    surface.set_at((rect.centerx, rect.y - 5), (236, 220, 255))
    _eyes(surface, rect, (250, 240, 190), gap=1)


def paint_battle_priest(surface: pygame.Surface) -> None:
    rect = _body(surface, (176, 178, 186), (94, 96, 104), (216, 218, 226), 10, 12)
    # Steel where the Priest had cloth, and the gold band kept but narrowed.
    pygame.draw.rect(surface, (198, 152, 66), (rect.x, rect.y + 2, rect.width, 1))
    pygame.draw.rect(surface, (198, 152, 66), (rect.centerx - 1, rect.centery + 2, 2, 3))
    _eyes(surface, rect, (52, 54, 60))


def paint_holy_priest(surface: pygame.Surface) -> None:
    rect = _body(surface, (244, 242, 232), (150, 146, 136), (254, 254, 250), 10, 12)
    # A halo above the head rather than a band across it -- the one hero mark
    # that sits outside the body, for the class that is never surrounded.
    pygame.draw.rect(surface, (240, 208, 120), (rect.x + 2, rect.y - 2, rect.width - 4, 1))
    pygame.draw.rect(surface, (240, 208, 120), (rect.centerx - 1, rect.centery + 2, 2, 3))
    _eyes(surface, rect, (128, 122, 110))


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


# --- and what it fights after the fork ---------------------------------------
# Two more, and the harder brief: these arrive twenty stages in, into a room
# that may already hold five things the player knows by shape. So each takes a
# silhouette cue rather than only a colour -- the revenant is the only body with
# a broken outline, the stalker the only one that leans.
def paint_revenant(surface: pygame.Surface) -> None:
    # Brute-sized and cold where the brute is warm: the point of it is that it
    # takes a brute's beating and moves like a grunt, so it must not read as
    # either. Nothing else in the game is this drowned blue-grey.
    rect = _body(surface, (108, 128, 134), (44, 56, 62), (156, 180, 186), 12, 13)

    # Ribs -- gaps cut out of the body, which is the one silhouette trick no
    # other sprite uses. A shape with holes in it reads as dead at 1x.
    for y in range(rect.y + 4, rect.bottom - 2, 3):
        surface.set_at((rect.x + 2, y), (44, 56, 62))
        surface.set_at((rect.right - 3, y), (44, 56, 62))

    _eyes(surface, rect, (140, 250, 236), gap=3)


def paint_stalker(surface: pygame.Surface) -> None:
    # A charger that hunts. Narrower than the charger and much darker, because
    # the charger's whole tell is that you can see it coming from across the
    # arena and this one's is that you have less time when you do.
    rect = _body(surface, (130, 54, 74), (56, 20, 32), (182, 92, 114), 10, 12)

    # Swept back along one side: the only asymmetric body in the atlas, so it
    # reads as leaning into a run even standing still.
    pygame.draw.rect(surface, (56, 20, 32), (rect.right, rect.y + 3, 2, 5))
    pygame.draw.rect(surface, (182, 92, 114), (rect.x - 1, rect.y + 1, 1, 4))

    _eyes(surface, rect, (252, 226, 96), gap=2)


# --- the same creatures wearing another face ---------------------------------
# The nine cosmetic variants. Each one is byte-identical in `entities.json` to
# the creature named in its `variant_of`, so the brief here is the *inverse* of
# the usual one: it must read as a different creature without ever reading as a
# different threat.
#
# Which settles the rule these are all drawn under, and it is the promoted-hero
# rule pointed at the enemies:
#
#     keep the base's body dimensions exactly; change the colour and one mark.
#
# The dimensions are load-bearing rather than tidy. A player reads danger off
# silhouette before colour -- a brute-sized shape means "do not stand next to
# that" and a rat-sized one means "this dies instantly". An orc drawn smaller
# than the brute whose numbers it is carrying would teach the wrong lesson about
# a 55hp body, and the player would learn it by dying. So the family is in the
# hue and one silhouette detail, and the size belongs to the base.
#
# Four families, four hues nothing else in the atlas uses: goblins mustard, orcs
# moss, beastmen tawny, demons charcoal with an ember.
def paint_goblin(surface: pygame.Surface) -> None:
    # The grunt's body (9x11) in mustard rather than leaf green. Ears are the
    # one mark -- cheap, instantly legible, and the whole goblin family shares
    # them, so three sprites become one idea.
    rect = _body(surface, (150, 148, 72), (72, 70, 32), (192, 190, 110), 9, 11)
    pygame.draw.rect(surface, (192, 190, 110), (rect.x - 1, rect.y + 1, 1, 3))
    pygame.draw.rect(surface, (192, 190, 110), (rect.right, rect.y + 1, 1, 3))
    _eyes(surface, rect, (28, 32, 26))


def paint_goblin_slinger(surface: pygame.Surface) -> None:
    # The bowman's body (8x11) and the bowman's hood, because the hood is how a
    # ranged enemy is told from a melee one at a glance and that reading must
    # survive the re-skin. Mustard underneath, ears poking out of the hood.
    rect = _body(surface, (150, 148, 72), (72, 70, 32), (192, 190, 110), 8, 11)
    pygame.draw.rect(surface, (94, 92, 38), (rect.x, rect.y - 1, rect.width, 4))
    surface.set_at((rect.x - 1, rect.y + 2), (192, 190, 110))
    surface.set_at((rect.right, rect.y + 2), (192, 190, 110))
    _eyes(surface, rect, (250, 244, 200), gap=1)


def paint_goblin_pup(surface: pygame.Surface) -> None:
    # The rat's body (6x7), which is the smallest in the game and has to stay
    # that way: this thing dies to one hit from anything, and the sprite is the
    # only warning of that the player gets.
    rect = _body(surface, (150, 148, 72), (72, 70, 32), (192, 190, 110), 6, 7)
    surface.set_at((rect.x - 1, rect.y), (192, 190, 110))
    surface.set_at((rect.right, rect.y), (192, 190, 110))
    _eyes(surface, rect, (232, 108, 100), gap=1)


def paint_orc(surface: pygame.Surface) -> None:
    # The brute's body (14x13) -- the biggest ordinary enemy in the game, and
    # the size is the entire warning. Moss green and cold where the brute is
    # muddy red, with the brute's heavy shoulders kept for the same reason the
    # slinger keeps its hood.
    rect = _body(surface, (98, 120, 86), (44, 58, 40), (138, 164, 120), 14, 13)
    pygame.draw.rect(surface, (44, 58, 40), (rect.x - 1, rect.y + 2, 2, 4))
    pygame.draw.rect(surface, (44, 58, 40), (rect.right - 1, rect.y + 2, 2, 4))
    # Tusks: a pale jaw along the bottom edge rather than two pixels below the
    # eyes. The first draft put them at centery + 3 and at 16px they read as a
    # second pair of eyes -- the body is only thirteen tall, so anything round
    # and light near the middle is an eye whatever it was drawn as.
    pygame.draw.rect(surface, (238, 232, 210), (rect.x + 3, rect.bottom - 3, 2, 2))
    pygame.draw.rect(surface, (238, 232, 210), (rect.right - 5, rect.bottom - 3, 2, 2))
    _eyes(surface, rect, (250, 214, 120), gap=3)


def paint_orc_charger(surface: pygame.Surface) -> None:
    # The charger's body (13x12) and the charger's horns. The horns are the
    # telegraph's silhouette -- the player learns "wide pale horns means it is
    # about to run at me" on stage 2 and must not have to learn it twice.
    rect = _body(surface, (98, 120, 86), (44, 58, 40), (138, 164, 120), 13, 12)
    pygame.draw.rect(surface, (240, 226, 200), (rect.x, rect.y - 2, 2, 3))
    pygame.draw.rect(surface, (240, 226, 200), (rect.right - 2, rect.y - 2, 2, 3))
    surface.set_at((rect.centerx - 3, rect.centery + 1), (250, 240, 120))
    surface.set_at((rect.centerx + 3, rect.centery + 1), (250, 240, 120))


def paint_beastman(surface: pygame.Surface) -> None:
    # The revenant's body (12x13) in tawny fur. Deliberately *without* the
    # revenant's ribs: a broken outline is that sprite's one silhouette trick
    # and the thing that reads as dead at 1x. A beastman is alive, so it gets a
    # mane instead and the atlas keeps one holed body rather than two.
    # Orange, not brown -- and that is a correction rather than a preference.
    # Drafted in tawny (170, 134, 90) it sat one step from the brute's muddy
    # (146, 82, 62) at a size one pixel narrower, and those two must never be
    # confused: a brute is 55hp you can walk away from, a beastman is 32hp that
    # follows. Orange is the one warm hue no enemy had.
    rect = _body(surface, (192, 124, 58), (96, 56, 24), (228, 170, 110), 12, 13)
    pygame.draw.rect(surface, (96, 56, 24), (rect.x + 1, rect.y - 1, rect.width - 2, 2))
    surface.set_at((rect.x, rect.y - 2), (228, 170, 110))
    surface.set_at((rect.right - 1, rect.y - 2), (228, 170, 110))
    _eyes(surface, rect, (250, 240, 200), gap=3)


def paint_beastman_stalker(surface: pygame.Surface) -> None:
    # The stalker's body (10x12) and its lean, which is the only asymmetric
    # silhouette in the atlas and means "this commits from further out than the
    # charger does". Tawny and darker, so the family reads before the threat.
    rect = _body(surface, (160, 96, 44), (78, 44, 18), (206, 142, 82), 10, 12)
    pygame.draw.rect(surface, (78, 44, 18), (rect.right, rect.y + 3, 2, 5))
    pygame.draw.rect(surface, (206, 142, 82), (rect.x - 1, rect.y + 1, 1, 4))
    _eyes(surface, rect, (252, 226, 96), gap=2)


def paint_imp(surface: pygame.Surface) -> None:
    # The mage's body (8x11), hood and held bolt. Charcoal instead of purple,
    # and the bolt burns rather than freezes -- the demons are the only things
    # in the atlas with an ember on them, which is the family's whole signature.
    rect = _body(surface, (78, 66, 84), (34, 28, 38), (118, 102, 126), 8, 11)
    pygame.draw.rect(surface, (34, 28, 38), (rect.x, rect.y - 1, rect.width, 4))
    # Horns, above the hood.
    surface.set_at((rect.x + 1, rect.y - 2), (156, 140, 164))
    surface.set_at((rect.right - 2, rect.y - 2), (156, 140, 164))
    pygame.draw.rect(surface, (250, 140, 60), (rect.centerx - 1, rect.bottom - 2, 2, 2))
    _eyes(surface, rect, (250, 140, 60), gap=1)


def paint_hellhound(surface: pygame.Surface) -> None:
    # The charger's body (13x12) and horns again, in the demon charcoal. Two
    # variants of the charger ship (orc_charger, hellhound) and that is the
    # point of a variant: the numbers are the act-I charger's either way, so a
    # player who learned the tell in act I still reads it in act VIII.
    rect = _body(surface, (64, 58, 66), (28, 24, 30), (104, 96, 108), 13, 12)
    pygame.draw.rect(surface, (240, 226, 200), (rect.x, rect.y - 2, 2, 3))
    pygame.draw.rect(surface, (240, 226, 200), (rect.right - 2, rect.y - 2, 2, 3))
    # The ember, where the charger has its two yellow pixels.
    surface.set_at((rect.centerx - 3, rect.centery + 1), (250, 140, 60))
    surface.set_at((rect.centerx + 3, rect.centery + 1), (250, 140, 60))
    pygame.draw.rect(surface, (250, 140, 60), (rect.centerx - 1, rect.bottom - 3, 2, 1))


def paint_demon(surface: pygame.Surface) -> None:
    # The only genuinely new creature in this batch, and the only one allowed to
    # invent a silhouette -- the nine above are re-skins and borrow theirs.
    #
    # It gets the one shape nothing else has: wings, drawn as a pair of blocks
    # spread wider than the body. A flanker is the only thing in the game that
    # does not come straight at you, and the sprite has to say "this one moves
    # differently" before it has moved at all, in a room that by act VII holds
    # six creatures the player already knows.
    rect = _body(surface, (108, 52, 62), (48, 20, 26), (156, 84, 96), 10, 12)

    # Wings: wider than the body on both sides, which is the whole read.
    pygame.draw.rect(surface, (48, 20, 26), (rect.x - 3, rect.y + 2, 3, 5))
    pygame.draw.rect(surface, (48, 20, 26), (rect.right, rect.y + 2, 3, 5))
    surface.set_at((rect.x - 3, rect.y + 1), (156, 84, 96))
    surface.set_at((rect.right + 2, rect.y + 1), (156, 84, 96))

    # Horns, and the family's ember.
    pygame.draw.rect(surface, (232, 214, 200), (rect.x + 1, rect.y - 2, 1, 2))
    pygame.draw.rect(surface, (232, 214, 200), (rect.right - 2, rect.y - 2, 1, 2))
    _eyes(surface, rect, (250, 140, 60), gap=2)


# --- one at the end of each act ----------------------------------------------
# All eight fill their cell: the renderer draws them at 2x, and anything with a
# margin would float inside a 32px footprint. Each is a different temperature
# from the ordinary enemies and from each other, so no boss ever reads as a
# large version of something already on the screen.
#
# The four below the Sovereign close acts V-VIII. They have a colour problem the
# first four did not: eight bosses is more distinct temperatures than a 16px
# cell comfortably holds, so each of these leans on one structural mark -- wings,
# bars, a scatter, a broken crown -- rather than on hue alone.
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


def paint_herald(surface: pygame.Surface) -> None:
    # First after the fork, and the quick one. Cold cyan-white: the Warden is
    # the only other pale boss and it is lilac, so these two never share a
    # stage and never have to be told apart in motion.
    rect = _body(surface, (150, 206, 214), (56, 96, 108), (206, 242, 248), 14, 14)

    # Wings swept up and out -- the mark that says "this one is fast" before it
    # has moved, the same job the Houndmaster's horns do.
    for offset, direction in ((0, -1), (1, 1)):
        edge = rect.x - 1 if direction < 0 else rect.right
        pygame.draw.rect(surface, (206, 242, 248), (edge, rect.y + 1 + offset, 1, 5))
        pygame.draw.rect(surface, (56, 96, 108), (edge, rect.y + 5, 1, 2))

    pygame.draw.rect(surface, (252, 240, 140), (rect.centerx - 4, rect.centery, 3, 2))
    pygame.draw.rect(surface, (252, 240, 140), (rect.centerx + 1, rect.centery, 3, 2))


def paint_gaoler(surface: pygame.Surface) -> None:
    # The slow one, and the heaviest thing in the game. Iron and rust -- the
    # only boss with no light in it at all, which is what stops a body this
    # large from reading as the Effigy at a glance.
    rect = _body(surface, (92, 88, 96), (38, 36, 42), (132, 128, 138), 15, 15)

    # Bars across the body. Vertical where the Effigy's grain is horizontal, so
    # the two slow bosses differ in structure and not only in colour.
    for x in range(rect.x + 2, rect.right - 1, 3):
        pygame.draw.rect(surface, (38, 36, 42), (x, rect.y + 2, 1, rect.height - 4))

    # Rust at the shoulders, the one warm note.
    pygame.draw.rect(surface, (150, 84, 46), (rect.x, rect.y + 1, rect.width, 1))
    pygame.draw.rect(surface, (198, 148, 92), (rect.centerx - 5, rect.centery, 3, 3))
    pygame.draw.rect(surface, (198, 148, 92), (rect.centerx + 2, rect.centery, 3, 3))


def paint_choir(surface: pygame.Surface) -> None:
    # The ranged one, and the least solid. Pale rose, and scattered rather than
    # built: it should look like several things agreeing rather than one body,
    # because eleven shots at once is what it is.
    rect = _body(surface, (206, 170, 220), (94, 66, 108), (238, 216, 246), 14, 14)

    # A scatter of brighter motes across the body -- the structural mark, and
    # the only sprite in the atlas that is deliberately noisy.
    for step_y in range(rect.y + 2, rect.bottom - 2, 2):
        for step_x in range(rect.x + 2, rect.right - 2, 4):
            offset = 2 if (step_y // 2) % 2 else 0
            if step_x + offset < rect.right - 2:
                surface.set_at((step_x + offset, step_y), (248, 236, 252))

    pygame.draw.rect(surface, (120, 84, 168), (rect.centerx - 5, rect.centery, 3, 3))
    pygame.draw.rect(surface, (120, 84, 168), (rect.centerx + 2, rect.centery, 3, 3))


def paint_hollow_king(surface: pygame.Surface) -> None:
    # Stage forty. The Sovereign inverted on purpose -- that fight is the
    # brightest sprite in the atlas and this one is the darkest, wearing the
    # same crown with pieces missing from it.
    rect = _body(surface, (58, 50, 86), (22, 18, 36), (110, 96, 152), 15, 15)

    # A broken crown: the Sovereign's three points with the middle one gone.
    pygame.draw.rect(surface, (216, 168, 74), (rect.x + 1, rect.y - 2, rect.width - 2, 2))
    for x in (rect.x + 2, rect.right - 4):
        pygame.draw.rect(surface, (216, 168, 74), (x, rect.y - 4, 2, 3))
    pygame.draw.rect(surface, (22, 18, 36), (rect.centerx - 1, rect.y - 2, 2, 2))

    pygame.draw.rect(surface, (22, 18, 36), (rect.x + 2, rect.bottom - 4, rect.width - 4, 2))
    pygame.draw.rect(surface, (250, 78, 70), (rect.centerx - 5, rect.centery, 3, 3))
    pygame.draw.rect(surface, (250, 78, 70), (rect.centerx + 2, rect.centery, 3, 3))


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


# --- what stands in a reward room --------------------------------------------
# Five fixtures, and they are drawn under a different rule from every body in
# this file. A creature has to be told apart from other creatures at 1x in a
# crowd; a fixture is alone in an empty room and has to be told apart from the
# *floor* -- so these are taller, more saturated, and each one is built around a
# single silhouette a player can name from across the room: a basin, an awning,
# an obelisk, a lid, an arch.
#
# All five fill more of the cell than a body does. Nothing walks in front of
# them, so there is no reason to keep them small.
def paint_fountain(surface: pygame.Surface) -> None:
    # A basin with water in it. The water is the only large area of blue-green
    # in the game, which is most of why this reads as healing without a label.
    mid = CELL // 2
    pygame.draw.rect(surface, (86, 92, 112), (mid - 6, mid - 4, 12, 9))
    pygame.draw.rect(surface, (58, 62, 78), (mid - 6, mid + 3, 12, 2))
    pygame.draw.rect(surface, (72, 178, 168), (mid - 5, mid - 3, 10, 5))
    pygame.draw.rect(surface, (160, 232, 224), (mid - 4, mid - 3, 4, 2))
    # A spout above the rim, so the shape is not a plain rectangle at a glance.
    pygame.draw.rect(surface, (110, 116, 138), (mid - 1, mid - 7, 2, 4))


def paint_stall(surface: pygame.Surface) -> None:
    # A striped awning over a counter. The stripes are the whole idea: nothing
    # else in the game has a repeating pattern on it, so a stall is identifiable
    # at a glance even when the colours are wrong on somebody's monitor.
    mid = CELL // 2
    pygame.draw.rect(surface, (96, 74, 52), (mid - 6, mid - 1, 12, 6))
    pygame.draw.rect(surface, (128, 100, 70), (mid - 6, mid - 1, 12, 2))
    for i in range(6):
        colour = config.ACCENT if i % 2 == 0 else (196, 92, 84)
        pygame.draw.rect(surface, colour, (mid - 6 + i * 2, mid - 6, 2, 5))
    pygame.draw.rect(surface, (40, 42, 54), (mid - 6, mid - 7, 12, 1))


def paint_shrine(surface: pygame.Surface) -> None:
    # A standing stone with a lit rune. Tall and narrow -- the only fixture with
    # that silhouette, so it is told apart from the fountain and the chest by
    # shape before colour has said anything.
    mid = CELL // 2
    pygame.draw.rect(surface, (58, 60, 78), (mid - 3, mid - 7, 6, 12))
    pygame.draw.rect(surface, (84, 88, 112), (mid - 3, mid - 7, 6, 2))
    pygame.draw.rect(surface, (168, 122, 214), (mid - 1, mid - 4, 2, 5))
    pygame.draw.rect(surface, (232, 208, 255), (mid - 1, mid - 4, 2, 2))
    pygame.draw.rect(surface, (40, 42, 54), (mid - 4, mid + 4, 8, 2))


def paint_chest(surface: pygame.Surface) -> None:
    # Wider than it is tall, with a banded lid. Deliberately the same gold the
    # coin uses on its clasp: a chest and the money it holds should look like
    # they belong to each other.
    mid = CELL // 2
    pygame.draw.rect(surface, (70, 48, 32), (mid - 6, mid - 4, 12, 9))
    pygame.draw.rect(surface, (108, 76, 48), (mid - 6, mid - 4, 12, 4))
    pygame.draw.rect(surface, (52, 36, 24), (mid - 6, mid, 12, 1))
    pygame.draw.rect(surface, config.GOLD, (mid - 1, mid - 2, 2, 5))
    pygame.draw.rect(surface, (250, 232, 168), (mid - 1, mid - 2, 2, 2))


def paint_door(surface: pygame.Surface) -> None:
    # An arch, drawn as a frame rather than a slab: what matters about a door
    # here is that it is a way *through*, and the renderer draws the icon of
    # what lies beyond it in the opening. So the middle is left dark and empty
    # on purpose -- it is a socket for that icon, not a missing detail.
    mid = CELL // 2
    pygame.draw.rect(surface, (128, 116, 92), (mid - 6, mid - 7, 12, 14))
    pygame.draw.rect(surface, (12, 12, 18), (mid - 4, mid - 5, 8, 12))
    pygame.draw.rect(surface, (168, 152, 116), (mid - 6, mid - 7, 12, 2))
    pygame.draw.rect(surface, (78, 70, 56), (mid - 6, mid + 5, 12, 2))


# --- what the floor does at depth --------------------------------------------
# Three traps, each drawn in its DANGEROUS state. The dormant state is this same
# cell through the atlas's `shaded()`, which is what a spent fountain already
# uses -- a second cell per trap would be a second thing to keep in sync for no
# pixel a player could not already read.
#
# All three are deliberately *warm*. Nothing else on the floor is: the arena is
# blues and greys, loot is gold, and the fixtures are muted. So "orange on the
# ground" means one thing in this game and it means it before the shape has
# resolved, which is the only budget a 16px cell has at 1x in a crowded fight.
def paint_spike(surface: pygame.Surface) -> None:
    # Four teeth through a floor plate. Drawn as triangles because every other
    # hazard here is a bar or a blade -- at this size the silhouette is the
    # whole of what tells them apart.
    mid = CELL // 2
    pygame.draw.rect(surface, (46, 44, 52), (mid - 7, mid - 7, 14, 14))
    pygame.draw.rect(surface, (68, 64, 76), (mid - 7, mid - 7, 14, 1))
    for i in range(4):
        x = mid - 6 + i * 4
        pygame.draw.polygon(
            surface, (218, 214, 226), [(x, mid + 5), (x + 3, mid + 5), (x + 1, mid - 5)]
        )
        # One bright column down each tooth: a flat grey triangle reads as a
        # pillar, a highlighted one reads as metal.
        pygame.draw.rect(surface, (255, 255, 255), (x + 1, mid - 4, 1, 6))
    pygame.draw.rect(surface, (176, 60, 48), (mid - 7, mid + 6, 14, 1))


def paint_flame(surface: pygame.Surface) -> None:
    # A jet, painted across the cell rather than up it: the renderer tiles this
    # along a horizontal lane, so the bright band has to run edge to edge or the
    # lane reads as a row of separate blobs.
    mid = CELL // 2
    pygame.draw.rect(surface, (176, 52, 30), (0, mid - 5, CELL, 10))
    pygame.draw.rect(surface, (232, 118, 36), (0, mid - 3, CELL, 6))
    pygame.draw.rect(surface, (252, 200, 92), (0, mid - 1, CELL, 3))
    # A ragged top and bottom edge so a long lane does not read as a painted
    # stripe on the floor. Alternating, not random -- the atlas has to be the
    # same PNG every build.
    for x in range(0, CELL, 4):
        pygame.draw.rect(surface, (232, 118, 36), (x, mid - 6, 2, 1))
        pygame.draw.rect(surface, (232, 118, 36), (x + 2, mid + 5, 2, 1))


def paint_blade(surface: pygame.Surface) -> None:
    # A disc on a shaft. Round on purpose: it is the only circular thing on the
    # floor, and roundness is what reads as *rotating* when the sprite itself
    # never animates -- the motion comes from the trap moving across the arena.
    mid = CELL // 2
    pygame.draw.rect(surface, (58, 60, 74), (mid - 1, 0, 2, CELL))
    pygame.draw.circle(surface, (188, 196, 214), (mid, mid), 7)
    pygame.draw.circle(surface, (236, 242, 252), (mid, mid), 5)
    pygame.draw.circle(surface, (92, 98, 118), (mid, mid), 2)
    # Teeth around the rim, at the diagonals so they survive the scale-up.
    for dx, dy in ((-5, -5), (5, -5), (-5, 5), (5, 5)):
        pygame.draw.rect(surface, (248, 252, 255), (mid + dx - 1, mid + dy - 1, 2, 2))
    pygame.draw.rect(surface, (176, 60, 48), (mid - 1, mid - 7, 2, 2))


PAINTERS = {
    "floor": paint_floor,
    "wall": paint_wall,
    "knight": paint_knight,
    "rogue": paint_rogue,
    "archer": paint_archer,
    "magician": paint_magician,
    "priest": paint_priest,
    "dark_knight": paint_dark_knight,
    "holy_knight": paint_holy_knight,
    "assassin": paint_assassin,
    "shadow_rogue": paint_shadow_rogue,
    "hunter": paint_hunter,
    "magic_archer": paint_magic_archer,
    "sage": paint_sage,
    "wizard": paint_wizard,
    "battle_priest": paint_battle_priest,
    "holy_priest": paint_holy_priest,
    "grunt": paint_grunt,
    "rat": paint_rat,
    "charger": paint_charger,
    "brute": paint_brute,
    "bowman": paint_bowman,
    "mage": paint_mage,
    "revenant": paint_revenant,
    "stalker": paint_stalker,
    "goblin": paint_goblin,
    "goblin_slinger": paint_goblin_slinger,
    "goblin_pup": paint_goblin_pup,
    "orc": paint_orc,
    "orc_charger": paint_orc_charger,
    "beastman": paint_beastman,
    "beastman_stalker": paint_beastman_stalker,
    "imp": paint_imp,
    "hellhound": paint_hellhound,
    "demon": paint_demon,
    "boss": paint_boss,
    "houndmaster": paint_houndmaster,
    "effigy": paint_effigy,
    "sovereign": paint_sovereign,
    "herald": paint_herald,
    "gaoler": paint_gaoler,
    "choir": paint_choir,
    "hollow_king": paint_hollow_king,
    "arrow": paint_arrow,
    "shadow": paint_shadow,
    "coin": paint_coin,
    "relic": paint_relic,
    "fountain": paint_fountain,
    "stall": paint_stall,
    "shrine": paint_shrine,
    "chest": paint_chest,
    "door": paint_door,
    "spike": paint_spike,
    "flame": paint_flame,
    "blade": paint_blade,
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
