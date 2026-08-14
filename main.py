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
        "--stage",
        type=int,
        default=1,
        help="start at this stage (1-based). For tuning -- you arrive at full "
        "health, so it is not the same fight as reaching it through a run",
    )
    parser.add_argument(
        "--class",
        dest="hero",
        default=None,
        help="skip the character select and play this class. For tuning; the "
        "normal way in is to pick one on the screen that exists for it",
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
    from hack_and_slash.core import campaign_io
    from hack_and_slash.core.campaign_io import CampaignFormatError
    from hack_and_slash.game.entities import load_bestiary
    from hack_and_slash.render.atlas import MissingAtlasError, load as load_atlas
    from hack_and_slash.scenes.base import App
    from hack_and_slash.scenes.menu import MenuScene

    try:
        campaign = campaign_io.load(config.LEVELS_DIR / "campaign.json")
    except CampaignFormatError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    problems = campaign.problems()
    if problems:
        # Refuse rather than start a run that cannot be finished -- possibly
        # several stages after the mistake.
        print("the campaign is not playable:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    if not 1 <= args.stage <= len(campaign):
        print(
            f"--stage must be between 1 and {len(campaign)}", file=sys.stderr
        )
        return 1

    bestiary = load_bestiary(config.ENTITIES_DATA, config.WEAPONS_DATA)

    roster = [c.id for c in bestiary.hero_classes]
    if args.hero is not None and args.hero not in roster:
        print(
            f"--class must be one of: {', '.join(roster)}",
            file=sys.stderr,
        )
        return 1

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

    menu = MenuScene(campaign, bestiary, atlas, seed=args.seed)

    if args.hero is not None:
        # Naming a class means skipping the screen whose only job is to ask for
        # one. Straight into the fight, which is the point of the flag.
        from hack_and_slash.scenes.play import PlayScene

        App(
            PlayScene(
                campaign,
                bestiary,
                atlas,
                seed=args.seed,
                start_stage=args.stage - 1,
                hero_type_id=args.hero,
                on_exit=lambda: MenuScene(campaign, bestiary, atlas, seed=args.seed),
            )
        ).run()
    elif args.stage > 1:
        # Skip the title screen when jumping to a stage -- the only reason to
        # pass --stage is to look at that stage. The character select still
        # happens: the stage is chosen, the class is not.
        App(menu._start_at(args.stage - 1)).run()
    else:
        App(menu).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
