"""Writes `levels/arena.json`.

There is no level editor -- that was a deliberate scope cut. This script is the
compromise: the arena is described here as a border plus a list of pillar
rectangles, which is far easier to get right than counting characters in a wall
of ASCII by hand. The output is still plain readable JSON, so a small tweak can
be made in the file directly without coming back here.

    python tools/make_level.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hack_and_slash import config  # noqa: E402
from hack_and_slash.core import level_io  # noqa: E402
from hack_and_slash.core.level import FLOOR, WALL, EnemySpawn, Level  # noqa: E402

WIDTH, HEIGHT = 40, 24

# Pillars, as (x, y, w, h) in tiles. They exist for three reasons: to break line
# of sight so archers are a positioning problem rather than a damage tax, to give
# chargers something to miss you into, and to stop the arena reading as an empty
# box. Deliberately fat -- one-tile pillars vanish behind the hero sprite.
PILLARS = [
    (5, 4, 3, 3),
    (5, 17, 3, 3),
    (17, 3, 4, 2),
    (16, 10, 6, 4),
    (18, 19, 4, 2),
    (31, 5, 3, 3),
    (31, 16, 3, 3),
    (25, 8, 2, 2),
    (25, 14, 2, 2),
]

HERO_TILE = (3, 12)

# Composition of the fight. Chasers pressure you, archers punish standing still,
# chargers punish standing in a line -- placed so you meet the chasers first and
# only get archered once you have committed to the middle.
ENEMIES = [
    EnemySpawn("grunt", (11, 6)),
    EnemySpawn("grunt", (11, 17)),
    EnemySpawn("grunt", (24, 5)),
    EnemySpawn("grunt", (24, 18)),
    EnemySpawn("grunt", (36, 12)),
    EnemySpawn("charger", (14, 12)),
    EnemySpawn("charger", (30, 12)),
    EnemySpawn("archer", (36, 4)),
    EnemySpawn("archer", (36, 20)),
]


def build_rows() -> tuple[str, ...]:
    grid = [[FLOOR] * WIDTH for _ in range(HEIGHT)]

    for x in range(WIDTH):
        grid[0][x] = WALL
        grid[HEIGHT - 1][x] = WALL
    for y in range(HEIGHT):
        grid[y][0] = WALL
        grid[y][WIDTH - 1] = WALL

    for px, py, pw, ph in PILLARS:
        for y in range(py, py + ph):
            for x in range(px, px + pw):
                grid[y][x] = WALL

    return tuple("".join(row) for row in grid)


def build_level() -> Level:
    return Level(
        name="The Arena",
        rows=build_rows(),
        hero_spawn=HERO_TILE,
        enemy_spawns=tuple(ENEMIES),
        tile=config.TILE,
    )


def main() -> int:
    level = build_level()

    problems = level.problems()
    if problems:
        # Refuse to write a level that cannot be played. A bad arena on disk is
        # worse than none: it fails at run time, far from the mistake.
        print("arena is not playable:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    path = config.LEVELS_DIR / "arena.json"
    level_io.save(level, path)
    print(f"wrote {path.relative_to(ROOT)}  ({level.width}x{level.height} tiles, "
          f"{len(level.enemy_spawns)} enemies)")
    for row in level.rows:
        print(f"  {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
