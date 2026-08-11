"""Renders a scene to a PNG with no window open.

    python tools/screenshot.py play out.png
    python tools/screenshot.py menu out.png
    python tools/screenshot.py play out.png --ticks 240 --scale 3

The point is being able to see a change without launching the game -- on a
headless machine, over a remote session, or from a test. `--ticks` runs the
fight forward first, with the hero holding a scripted input, so a screenshot can
show a real fight in progress rather than the opening frame of an empty arena.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from hack_and_slash import config  # noqa: E402
from hack_and_slash.core import campaign_io  # noqa: E402
from hack_and_slash.core.vec2 import Vec2  # noqa: E402
from hack_and_slash.game.entities import load_bestiary  # noqa: E402
from hack_and_slash.game.intent import Intent  # noqa: E402
from hack_and_slash.game.sim import step  # noqa: E402
from hack_and_slash.render.atlas import load as load_atlas  # noqa: E402
from hack_and_slash.scenes.menu import MenuScene  # noqa: E402
from hack_and_slash.scenes.play import PlayScene  # noqa: E402


def build_scene(name: str, campaign, bestiary, atlas, seed: int, stage: int):
    if name == "menu":
        return MenuScene(campaign, bestiary, atlas, seed=seed)
    if name == "play":
        return PlayScene(campaign, bestiary, atlas, seed=seed, start_stage=stage)
    raise SystemExit(f"unknown scene '{name}' -- try 'play' or 'menu'")


def advance(scene: PlayScene, ticks: int) -> None:
    """Run the fight forward so the shot shows something happening.

    The hero walks right and swings the whole time. Crude, but it puts enemies
    in motion, opens hitboxes and produces damage numbers -- which is what a
    screenshot of a combat game needs to show.
    """
    intent = Intent(move=Vec2(1, 0), aim=Vec2(1, 0), attack=True)
    for _ in range(ticks):
        step(scene.world, intent)
        scene.effects.feed(scene.world.drain_events(), scene.world.hitstop)
        scene.effects.tick()
        hero = scene.world.hero
        if hero is not None:
            scene.camera.follow(hero.pos)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", choices=("play", "menu"))
    parser.add_argument("output")
    parser.add_argument("--ticks", type=int, default=0, help="simulate this long first")
    parser.add_argument("--scale", type=int, default=3, help="upscale factor for the PNG")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--stage", type=int, default=1, help="1-based stage to shoot")
    args = parser.parse_args()

    pygame.init()
    # A dummy display still has to exist for font rendering and conversion.
    pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))

    campaign = campaign_io.load(config.LEVELS_DIR / "campaign.json")
    bestiary = load_bestiary(config.ENTITIES_DATA, config.WEAPONS_DATA)
    atlas = load_atlas()

    stage = max(0, min(args.stage - 1, len(campaign) - 1))
    scene = build_scene(args.scene, campaign, bestiary, atlas, args.seed, stage)
    if args.ticks and isinstance(scene, PlayScene):
        advance(scene, args.ticks)

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.draw(surface)

    if args.scale > 1:
        surface = pygame.transform.scale(
            surface,
            (config.INTERNAL_W * args.scale, config.INTERNAL_H * args.scale),
        )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(out))
    pygame.quit()

    print(f"wrote {out}  ({surface.get_width()}x{surface.get_height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
