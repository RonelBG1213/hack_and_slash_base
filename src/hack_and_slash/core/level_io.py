"""Reading and writing `levels/*.json`.

Carries a `schema_version` from the first file written. Adding it later means
guessing at the shape of files already on disk; adding it now costs one integer
and makes every future format change a migration instead of a break.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .level import FLOOR, HERO_MARK, EnemySpawn, Level

SCHEMA_VERSION = 1


class LevelFormatError(ValueError):
    """A level file that cannot be turned into a Level at all.

    Distinct from `Level.problems()`, which is about a level that parses fine but
    would not be fair to play -- a spawn in a wall is a design mistake, a missing
    `rows` key is a broken file.
    """


def to_dict(level: Level) -> dict[str, Any]:
    # The hero spawn is written back into the grid as '@' rather than kept as a
    # separate pair of numbers, so a hand edit that moves the map cannot leave
    # the spawn pointing at the wrong cell.
    rows = list(level.rows)
    hx, hy = level.hero_spawn
    if 0 <= hy < len(rows) and 0 <= hx < len(rows[hy]):
        row = rows[hy]
        rows[hy] = row[:hx] + HERO_MARK + row[hx + 1 :]

    return {
        "schema_version": SCHEMA_VERSION,
        "name": level.name,
        "tile": level.tile,
        "rows": rows,
        "enemies": [
            {"type": spawn.type_id, "x": spawn.tile[0], "y": spawn.tile[1]}
            for spawn in level.enemy_spawns
        ],
    }


def from_dict(payload: dict[str, Any]) -> Level:
    version = payload.get("schema_version", SCHEMA_VERSION)
    if version > SCHEMA_VERSION:
        raise LevelFormatError(
            f"level was written by a newer build (schema {version}, this build reads "
            f"{SCHEMA_VERSION})"
        )

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
        raise LevelFormatError("'rows' must be a non-empty list of strings")

    found = _take_hero(rows)
    if found is None:
        raise LevelFormatError(f"no hero spawn -- put a '{HERO_MARK}' somewhere in 'rows'")
    hero_spawn, rows = found

    enemies = tuple(
        EnemySpawn(entry["type"], (int(entry["x"]), int(entry["y"])))
        for entry in payload.get("enemies", [])
    )

    return Level(
        name=payload.get("name", "unnamed"),
        rows=tuple(rows),
        hero_spawn=hero_spawn,
        enemy_spawns=enemies,
        tile=int(payload.get("tile", 16)),
    )


def _take_hero(rows: list[str]) -> tuple[tuple[int, int], list[str]] | None:
    """Pull the hero spawn out of the grid, returning it and the plain floor.

    In memory the marker does not exist -- `rows` holds terrain and nothing else,
    and the spawn is a pair of coordinates. `to_dict` paints it back in on the
    way out. Normalising here is what makes load(save(x)) == x: leave the '@' in
    the grid and every round trip returns something subtly unequal to what went
    in, which is exactly the kind of drift that makes a save format untrustworthy.
    """
    for y, row in enumerate(rows):
        x = row.find(HERO_MARK)
        if x != -1:
            cleaned = list(rows)
            cleaned[y] = row[:x] + FLOOR + row[x + 1 :]
            return (x, y), cleaned
    return None


def load(path: Path) -> Level:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LevelFormatError(f"{path.name} is not valid JSON: {exc}") from exc
    return from_dict(payload)


def save(level: Level, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(level), indent=2) + "\n", encoding="utf-8")
