"""Writes the four stages and the campaign manifest that orders them.

There is no level editor -- that was a deliberate scope cut. This script is the
compromise: a stage is described here as a size, a list of pillar rectangles and
a list of enemies, which is far easier to get right than counting characters in a
wall of ASCII. The output is plain readable JSON, so a small tweak can be made in
the file directly without coming back here.

    python tools/make_level.py

The curve is the point of this file. Stage 1 teaches you that things walk at you.
Stage 2 adds something that shoots, so pillars start mattering. Stage 3 is the
full mix in the arena the game was originally tuned around. Stage 4 is the boss.
Health carries between them, so the numbers here are not four independent fights
-- they are one run, and stage 4 is fought at whatever you have left.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hack_and_slash import config  # noqa: E402
from hack_and_slash.core import campaign_io, level_io  # noqa: E402
from hack_and_slash.core.campaign import Campaign  # noqa: E402
from hack_and_slash.core.level import FLOOR, WALL, EnemySpawn, Level  # noqa: E402


@dataclass(frozen=True)
class Stage:
    """One arena, described the way a person would draw it on paper.

    `pillars` are (x, y, w, h) rectangles of wall in tiles. They exist to break
    line of sight so archers are a positioning problem rather than a damage tax,
    to give chargers something to miss you into, and to stop an arena reading as
    an empty box. Deliberately fat -- one-tile pillars vanish behind a sprite.

    **The constraint that is easy to get wrong:** nothing in this game paths
    around walls. Enemies walk straight at you. So a pillar that seals off a
    lane does not make a stage more interesting, it strands whatever is behind
    it -- and the player has to go and fetch a grunt that has spent the fight
    pushing into a wall. Keep pillars clear of the lanes between the hero spawn
    and the enemies, especially on the sparse early stages where one stuck enemy
    is the difference between a stage ending and not.
    """

    name: str
    filename: str
    width: int
    height: int
    hero: tuple[int, int]
    enemies: list[EnemySpawn]
    pillars: list[tuple[int, int, int, int]] = field(default_factory=list)

    def build(self) -> Level:
        grid = [[FLOOR] * self.width for _ in range(self.height)]

        for x in range(self.width):
            grid[0][x] = WALL
            grid[self.height - 1][x] = WALL
        for y in range(self.height):
            grid[y][0] = WALL
            grid[y][self.width - 1] = WALL

        for px, py, pw, ph in self.pillars:
            for y in range(py, py + ph):
                for x in range(px, px + pw):
                    grid[y][x] = WALL

        return Level(
            name=self.name,
            rows=tuple("".join(row) for row in grid),
            hero_spawn=self.hero,
            enemy_spawns=tuple(self.enemies),
            tile=config.TILE,
        )


def spawns(*entries: tuple[str, int, int]) -> list[EnemySpawn]:
    return [EnemySpawn(kind, (x, y)) for kind, x, y in entries]


STAGES = [
    # --- 1 -------------------------------------------------------------------
    # Small, open, grunts only. Teaches the swing and that things walk at you.
    # Pillars kept small and pushed to the edges: with four enemies and no
    # pathfinding, one stranded behind a wall is a stage that never ends. An
    # earlier draft put a three-tile pillar squarely on the hero's row and the
    # last grunt spent nine thousand ticks pressed against the far side of it.
    Stage(
        name="The Yard",
        filename="stage1.json",
        width=28,
        height=18,
        hero=(3, 9),
        pillars=[(7, 3, 2, 2), (7, 13, 2, 2), (19, 3, 2, 2), (19, 13, 2, 2)],
        enemies=spawns(
            ("grunt", 14, 9),
            ("grunt", 20, 7),
            ("grunt", 20, 11),
            ("grunt", 24, 9),
        ),
    ),
    # --- 2 -------------------------------------------------------------------
    # Archers arrive, and with them the reason pillars exist. The first charger
    # too, in the open middle where its telegraph is readable.
    Stage(
        name="The Pillars",
        filename="stage2.json",
        width=34,
        height=20,
        hero=(3, 10),
        pillars=[
            (8, 3, 3, 4),
            (8, 13, 3, 4),
            (15, 8, 4, 4),
            (23, 3, 3, 4),
            (23, 13, 3, 4),
        ],
        enemies=spawns(
            ("grunt", 13, 4),
            ("grunt", 13, 15),
            ("grunt", 21, 10),
            ("charger", 20, 4),
            ("archer", 30, 5),
            ("archer", 30, 15),
        ),
    ),
    # --- 3 -------------------------------------------------------------------
    # The original arena, unchanged. It is the fight the whole game was tuned
    # around and its numbers are on record, which makes it the one stage the
    # balance harness can be checked against.
    Stage(
        name="The Gauntlet",
        filename="stage3.json",
        width=40,
        height=24,
        hero=(3, 12),
        pillars=[
            (5, 4, 3, 3),
            (5, 17, 3, 3),
            (17, 3, 4, 2),
            (16, 10, 6, 4),
            (18, 19, 4, 2),
            (31, 5, 3, 3),
            (31, 16, 3, 3),
            (25, 8, 2, 2),
            (25, 14, 2, 2),
        ],
        enemies=spawns(
            ("grunt", 11, 6),
            ("grunt", 11, 17),
            ("grunt", 24, 5),
            ("grunt", 24, 18),
            ("grunt", 36, 12),
            ("charger", 14, 12),
            ("charger", 30, 12),
            ("archer", 36, 4),
            ("archer", 36, 20),
        ),
    ),
    # --- 4 -------------------------------------------------------------------
    # The boss, and deliberately little else. Four pillars in a wide ring: cover
    # from the volley, and something for a charge to end against. A crowd here
    # would bury the one fight the stage is about.
    Stage(
        name="The Keep",
        filename="stage4.json",
        width=32,
        height=22,
        hero=(3, 11),
        pillars=[(9, 4, 3, 3), (9, 15, 3, 3), (21, 4, 3, 3), (21, 15, 3, 3)],
        enemies=spawns(
            ("boss", 25, 11),
            ("grunt", 16, 4),
            ("grunt", 16, 17),
        ),
    ),
]

CAMPAIGN_NAME = "Hack and Slash"


def build_campaign() -> Campaign:
    return Campaign(
        name=CAMPAIGN_NAME, stages=tuple(stage.build() for stage in STAGES)
    )


def main() -> int:
    campaign = build_campaign()

    problems = campaign.problems()
    if problems:
        # Refuse to write a campaign that cannot be played. A bad stage on disk
        # is worse than none: it fails at run time, far from the mistake, and
        # possibly minutes into somebody's run.
        print("campaign is not playable:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    for stage, level in zip(STAGES, campaign.stages):
        level_io.save(level, config.LEVELS_DIR / stage.filename)

    manifest = config.LEVELS_DIR / "campaign.json"
    campaign_io.save(campaign, manifest, [s.filename for s in STAGES])

    print(f"wrote {manifest.relative_to(ROOT)}  ({len(STAGES)} stages)")
    for index, (stage, level) in enumerate(zip(STAGES, campaign.stages), start=1):
        kinds: dict[str, int] = {}
        for spawn in level.enemy_spawns:
            kinds[spawn.type_id] = kinds.get(spawn.type_id, 0) + 1
        mix = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
        print(
            f"  {index}. {stage.name:<14} {level.width:>2}x{level.height:<2} "
            f"{len(level.enemy_spawns)} enemies  ({mix})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
