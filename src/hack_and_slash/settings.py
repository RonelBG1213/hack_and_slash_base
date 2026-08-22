"""What the player has chosen about how the game runs, and where it is kept.

Six values, and none of them may touch a fight. That is the whole design rule
here: `config.py` is what the game *is* and this is how one person likes looking
at it, so anything that would move a damage roll belongs in `data/`, behind a
tuning decision and a sweep, rather than behind a menu row.

The key bindings are the newest of the six and they follow the rule without
needing an argument: which key swings is not how hard the swing lands. They are
named actions from `bindings.py`, which is pure for the same reason this module
is -- see the note on `Settings.bindings`.

The difficulty tiers are that rule being followed, not broken: they are content
in `data/difficulty.json`, they are chosen once per run on the character select,
and they are nowhere in this dataclass. A `difficulty` field here would be a
preference that decides a fight -- which is exactly what the paragraph above
refuses.

The two effect toggles are safe by construction rather than by care --
`render/effects.py` is fed by events the sim emits and never reads back, and
`test_effects.py` runs the same seeded fight with the toggles both ways and
demands identical output. `seed` is the exception that proves the rule: it
chooses *which* fight, and choosing a fight is not changing one.

Pure Python. No pygame -- the window size is read from here *before* there is a
display to ask, which is the whole reason this is not in `render/`.

Named `settings` while the screen that edits it is `scenes/options.py`, for the
same reason `progression` is not `levels`: one word, one meaning, per project.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import bindings, config

#: `scale: 0` means "whatever the game shipped with". Stored as a sentinel
#: rather than by writing `DEFAULT_SCALE` into the file, so a settings file
#: written today follows the default if the default ever moves -- somebody who
#: never touched the row has expressed no opinion, and recording one for them
#: is how a preference file quietly outvotes the program.
AUTO_SCALE = 0

#: The scales the options screen offers. Whole numbers only: the upscale is
#: integer everywhere (`config.integer_scale`), and offering a fractional one
#: would put a smeared picture behind a menu row that promised otherwise.
SCALES = (2, 3, 4, 5, 6)


@dataclass
class Settings:
    """One player's preferences. Every field defaults to today's behaviour.

    Not frozen, unlike the content dataclasses -- the options screen edits a
    live instance and writes it on the way out, and a frozen one would mean
    rebuilding it on every keypress for no benefit.
    """

    #: Window scale, or `AUTO_SCALE` for `config.DEFAULT_SCALE`.
    scale: int = AUTO_SCALE
    fullscreen: bool = False

    #: The feel pass. Both default on, which is the game as it has always been.
    screenshake: bool = True
    damage_numbers: bool = True

    #: The seed the next run starts from, for players who do not use `--seed`.
    #: Zero is a real seed and the one the game has always defaulted to, so
    #: there is no sentinel here and none is wanted.
    seed: int = 0

    #: Which keys ask for which action, as `{action name: [key name]}` -- and
    #: **only the actions the player actually moved.** Empty is the whole game
    #: as it shipped, which is `AUTO_SCALE`'s rule applied a second time: an
    #: action nobody rebound has had no opinion expressed about it, and
    #: recording one anyway is how this file quietly outvotes `bindings.DEFAULTS`
    #: if a shipped key ever moves.
    #:
    #: Names rather than keycodes, and the reason is the paragraph at the top of
    #: this module -- `bindings.py` is pure for the same reason this is, so
    #: neither can name a `pygame.K_*`. `scenes/keymap.py` does the translation.
    #:
    #: This is a preference and it cannot decide a fight: which key swings is
    #: not how hard the swing lands. The line above holds.
    bindings: dict[str, list[str]] = field(default_factory=dict)

    @property
    def window_size(self) -> tuple[int, int]:
        """Pixel size of the window this asks for.

        Fullscreen ignores it -- the display driver picks -- but the value is
        still what the window returns to when fullscreen is switched off, so it
        is computed the same way in both cases.
        """
        scale = config.DEFAULT_SCALE if self.scale == AUTO_SCALE else self.scale
        return (config.INTERNAL_W * scale, config.INTERNAL_H * scale)


def _clean_bindings(value: object) -> dict[str, list[str]]:
    """Keep the entries that are shaped like bindings and drop the rest.

    Forgiving in the same way and for the same reason as the loader that calls
    it. Three ways this block can be wrong and none of them may stop the game:
    it is not a mapping at all, it names an action this build does not have (a
    file written by a later one), or a value is not a list of key names.

    Whether a name is a key *SDL knows* is deliberately not checked here -- that
    needs pygame, which this module may not import. `scenes/keymap.py` drops
    unresolvable names when it translates, so a binding written on another
    platform survives in the file and simply does not bind here.
    """
    if not isinstance(value, dict):
        return {}

    cleaned: dict[str, list[str]] = {}
    for action, keys in value.items():
        if action not in bindings.Action.__members__.values():
            continue
        if not isinstance(keys, list):
            continue
        named = [k for k in keys if isinstance(k, str) and k]
        if named:
            cleaned[str(action)] = named
    return cleaned


def load(path: Path | None = None) -> Settings:
    """Read the settings, falling back to defaults on anything unreadable.

    Deliberately forgiving, and it is the one place in this project that is.
    Content files (`data/*.json`, the campaign manifest) refuse loudly on a
    malformed field, because a typo in a damage number is a bug somebody has to
    see. This is not content: a half-written settings file -- a power cut during
    a write, an editor that mangled it -- must not stop the game starting. The
    worst case is that somebody sets their scale twice.

    Unknown keys are dropped and missing ones keep their default, so a file
    written by an older or newer build still loads.
    """
    source = path or config.SETTINGS_FILE
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()

    if not isinstance(payload, dict):
        return Settings()

    known = {f.name: f.type for f in fields(Settings)}
    accepted: dict[str, object] = {}
    for name, value in payload.items():
        if name not in known:
            continue
        # One coercion per field type rather than trusting the JSON: a `scale`
        # of "3" or of true would otherwise reach `window_size` and multiply.
        if name in ("fullscreen", "screenshake", "damage_numbers"):
            if isinstance(value, bool):
                accepted[name] = value
        elif name == "bindings":
            accepted[name] = _clean_bindings(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            accepted[name] = value

    return Settings(**accepted)


def save(settings: Settings, path: Path | None = None) -> None:
    """Write the settings, creating `state/` if this is the first time.

    Silent on failure for the same reason `load` is forgiving: a read-only
    directory is a reason for a preference not to stick, and not a reason for
    the game to stop.
    """
    target = path or config.SETTINGS_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    except OSError:
        pass
