"""Entry point.

    python main.py            play
    python main.py --smoke    pixel-fidelity check, no window
    python main.py --seed 7   play a specific run

Everything interesting lives in src/hack_and_slash/. This file only decides
which of them to start.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Top-down twin-stick hack and slash")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="check that sprites survive the upscale with hard edges, then exit",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="seed for the run; the same seed replays the same fight",
    )
    parser.add_argument(
        "--level",
        default="arena",
        help="name of a level in levels/ (without .json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.smoke:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        from hack_and_slash.scenes import smoke

        return smoke.run()

    import pygame

    from hack_and_slash import config
    from hack_and_slash.core import level_io
    from hack_and_slash.core.level_io import LevelFormatError
    from hack_and_slash.game.entities import load_bestiary
    from hack_and_slash.render.atlas import MissingAtlasError, load as load_atlas
    from hack_and_slash.scenes.base import App
    from hack_and_slash.scenes.menu import MenuScene

    level_path = config.LEVELS_DIR / f"{args.level}.json"
    if not level_path.exists():
        print(
            f"no level at {level_path} -- run `python tools/make_level.py` to build it",
            file=sys.stderr,
        )
        return 1

    try:
        level = level_io.load(level_path)
    except LevelFormatError as exc:
        print(f"cannot load {level_path.name}: {exc}", file=sys.stderr)
        return 1

    problems = level.problems()
    if problems:
        # Refuse rather than start a run that cannot be finished.
        print(f"{level_path.name} is not playable:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    bestiary = load_bestiary(config.ENTITIES_DATA, config.WEAPONS_DATA)

    # The display has to exist before the atlas, so surfaces can be converted to
    # the window's pixel format -- an unconverted blit costs more every frame.
    pygame.init()
    pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H), pygame.RESIZABLE)

    try:
        atlas = load_atlas()
    except MissingAtlasError as exc:
        pygame.quit()
        print(str(exc), file=sys.stderr)
        return 1

    App(MenuScene(level, bestiary, atlas, seed=args.seed)).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
