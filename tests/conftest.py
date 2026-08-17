"""Test-wide setup.

The video driver is forced to `dummy` before any test can import pygame, so the
suite never opens a window -- on CI there is no display, and locally a window
stealing focus mid-run is its own kind of flakiness.

Note this only matters for the handful of render tests. Everything under `core/`
and `game/` is pygame-free by design and does not care.

The second fixture points every writable path at a temporary directory. Two
separate reasons, and the second is the one that would actually bite: a suite
that wrote to `state/` would leave a save file in the working tree after every
run, and -- worse -- `PlayScene` autosaves on stage entry, so running the tests
on a machine where somebody plays this game would overwrite their run with a
fixture's. A test may not cost a player their campaign.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Redirect the save, the settings and the profile into `tmp_path`.

    Autouse and function-scoped: every test gets an empty one, so no test can
    see what another left behind. `monkeypatch` puts the originals back, which
    matters because `config` is imported once and shared by the whole session.
    """
    from hack_and_slash import config

    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "SAVE_FILE", tmp_path / "save.json")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "PROFILE_FILE", tmp_path / "profile.json")
    return tmp_path
