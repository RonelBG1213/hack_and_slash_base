"""Constants shared across the game. Pure data -- imports nothing from pygame."""

from pathlib import Path

# --- paths -------------------------------------------------------------------
# config.py lives at src/hack_and_slash/config.py, so the project root is 3 up.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
LEVELS_DIR = ROOT / "levels"

ENTITIES_DATA = DATA_DIR / "entities.json"
WEAPONS_DATA = DATA_DIR / "weapons.json"
LOOT_DATA = DATA_DIR / "loot.json"
PROGRESSION_DATA = DATA_DIR / "progression.json"
SPRITE_ATLAS = ASSETS_DIR / "sprites.png"

# --- simulation --------------------------------------------------------------
# The sim advances in fixed ticks, never in real frame time. Everything that
# affects the outcome of a fight -- speeds, swing timings, cooldowns -- is
# expressed in ticks or in pixels-per-tick, so a seeded run replays identically
# no matter what the frame rate did. Rendering is free to lag or race; the sim
# is not.
TICKS_PER_SEC = 60
DT = 1.0 / TICKS_PER_SEC

# Longest real interval a single frame may feed the accumulator. Without this a
# stall (dragging the window, a breakpoint) queues hundreds of ticks and the
# game fast-forwards through a fight the player never saw.
MAX_FRAME_TIME = 0.25

# --- rendering ---------------------------------------------------------------
TILE = 16

# The internal resolution everything is drawn at. The window scales this up by a
# whole number only -- fractional scaling is what makes pixel art look smeared.
INTERNAL_W = 384
INTERNAL_H = 216

DEFAULT_SCALE = 3
WINDOW_W = INTERNAL_W * DEFAULT_SCALE
WINDOW_H = INTERNAL_H * DEFAULT_SCALE

# Bottom strip reserved for the HP bar and dodge pip; the arena draws above it.
HUD_H = 28
VIEWPORT_H = INTERNAL_H - HUD_H

FPS = 60
CAPTION = "Hack and Slash"


def integer_scale(win_w: int, win_h: int) -> int:
    """Largest whole-number factor that fits the internal surface in the window.

    Never returns 0 -- on a window smaller than the internal resolution we scale
    by 1 and let the edges crop rather than collapsing the surface to nothing.
    """
    return max(1, min(win_w // INTERNAL_W, win_h // INTERNAL_H))


def letterbox_offset(win_w: int, win_h: int) -> tuple[int, int]:
    """Top-left corner of the scaled surface inside the window."""
    scale = integer_scale(win_w, win_h)
    return (
        (win_w - INTERNAL_W * scale) // 2,
        (win_h - INTERNAL_H * scale) // 2,
    )


def window_to_internal(px: int, py: int, win_w: int, win_h: int) -> tuple[int, int]:
    """Window pixel -> internal-surface pixel.

    Every frame needs this: the mouse arrives in window coordinates but aiming
    happens in the 384x216 space. Getting it wrong aims somewhere other than the
    cursor, so it is kept pure and tested rather than inlined into the input code.
    """
    scale = integer_scale(win_w, win_h)
    off_x, off_y = letterbox_offset(win_w, win_h)
    return ((px - off_x) // scale, (py - off_y) // scale)


# --- sprite atlas ------------------------------------------------------------
# The order cells appear in assets/sprites.png. Declared here, in the one module
# that imports nothing, so the art generator and the atlas loader cannot drift
# apart -- and so a test can check that every sprite named in data/entities.json
# actually exists without pulling pygame into the logic suite.
#
# Adding a sprite means appending here and painting it in tools/gen_art.py.
#
# Grouped by what the thing is -- terrain, the five playable classes, the ten
# they promote into, the ordinary enemies, the eight act bosses, then the things
# that are not bodies. The grouping is for whoever reads the PNG; only the order
# matters to the code, and only because a cell is found by index.
#
# Append, never insert. A name added in the middle renumbers every cell after it
# and silently invalidates an already-generated sprites.png -- which is why the
# two enemies added for acts V-VIII sit after the mage rather than beside the
# creatures they most resemble.
SPRITE_ORDER = (
    "floor",
    "wall",
    # the roster
    "knight",
    "rogue",
    "archer",
    "magician",
    "priest",
    # promoted on the last stage: same silhouette as the class it grew out of,
    # so a Dark Knight still reads as a Knight at 1x in a crowded arena. The
    # branch is told by colour and one mark, which is the only budget a 16px
    # cell has left once the body shape is spoken for.
    "dark_knight",
    "holy_knight",
    "assassin",
    "shadow_rogue",
    "hunter",
    "magic_archer",
    "sage",
    "wizard",
    "battle_priest",
    "holy_priest",
    # what it fights
    "grunt",
    "rat",
    "charger",
    "brute",
    "bowman",
    "mage",
    # and what it fights after the fork
    "revenant",
    "stalker",
    # one at the end of each act
    "boss",
    "houndmaster",
    "effigy",
    "sovereign",
    "herald",
    "gaoler",
    "choir",
    "hollow_king",
    # neither of these is a creature
    "arrow",
    "shadow",
    # nor these: what a kill leaves on the floor
    "coin",
    "relic",
    # the same creatures wearing another face -- nine cosmetic variants, each
    # byte-identical in entities.json to the one named in its `variant_of`.
    # Appended here rather than filed beside the creatures they copy, for the
    # reason stated above: a cell is found by index, and inserting a goblin next
    # to the grunt would renumber every sprite after it.
    "goblin",
    "goblin_slinger",
    "goblin_pup",
    "orc",
    "orc_charger",
    "beastman",
    "beastman_stalker",
    "imp",
    "hellhound",
    # and the one thing here that is not a re-skin
    "demon",
)
ATLAS_COLUMNS = 8


def sprite_index(name: str) -> int:
    return SPRITE_ORDER.index(name)


# --- palette -----------------------------------------------------------------
# Kept small and named so the whole game reads as one coherent set of colors.
BLACK = (0, 0, 0)
LETTERBOX = (12, 12, 16)
WHITE = (236, 239, 244)
GREY = (120, 128, 140)
DARK = (28, 30, 38)
PANEL = (20, 22, 28)
ACCENT = (216, 168, 74)
GOOD = (126, 186, 116)
BAD = (198, 84, 78)
HERO = (108, 168, 214)
TELEGRAPH = (224, 122, 95)

# Gold, and the colour of each rarity. Keyed by the string in data/loot.json
# rather than by the `Rarity` enum, because this module imports nothing and is
# the one place that is true of -- game/ imports config, never the other way
# round.
#
# The ladder is the one every game of this kind uses, and that is the argument
# for it: grey-green-blue-purple-orange is read correctly by a player who has
# never seen this game, without a legend and without being told.
GOLD = (226, 186, 84)
RARITY_COLORS = {
    "common": (170, 176, 188),
    "uncommon": (126, 186, 116),
    "rare": (108, 168, 214),
    "epic": (168, 122, 214),
    "legendary": (232, 158, 74),
}
