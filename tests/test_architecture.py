"""Guards the one structural rule the whole project depends on:

`hack_and_slash.core.*` and `hack_and_slash.game.*` must never import pygame.

Two things ride on this. First, the entire logic layer -- movement, collision,
hit resolution, AI -- runs headless under pytest with no window and no SDL.
Second, the eventual port to a real engine is only affordable while the
interesting code is plain arithmetic on plain data. The day someone imports
pygame into core/ for a quick convenience, this test fails and says so.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
PURE_PACKAGES = ("core", "game")

#: Pure modules that sit at the top of the package rather than inside one of the
#: pure packages, so the glob below cannot find them. Named one by one and
#: deliberately short: a module belongs here only if it must be readable with no
#: display in existence.
#:
#: `config` is the constants everything reads. `settings` is the player's
#: preferences, and it is on this list because the window size is read from it
#: *before* there is a window to ask -- the moment it imports pygame, `main.py`
#: can no longer decide how big to open the display.
PURE_MODULES = ("config", "settings")


def _pure_modules() -> list[str]:
    names = [f"hack_and_slash.{stem}" for stem in PURE_MODULES]
    for package in PURE_PACKAGES:
        for path in sorted((SRC / "hack_and_slash" / package).glob("*.py")):
            if path.stem == "__init__":
                continue
            names.append(f"hack_and_slash.{package}.{path.stem}")
    return names


def test_logic_layer_imports_without_pygame() -> None:
    modules = _pure_modules()
    if not modules:
        # Legitimate only at step 1, before core/ has anything in it. Once a
        # single logic module exists this branch is unreachable, so the guard
        # cannot rot into a permanent silent skip.
        pytest.skip("no logic modules yet -- core/ and game/ are still empty")

    # A subprocess gives a clean interpreter: no other test can have imported
    # pygame first and masked the dependency we are looking for.
    script = (
        "import sys, importlib\n"
        "sys.modules['pygame'] = None\n"  # makes `import pygame` raise ImportError
        f"for name in {modules!r}:\n"
        "    try:\n"
        "        importlib.import_module(name)\n"
        "    except ImportError as exc:\n"
        "        if 'pygame' in str(exc):\n"
        "            print('PYGAME_LEAK', name, exc)\n"
        "            sys.exit(1)\n"
        "        raise\n"
        "print('CLEAN')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(SRC),
    )
    assert result.returncode == 0, (
        "a pure-logic module imports pygame:\n"
        f"{result.stdout}{result.stderr}\n"
        "Move the pygame code into render/ or scenes/."
    )
    assert "CLEAN" in result.stdout
