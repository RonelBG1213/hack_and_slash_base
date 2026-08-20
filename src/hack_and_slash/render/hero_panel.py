"""What the hero is, drawn over a paused arena.

The fourth panel, and the only one that asks for nothing. Same slot and the same
reasoning as `shop_panel.py`, `job_panel.py` and `level_panel.py`: the scene
decides *when* this is on screen, this decides what it looks like, and neither
holds the other's details.

**Reads a `Run` and writes to nothing at all.** The other three each sit in front
of a decision -- buy this, spend that, choose a path -- and every one of them has
a function in `game/` that the scene calls when a key arrives. This one has no
such function because there is nothing to call: it is a readout, and closing it
leaves the run byte for byte what it was.

It exists because the attribute layer had nowhere to be seen. A piece bought at a
stall dissolves into `run.earned` on the way in -- `equipment.buy` hands the block
to `progression.grant` and what survives is a sum -- so the only evidence a player
ever had that a Cuirass did anything was the health number in the HUD moving, and
seven of the eight attributes did not even have that.

Three columns: what the class brings, what this run earned, and the total. The
middle one is the answer to "did that purchase do anything", which is the
question this panel is for.
"""

from __future__ import annotations

import pygame

from .. import config
from ..game import progression, skills
from .level_panel import LABELS, ROW_H, ROW_Y, format_value, hint_y

#: Always eight rows -- every attribute, every time. That is the one way this
#: differs from the shrine's plinth, which draws the three it rolled: a decision
#: is about what is in front of you, and a readout that hid five of your eight
#: numbers would be a worse answer to every question it is opened for.
#:
#: Which makes this panel the tallest case of `level_panel.py`'s geometry, so its
#: constants are imported rather than redrafted. That file records what redrafting
#: them costs: at `ROW_H 18` the eighth row draws straight through the hint, and
#: the fit test measures `len(ROW_KEYS) - 1` so it passed while the pixels
#: overlapped.
ROWS: tuple[str, ...] = progression.SPENDABLE

TITLE_Y = 10
SUBTITLE_Y = 28

LEFT = 30

#: The three numeric columns, right-aligned so the digits line up down the panel
#: rather than the words in front of them. Right-aligned and not left, because a
#: column of `130` over `0` over `0.18` read from its left edge is three numbers
#: you have to measure before you can compare them.
#:
#: `TOTAL_RIGHT` is `INTERNAL_W - LEFT`, so the block is inset by the same margin
#: on both sides -- the same shape `shop_panel.TALLY_RIGHT` has.
BASE_RIGHT = 230
EARNED_RIGHT = 292
TOTAL_RIGHT = config.INTERNAL_W - LEFT

#: What sits over each column. Lower case and in the small font, because they are
#: read once on the way in and never again -- the rows are the content.
COLUMN_HEADS = (("class", BASE_RIGHT), ("earned", EARNED_RIGHT), ("total", TOTAL_RIGHT))


def values(run, name: str) -> tuple[int, int, int]:
    """The three numbers on one row: class, earned, total.

    Six of the eight rows are one field of `EntityType.attributes` beside the
    same field of `run.earned`. **Two are not, and both for the same reason: the
    class's own health and its own damage predate the attribute layer and live
    somewhere else.** `hp` is a field on `EntityType`; damage per swing is a
    field on a `Weapon`. Their attribute blocks carry only what is added on top.

    Read literally, those two rows print `Health 0 + 24 = 24` and
    `Damage 0 + 3 = 3` -- the first beside a HUD saying `154/154`, and the
    second for a Knight whose sword does twelve. That is not a rounding
    disagreement; it is the panel and the game meaning different things by one
    word, and it is worth noting that every hero in `data/entities.json` ships a
    fully neutral block, so without this the class column would be zeroes all
    the way down for every class in the game.

    So each of the two reads the figure that already means what the row means:

    - health: `EntityType.full_hp` and `Run.max_hp`, both of which exist because
      other callers needed exactly this sum;
    - damage: the **light attack**, plus `Attributes.damage`, which
      `combat.resolve_damage` adds flat to the rolled weapon number before the
      crit -- so the total is what a light swing hits for before variance.

    Light and not the heavy or the ultimate, and the choice is arbitrary only if
    you have not read `docs/balance.md`: slot 0 is the swing the game is measured
    on, the one the reference bot presses and the only one an advanced class
    inherits. It is also the one a player makes most. The other three are on
    screen as pips and are not attributes.

    Split out of the drawing so it can be asserted against `Run.max_hp` and the
    weapon table directly, headlessly, without a surface.
    """
    earned = getattr(run.earned, name)
    if name == "max_hp":
        return run.hero_type.full_hp, earned, run.max_hp
    if name == "damage":
        base = _light_damage(run.hero_type)
        return base, earned, base + earned
    base = getattr(run.hero_type.attributes, name)
    return base, earned, base + earned


