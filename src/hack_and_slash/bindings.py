"""What the player asked for, named -- and which keys currently ask for it.

The keyboard half of the `Intent` seam. `game/intent.py` says what a body wants
to do this tick; this says what a *player* can ask for and what they press to
ask it. Nothing here reaches the sim: an `Action` is resolved to keycodes by
`scenes/keymap.py` and turned into an `Intent` by `scenes/play.py`, and the two
layers below that never learn a key was involved.

**Pure, and on `test_architecture.py`'s list for the same reason `settings` is.**
The bindings live on `Settings`, `Settings` is read before there is a display to
ask, and the moment either module imports pygame `main.py` can no longer decide
how big to open the window. That is the whole reason a binding is stored as a
key *name* rather than as a `pygame.K_*` integer -- `K_LSHIFT` is 1073742049,
which is a number nobody can read in a settings file or a diff, and which this
module could not name without the import it is forbidden.

The names are SDL's own, round-tripped by `pygame.key.key_code` and
`pygame.key.name`. `scenes/keymap.py` owns that translation and is the only
place that needs pygame to do it.

Two things are deliberately not here, and both are recorded in `docs/limits.md`
rather than left to be rediscovered as gaps:

* **the menu and panel keys** -- Escape, Enter and the digits that buy at a
  stall, spend at a shrine and choose at the fork. They are what a player uses
  to reach this screen and to leave it, and one of them bound to a swing is how
  somebody locks themselves out of the game;
* **the mouse buttons.** Left click swings and right click rolls, as they always
  have. A button is not a key and this module does not model one.
"""

from __future__ import annotations

from enum import StrEnum


class Action(StrEnum):
    """Something a player can ask for, independent of what asks it.

    A `StrEnum` because the value is what lands in `state/settings.json`, and a
    settings file reading `"dodge"` is one somebody can fix by hand where one
    reading `8` is not. The same argument as the key names above, one level up.

    This is also the list a controller would bind to. Nothing here mentions a
    keyboard, which is the property that makes the second device a second
    binding table rather than a second refactor -- see `docs/roadmap.md`, where
    rebinding and the controller are one item for exactly this reason.
    """

    MOVE_UP = "move_up"
    MOVE_DOWN = "move_down"
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    ATTACK = "attack"
    NEUTRAL = "neutral"
    HEAVY = "heavy"
    ULTIMATE = "ultimate"
    DODGE = "dodge"
    SHEET = "sheet"
    RESTART = "restart"


#: What each action is called on the rebinding screen. Prose rather than the
#: slot's internal name -- `skills.HEAVY` is index 2 to the sim and "Heavy
#: attack" to the person deciding which key to put it on.
LABELS: dict[Action, str] = {
    Action.MOVE_UP: "Move up",
    Action.MOVE_DOWN: "Move down",
    Action.MOVE_LEFT: "Move left",
    Action.MOVE_RIGHT: "Move right",
    Action.ATTACK: "Light attack",
    Action.NEUTRAL: "Class buff",
    Action.HEAVY: "Heavy attack",
    Action.ULTIMATE: "Ultimate",
    Action.DODGE: "Dodge roll",
    Action.SHEET: "Character sheet",
    Action.RESTART: "Restart the run",
}


#: The keys the game has always shipped with, as SDL names.
#:
#: This tuple is the claim that rebinding moved nothing for a player who never
#: opens the screen, and `test_bindings.py` asserts it against the sets
#: `scenes/play.py` carried as module constants before this existed.
#:
#: The reasoning behind the choices, carried here from those constants because
#: it is design intent rather than a detail of where the table happened to live:
#:
#: * **The three skills sit under the left hand**, on keys it can reach without
#:   leaving WASD -- the right hand is on the mouse and aiming, so it has
#:   nothing spare.
#: * **`r` is not among them.** It is already "restart the run", and quietly
#:   rebinding it would cost somebody a run. It is on this list so a player can
#:   move it *deliberately*, which is the opposite thing.
#: * **Light attack has a keyboard alternate (`j`) and the skills do not.** It
#:   predates the skills and somebody may be playing keyboard-only; inventing a
#:   parallel binding for every slot would be three more things to document and
#:   three more chances for two of them to disagree.
#:
#: Insertion order is the order the rows are drawn, so this is also the screen's
#: layout: the four directions, the four attacks, the roll, then the two that
#: are not combat at all.
DEFAULTS: dict[Action, tuple[str, ...]] = {
    Action.MOVE_UP: ("w", "up"),
    Action.MOVE_DOWN: ("s", "down"),
    Action.MOVE_LEFT: ("a", "left"),
    Action.MOVE_RIGHT: ("d", "right"),
    Action.ATTACK: ("j",),
    Action.NEUTRAL: ("q",),
    Action.HEAVY: ("e",),
    Action.ULTIMATE: ("f",),
    Action.DODGE: ("space", "left shift", "right shift"),
    Action.SHEET: ("i", "tab"),
    Action.RESTART: ("r",),
}


def resolve(overrides: dict[str, list[str]] | None) -> dict[Action, tuple[str, ...]]:
    """The bindings in force: what the player changed, over what shipped.

    `overrides` is sparse on purpose -- `Settings.bindings` records only the
    actions somebody actually moved. That is `AUTO_SCALE`'s rule a second time
    (see `settings.py`): a player who never touched a row has expressed no
    opinion about it, and writing one down for them is how a preference file
    quietly outvotes the program. If the shipped key for the roll ever moves,
    everybody who never rebound the roll moves with it.

    Forgiving in the two ways the file it comes from can be wrong. An action
    this build does not know is dropped -- a settings file from a later build
    must not stop this one starting. An action bound to *nothing* falls back to
    its default rather than being left unreachable, because an attack with no
    key is an attack the player cannot use and no screen here can produce one.
    """
    resolved = dict(DEFAULTS)
    for name, keys in (overrides or {}).items():
        try:
            action = Action(name)
        except ValueError:
            continue
        if keys:
            resolved[action] = tuple(keys)
    return resolved
