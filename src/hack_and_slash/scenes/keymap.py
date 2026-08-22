"""Key names in, pygame keycodes out -- and the rules about what may be bound.

The translation layer between `bindings.py`, which is pure and stores SDL key
*names*, and everything that has to compare against a real `event.key`. This is
the only module in the project that needs pygame in order to answer "which key
is that", which is exactly why it is here and not there.

Not a `Scene`, in a package full of them. `scenes/smoke.py` is not one either:
the package is "the pygame-facing half of the front end", and the base class is
what most of it happens to be.

Three jobs, and the third is the interesting one:

* **`keycodes`** -- what `scenes/play.py` compares an `event.key` against.
* **`label`** -- what the HUD pips and the panel hints *print*. One source, so a
  pip cannot go on saying Q after the buff moved to C.
* **`assign`** -- the rules. A rebinding screen that accepted anything would let
  a player put a swing on Escape and lock themselves out of the screen they were
  standing on, or strand an attack on no key at all.
"""

from __future__ import annotations

import pygame

from ..bindings import DEFAULTS, LABELS, Action, resolve
from ..settings import Settings

#: Keys this screen refuses to hand out, by name.
#:
#: Not a style rule -- each of these is load-bearing somewhere a rebinding screen
#: cannot reach. Escape leaves every screen in the game and closes the shop, the
#: sheet and the level panel. Return and the keypad's Enter dismiss all three and
#: take a row on the menu. Backspace edits the seed on the Settings screen. One
#: to eight buy at a stall (`render/shop_panel.py`), spend at a shrine
#: (`render/level_panel.py`) and choose a path at the fork
#: (`render/job_panel.py`), and none of those three panels has anywhere else to
#: put a digit.
#:
#: **Space is deliberately not here, and it is the interesting omission.** It
#: confirms on the menu *and* it is the shipped dodge key, which works because
#: the arena and the panels are never taking keys at the same moment. Reserving
#: it would mean refusing the game's own default.
RESERVED = frozenset(
    {"escape", "return", "enter", "backspace"} | {str(digit) for digit in range(1, 9)}
)


def name_of(key: int) -> str | None:
    """What to write in the settings file for a key that was just pressed.

    `None` when the name does not survive the trip back, which is the only
    honest answer: a binding that cannot be re-read is one that works until the
    game is restarted and then silently does not. Rare -- every key on an
    ordinary board round-trips -- but a settings file is forever and this check
    costs one comparison at the moment somebody presses a key.
    """
    label = pygame.key.name(key)
    if not label:
        return None
    try:
        return label if pygame.key.key_code(label) == key else None
    except ValueError:
        return None


def keycodes(settings: Settings) -> dict[Action, tuple[int, ...]]:
    """The bindings in force, as the integers `event.key` actually carries.

    Names SDL does not know are dropped rather than raised on -- a settings file
    written on another platform, or by another pygame, must not stop the scene
    being built. An action left with nothing after that falls back to its
    default, for the reason `bindings.resolve` gives: an attack with no key is
    an attack the player cannot reach, and no screen here can produce one.
    """
    codes: dict[Action, tuple[int, ...]] = {}
    for action, names in resolve(settings.bindings).items():
        resolved = tuple(code for code in map(_code, names) if code is not None)
        if not resolved:
            resolved = tuple(
                code for code in map(_code, DEFAULTS[action]) if code is not None
            )
        codes[action] = resolved
    return codes


def _code(name: str) -> int | None:
    try:
        return pygame.key.key_code(name)
    except ValueError:
        return None


def label(action: Action, settings: Settings) -> str:
    """The key to print for an action -- the first one bound to it.

    A single character comes back upper case and everything else comes back as
    SDL names it, which is what makes this read as Q, F, space and left shift
    rather than as a mixture. The HUD pips and the two panel hints all come
    through here, so what the game says and what it listens to cannot drift
    apart.
    """
    names = resolve(settings.bindings)[action]
    return pretty(names[0]) if names else "--"


def pretty(name: str) -> str:
    return name.upper() if len(name) == 1 else name


def describe(action: Action, settings: Settings) -> str:
    """Every key bound to an action, for the rebinding screen's own column."""
    names = resolve(settings.bindings)[action]
    return "  ".join(pretty(name) for name in names) if names else "--"


def assign(settings: Settings, action: Action, name: str) -> str | None:
    """Put `name` on `action`. Returns `None`, or why it was refused.

    Three rules, in the order they are checked:

    1. **A reserved key is refused**, naming it -- see `RESERVED`.
    2. **Otherwise the key is taken** from whatever else held it. Two actions
       sharing a key is not a conflict the sim could resolve: the arena reads
       both tables on the same `event.key` and both would fire.
    3. **Unless taking it would leave that other action with nothing**, in which
       case the whole assignment is refused and says which action it would have
       stranded. Better to tell somebody they must move the buff first than to
       hand them a build with an attack they cannot press.

    On success the action's keys are **replaced**, not added to -- so binding
    Move up to `up` drops `w` from it. That is the rule that keeps the screen
    honest: a row shows what it is bound to, and after a rebind it shows one
    key, which is the one that was just pressed. Reset puts the alternates back.

    Mutates `settings.bindings` in place. The screen writes it on the way out,
    the way `scenes/options.py` writes the rest.
    """
    if name in RESERVED:
        return f"{pretty(name)} is reserved"

    current = resolve(settings.bindings)

    stripped: dict[Action, list[str]] = {}
    for other, names in current.items():
        if other == action or name not in names:
            continue
        remaining = [key for key in names if key != name]
        if not remaining:
            return f"{pretty(name)} is the only {LABELS[other]} key"
        stripped[other] = remaining

    for other, remaining in stripped.items():
        settings.bindings[str(other)] = remaining
    settings.bindings[str(action)] = [name]
    return None


def reset(settings: Settings) -> None:
    """Back to what shipped, by forgetting rather than by writing.

    Cleared rather than filled with `DEFAULTS`, and the difference matters the
    day a shipped key moves: a player who has reset has expressed no opinion
    again, exactly as they had before they ever opened the screen. Writing the
    defaults down would freeze today's answer into their settings file forever.
    """
    settings.bindings.clear()
