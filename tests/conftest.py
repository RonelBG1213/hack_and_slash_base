"""Test-wide setup.

The video driver is forced to `dummy` before any test can import pygame, so the
suite never opens a window -- on CI there is no display, and locally a window
stealing focus mid-run is its own kind of flakiness.

Note this only matters for the handful of render tests. Everything under `core/`
and `game/` is pygame-free by design and does not care.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
