"""The colours a player reads a *fact* off, and the one alternate set of them.

`config.py` holds the whole palette and this module holds the part of it that
carries meaning. The difference is the entire design here, so it is worth being
exact about: `WHITE`, `GREY`, `DARK`, `PANEL` and `ACCENT` are decoration -- they
separate on lightness, they say "this row is selected" or "this is a panel", and
a player who cannot tell red from green reads every one of them correctly. The
seven values below are the ones that answer a question by hue alone: *how badly
am I hurt*, *was that damage mine*, *how good is that thing on the floor*.

**Only those move.** Routing all 136 `config.<COLOUR>` sites through an
indirection is the refactor `docs/roadmap.md` prices under Localisation, and it
would buy nothing here -- the four call sites that matter are the hero's health
bar, the enemy pip, the damage numbers and the rarity ladder.

`SHIPPED` is not "the default palette", it is **the game as it draws today**,
field for field, and `test_effects.py` asserts that against `config` rather than
trusting this file. That is what makes the row's "off" position mean off: a
future tune of `config.BAD` that forgot this module would fail a test rather than
quietly leaving the shipped palette pointing at last month's red.

`COLOURBLIND` is Okabe-Ito, the set drawn for exactly this and unambiguous under
deuteranopia and protanopia. One alternate rather than one per deficiency: what
the shipped green-amber-red ladder and the grey-green-blue-purple-orange loot
ladder both fail is red-green, which is the great majority of the affected
population, and two red-green palettes would differ from each other far less than
either differs from the set they replace. `BY_NAME` exists so a third is a table
entry rather than a change of shape.

Pure Python, and it imports only `config` -- for the same reason `settings.py`
does. That module has to hold the player's choice and it may never see pygame, so
the palettes cannot live in `render/`.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config


@dataclass(frozen=True)
class Palette:
    """One coherent set of the colours that mean something.

    Frozen, unlike `Settings` and like every content dataclass in `data/`: this
    is a fact about how the game looks, not a preference being edited. The
    screen picks *which* palette, never what is in one.
    """

    #: What `settings.colourblind` resolves to, and the key into `BY_NAME`.
    name: str

    #: The health ladder, in the order a run walks down it. `good` also colours
    #: the "+" pip on the HUD and an earned attribute on the character sheet.
    good: tuple[int, int, int]
    caution: tuple[int, int, int]
    #: Danger on the hero's bar, and every enemy's health pip.
    bad: tuple[int, int, int]
    #: The other half of the danger pulse -- `bad` lightened, but by eye rather
    #: than by arithmetic, so it is a field rather than a function of `bad`.
    #: The shipped pair is (198,84,78) and (240,140,130): a linear blend toward
    #: white that reached 240 red would put green at 210, not 140. There is no
    #: formula that reproduces today's bar, and reproducing it exactly is the
    #: whole job of the shipped palette.
    bad_pulse: tuple[int, int, int]

    #: A floating number's colour, which answers "was that me?" without the
    #: player reading the number.
    hurt_number: tuple[int, int, int]
    dealt_number: tuple[int, int, int]

    #: The rim on a champion. Its own field rather than a reuse of `caution`,
    #: because the two answer different questions on the same screen -- one is
    #: "this bar is getting low" and the other is "that monster is not the
    #: monster beside it" -- and a palette that wanted to separate them could
    #: not if they were one value.
    champion: tuple[int, int, int]

    #: Keyed by `loot.Rarity.value`, exactly as `config.RARITY_COLORS` is, so a
    #: tier added to `data/loot.json` is one entry in each palette and nothing
    #: else. Keyed by the string and not the enum because this module imports
    #: nothing from `game/`.
    rarity: dict[str, tuple[int, int, int]]


#: The game as it draws today. Every field is either a `config` constant or one
#: of the two literals `render/effects.py` used to hold, so switching the row off
#: is not "a palette that resembles the old one" -- it is the old one.
SHIPPED = Palette(
    name="shipped",
    good=config.GOOD,
    caution=config.ACCENT,
    bad=config.BAD,
    bad_pulse=(240, 140, 130),
    # These two lived inline in `Effects._add_number`. Moved rather than
    # copied: a second red in a second place is how the damage numbers end up
    # disagreeing with the health bar about what "hurt" looks like.
    hurt_number=(232, 106, 96),
    dealt_number=(240, 236, 220),
    # Violet: the one hue nothing else on the arena floor uses, so a rim in it
    # cannot be read as low health, as a telegraph or as a rarity.
    champion=(186, 132, 232),
    rarity=dict(config.RARITY_COLORS),
)

#: Okabe-Ito. The health ladder becomes blue -> yellow -> vermillion, which is
#: three unmistakable steps under every common deficiency *and* under none.
#:
#: The rarity ladder is the harder half and is built to separate on **lightness
#: as well as hue**, because it is read off a 16px relic on a dark floor rather
#: than off a bar. Grey is kept: common is supposed to look unremarkable, and it
#: is the one rung whose meaning is "nothing special" rather than a position.
COLOURBLIND = Palette(
    name="colourblind",
    good=(86, 180, 233),
    caution=(240, 228, 66),
    bad=(213, 94, 0),
    bad_pulse=(255, 168, 82),
    # Warm against the pale one, and the same warmth as `bad` above, so "that
    # was me" reads the same on the bar and in the air.
    hurt_number=(230, 130, 60),
    dealt_number=(240, 236, 220),
    # Okabe-Ito's reddish purple, which is the ring's hue under every common
    # deficiency and is not `bad` above.
    champion=(204, 121, 167),
    rarity={
        "common": (170, 176, 188),
        "uncommon": (86, 180, 233),
        "rare": (240, 228, 66),
        "epic": (204, 121, 167),
        "legendary": (213, 94, 0),
    },
)

#: Both, by `name`. The options screen stores a bool and `for_settings` below is
#: the only translation, but a run through this map is what makes a third
#: palette a table entry.
BY_NAME = {p.name: p for p in (SHIPPED, COLOURBLIND)}


def for_settings(colourblind: bool) -> Palette:
    """The palette a `Settings` asks for.

    One function rather than the caller writing the conditional, so the four
    render objects that hold a palette cannot come to disagree about which one
    `colourblind=True` means.
    """
    return COLOURBLIND if colourblind else SHIPPED
