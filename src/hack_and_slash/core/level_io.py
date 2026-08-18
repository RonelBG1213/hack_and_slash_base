"""Reading and writing `levels/*.json`.

Carries a `schema_version` from the first file written. Adding it later means
guessing at the shape of files already on disk; adding it now costs one integer
and makes every future format change a migration instead of a break.

Version 2 added `kind` and `props`. Both default, so a version-1 file still
loads and still means an arena -- which is the whole point of having had the
integer there from the start. The bump is for the other direction: a version-2
room opened by a version-1 build would come back as an arena with no enemies,
and `Level.problems()` would call it broken while it was merely newer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .level import FLOOR, HERO_MARK, EnemySpawn, Level, Prop, PropKind, RoomKind

SCHEMA_VERSION = 2


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
        "kind": level.kind.value,
        "enemies": [
            {"type": spawn.type_id, "x": spawn.tile[0], "y": spawn.tile[1]}
            for spawn in level.enemy_spawns
        ],
        "props": [
            {
                "kind": prop.kind.value,
                "x": prop.tile[0],
                "y": prop.tile[1],
                # Written only where it means something, so a fountain's entry
                # in the file does not carry a null nobody reads.
                **({"leads_to": prop.leads_to.value} if prop.leads_to else {}),
            }
            for prop in level.props
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
        kind=_enum(RoomKind, payload.get("kind"), RoomKind.COMBAT, "kind"),
        props=tuple(_prop(entry) for entry in payload.get("props", [])),
    )


def _enum(cls, raw, default, field: str):
    """One of `cls`, or `default` when the key is absent.

    A *present* value that names nothing raises, rather than falling back. The
    default is there for version-1 files that never had the key; a typo in a
    version-2 file is a broken room, and quietly turning it into an arena is how
    a fountain full of grunts gets shipped.
    """
    if raw is None:
        return default
    try:
        return cls(raw)
    except ValueError:
        raise LevelFormatError(
            f"'{raw}' is not a {field}; the {len(cls)} are "
            f"{', '.join(member.value for member in cls)}"
        ) from None


def _prop(entry: dict[str, Any]) -> Prop:
    try:
        tile = (int(entry["x"]), int(entry["y"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise LevelFormatError(f"a prop is missing {exc}") from exc
    return Prop(
        kind=_enum(PropKind, entry.get("kind"), None, "prop kind"),
        tile=tile,
        leads_to=_enum(RoomKind, entry.get("leads_to"), None, "kind"),
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