def _light_damage(hero_type) -> int:
    """What the class's light attack hits for, plus whatever its block adds.

    Defensive about the slot for `hud._draw_skills`'s reason: a `World` can be
    built around any entity type -- the tools and half the tests do it -- and a
    panel that raised an IndexError on a body with no weapons would break every
    one of them.
    """
    weapons = hero_type.weapons
    light = weapons[skills.LIGHT].damage if len(weapons) > skills.LIGHT else 0
    return light + hero_type.attributes.damage


class HeroPanel:
    def __init__(self) -> None:
        self.title = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 16)
        self.small = pygame.font.Font(None, 13)

    def draw(self, surface: pygame.Surface, run) -> None:
        self._wash(surface)

        heading = self.title.render("THE HERO", False, config.ACCENT)
        surface.blit(heading, ((config.INTERNAL_W - heading.get_width()) // 2, TITLE_Y))

        # Left-aligned rather than centred, unlike the other three panels. The
        # column heads share this line, and a centred name grows towards them
        # from the middle -- so the longest class in the game would decide
        # whether the word "class" is legible.
        who = run.hero_type.name
        if run.hero_level > 1:
            # Hidden at level 1 for the HUD's reason: while
            # `data/progression.json` ships `xp_base: 0` the hero is level 1 for
            # the whole game, and a permanent "Lv 1" is a line that never once
            # says anything.
            who = f"{who}  --  Lv {run.hero_level}"
        surface.blit(self.font.render(who, False, config.WHITE), (LEFT, SUBTITLE_Y - 2))

        for head, right in COLUMN_HEADS:
            label = self.small.render(head, False, config.GREY)
            surface.blit(label, (right - label.get_width(), SUBTITLE_Y + 2))

        for index, name in enumerate(ROWS):
            self._row(surface, run, index, name)

        hint = self.small.render("I or Esc to close", False, config.GREY)
        surface.blit(
            hint, ((config.INTERNAL_W - hint.get_width()) // 2, hint_y(len(ROWS)))
        )

    def _wash(self, surface: pygame.Surface) -> None:
        """The same dim wash the other three panels use. The arena stays visible,
        which keeps this reading as a moment in a run rather than a screen."""
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((8, 8, 12, 220))
        surface.blit(wash, (0, 0))

    def _row(self, surface, run, index: int, name: str) -> None:
        y = ROW_Y + index * ROW_H
        base, earned, total = values(run, name)

        surface.blit(self.font.render(LABELS[name], False, config.WHITE), (LEFT, y))

        # The earned column is the only one that is ever coloured, and it is the
        # question the panel is open to answer. Grey at zero rather than hidden:
        # "this run has bought nothing towards Dodge" is an answer, and an empty
        # cell reads as a panel that failed to draw.
        cells = (
            (base, BASE_RIGHT, config.GREY),
            (earned, EARNED_RIGHT, config.GOOD if earned else config.GREY),
            (total, TOTAL_RIGHT, config.WHITE),
        )
        for value, right, colour in cells:
            text = self.small.render(format_value(name, value), False, colour)
            surface.blit(text, (right - text.get_width(), y + 3))
