"""Loads `assets/sfx/` and plays cues by name.

Names, not paths, everywhere outside this module -- `audio/cues.py` decides that
a hit wants `"hit"`, and which file that is gets decided here. The same
arrangement `render/atlas.py` has with `config.SPRITE_ORDER`, for the same
reason: the generator and the loader agree through one tuple in `config.py`
rather than through a hunt for filenames.

**One thing here is deliberately unlike the atlas: nothing in this module ever
raises.** `atlas.load` refuses loudly on a missing PNG, and it is right to --
a game that cannot draw cannot run, so the only useful response is an error
naming the command that fixes it. Sound is not like that. No audio device, a
mixer SDL declined to open, `SDL_AUDIODRIVER=dummy` under the test suite, an
`assets/sfx/` nobody has generated yet: every one of those is a **quiet game**,
and none of them is a reason to stop. A player with no sound card still gets to
play, and the headless suite and `tools/screenshot.py` still run.

So every failure path in here ends at the same place -- a bank holding nothing,
whose `play` does nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pygame

from .. import config

#: How many cues may sound at once. The default is 8, which a twenty-enemy arena
#: can exhaust even after `Cues.drain` has collapsed a frame to one play per
#: name -- and an exhausted mixer drops whichever call arrives last rather than
#: whichever matters least, so the cue that goes missing is arbitrary.
CHANNELS = 16


class SoundBank:
    """The loaded cues, or none of them.

    A bank with an empty `sounds` is the silent case and is a perfectly ordinary
    thing to hold -- see the module docstring. `ok` is for tests and for the
    one-line report at startup; nothing in the game branches on it, because
    everything it would guard is already a no-op.
    """

    def __init__(self, sounds: Optional[dict[str, pygame.mixer.Sound]] = None) -> None:
        self.sounds: dict[str, pygame.mixer.Sound] = sounds or {}

    @property
    def ok(self) -> bool:
        return bool(self.sounds)

    def play(self, names: list[str], level: float = 1.0) -> None:
        """Play each named cue once, at `level` (0.0-1.0).

        Unknown names are ignored rather than raising. The caller is
        `audio/cues.py`, which can only produce names from `config.SOUND_NAMES`
        -- but a bank loaded against a half-generated `assets/sfx/` is exactly
        the silent-degradation case this module exists to handle, and crashing a
        run over a missing WAV would be the one outcome worse than not hearing it.

        Volume is set per play rather than once at load, because the options
        screen can move it while the game is running.
        """
        if not self.sounds or level <= 0.0:
            return

        for name in names:
            sound = self.sounds.get(name)
            if sound is None:
                continue
            sound.set_volume(level)
            # Returns None when every channel is busy. Nothing to do about that
            # and nothing worth saying: the cue that would have been dropped is
            # the sixteenth simultaneous one.
            sound.play()

    def stop(self) -> None:
        """Silence everything now. For leaving a run, not for pausing one."""
        if self.sounds and pygame.mixer.get_init() is not None:
            pygame.mixer.stop()


#: The silent bank, shared. Immutable in practice -- `play` on an empty bank
#: touches nothing -- so one instance serves every failure path.
SILENT = SoundBank()


def load(directory: Optional[Path] = None) -> SoundBank:
    """Read every cue in `config.SOUND_NAMES` off disk.

    Returns `SILENT` rather than raising on any of the four ways this can fail to
    produce sound. A cue whose file is missing is skipped and the rest still
    load, so a partly-generated directory is partly audible rather than silent.
    """
    if pygame.mixer.get_init() is None:
        # No mixer: either nobody called `pygame.mixer.init()` (a tool, a test,
        # a scene built directly) or SDL declined to open a device. Both are the
        # quiet case.
        return SILENT

    source = directory or config.SOUNDS_DIR
    if not source.is_dir():
        return SILENT

    sounds: dict[str, pygame.mixer.Sound] = {}
    for name in config.SOUND_NAMES:
        path = source / f"{name}.wav"
        if not path.exists():
            continue
        try:
            sounds[name] = pygame.mixer.Sound(str(path))
        except pygame.error:
            # A truncated or malformed WAV. One missing cue, not a dead game.
            continue

    if not sounds:
        return SILENT

    try:
        pygame.mixer.set_num_channels(CHANNELS)
    except pygame.error:
        # Keep whatever the mixer defaulted to. Fewer channels is a cue dropped
        # in a crowd, which is not worth refusing to make any sound at all over.
        pass

    return SoundBank(sounds)


#: Held for the life of the process. See `get`.
_bank: Optional[SoundBank] = None


def get() -> SoundBank:
    """The process-wide bank, loaded on first use.

    **Memoised rather than threaded through the scenes, which is how `Atlas` is
    handled, and the difference is deliberate.** The atlas is passed into every
    scene because it is needed at construction to draw; a scene without one
    cannot render a frame. The bank has no per-scene state, is never rebuilt, and
    is wanted by exactly one method on one scene -- so threading it would mean
    changing the signature of `PlayScene.__init__`, which `restarted()`,
    `tools/screenshot.py` and a large number of tests all call positionally.

    Decoding fourteen short WAVs is a few milliseconds and happens once, on the
    first frame that makes a noise rather than at startup.
    """
    global _bank
    if _bank is None:
        _bank = load()
    return _bank


def reset() -> None:
    """Drop the memo, so the next `get()` reloads.

    For tests, which need a bank built against a `tmp_path` and must not inherit
    one another's. Nothing in the game calls this.
    """
    global _bank
    _bank = None
