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
        default=None,
        help="seed for the run; the same seed replays the same fight. Overrides "
        "the seed set in the options screen, and defaults to it when absent",
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

    from hack_and_slash import config, settings as settings_module
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

    # Advanced classes are accepted here and nowhere else. They are kept out of
    # `hero_classes` on purpose -- that is what keeps them off the character
    # select, which is laid out for five columns -- but half the campaign is
    # fought as one, and `--stage 36` is useless if the only way to reach that
    # stage as the hero who belongs there is to play thirty-five stages first.
    # A tuning flag, like `--stage` beside it.
    roster = [c.id for c in bestiary.hero_classes]
    playable = roster + [c.id for c in bestiary.advanced_classes]
    if args.hero is not None and args.hero not in playable:
        print(
            f"--class must be one of: {', '.join(playable)}",
            file=sys.stderr,
        )
        return 1

    # Read before the window is opened, because it is what decides how big the
    # window is. Never fails: a settings file that cannot be read comes back as
    # the defaults rather than as an exception -- see `settings.load`.
    settings = settings_module.load()

    # `--seed` beats the stored one, and the flag defaults to None rather than
    # to 0 so that "not passed" and "passed --seed 0" are different things.
    # Zero is a real seed and the one the game shipped defaulting to, so a flag
    # defaulting to 0 would silently overrule a seed set on the options screen.
    seed = args.seed if args.seed is not None else settings.seed

    # Asked for before `pygame.init()`, because that is the only moment the
    # mixer takes these numbers -- afterwards it has already opened a device
    # with its own. They are `config.SOUND_RATE`, signed 16-bit and mono
    # because that is exactly what `tools/gen_sfx.py` writes, so nothing is
    # resampled or converted between the file and the speaker.
    #
    # The buffer is the one number not taken from the files. 512 frames is
    # about 12ms at 44100; pygame's default of 4096 is about 93ms, which is
    # late enough that a swing sounds like a reply to itself.
    #
    # Wrapped because a machine with no audio device must still reach the
    # menu. `pygame.init()` below tolerates a mixer that failed to open, and
    # `audio/bank.load` treats an uninitialised mixer as the quiet case, so
    # the whole failure path here is one silent game rather than an error.
    try:
        pygame.mixer.pre_init(config.SOUND_RATE, -16, 1, 512)
    except pygame.error:
        pass

    # The display has to exist before the atlas, so surfaces can be converted to
    # the window's pixel format -- an unconverted blit costs more every frame.
    pygame.init()
    if settings.fullscreen:
        pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        pygame.display.set_mode(settings.window_size, pygame.RESIZABLE)

    try:
        atlas = load_atlas()
    except MissingAtlasError as exc:
        pygame.quit()
        print(str(exc), file=sys.stderr)
        return 1

    def home() -> MenuScene:
        """A fresh title screen. Every route back here goes through this.

        Rebuilt rather than held, because the menu reads the save file when it
        is constructed -- a `MenuScene` kept across a run that just ended would
        go on offering a Load Game row for a run that has been deleted.
        """
        return MenuScene(campaign, bestiary, atlas, seed=seed, settings=settings)

    if args.hero is not None:
        # Naming a class means skipping the screen whose only job is to ask for
        # one. Straight into the fight, which is the point of the flag.
        from hack_and_slash.scenes.play import PlayScene

        App(
            PlayScene(
                campaign,
                bestiary,
                atlas,
                seed=seed,
                start_stage=args.stage - 1,
                hero_type_id=args.hero,
                settings=settings,
                on_exit=home,
            ),
            settings=settings,
        ).run()
    elif args.stage > 1:
        # Skip the title screen when jumping to a stage -- the only reason to
        # pass --stage is to look at that stage. The character select still
        # happens: the stage is chosen, the class is not.
        App(home()._start_at(args.stage - 1), settings=settings).run()
    else:
        App(home(), settings=settings).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
