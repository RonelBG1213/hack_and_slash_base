"""Level serialisation. The round trip is the contract."""

from __future__ import annotations

import json

import pytest

from hack_and_slash.core import level_io
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.core.level_io import LevelFormatError

SIMPLE = Level(
    name="round trip",
    rows=(
        "#####",
        "#...#",
        "#.#.#",
        "#...#",
        "#####",
    ),
    hero_spawn=(1, 1),
    enemy_spawns=(EnemySpawn("grunt", (3, 3)), EnemySpawn("archer", (3, 1))),
    tile=16,
)


def test_round_trip_through_a_dict_changes_nothing() -> None:
    assert level_io.from_dict(level_io.to_dict(SIMPLE)) == SIMPLE


def test_round_trip_through_a_file_changes_nothing(tmp_path) -> None:
    path = tmp_path / "level.json"
    level_io.save(SIMPLE, path)
    assert level_io.load(path) == SIMPLE


def test_the_hero_spawn_is_written_into_the_grid() -> None:
    """Kept in the picture rather than as separate coordinates, so a hand edit
    that shifts the map cannot leave the spawn pointing at the wrong cell."""
    payload = level_io.to_dict(SIMPLE)
    assert payload["rows"][1][1] == "@"
    # And the marker is walkable when it comes back, not a hole in the floor.
    assert level_io.from_dict(payload).is_walkable(1, 1)


def test_saved_files_carry_a_schema_version(tmp_path) -> None:
    path = tmp_path / "level.json"
    level_io.save(SIMPLE, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == level_io.SCHEMA_VERSION


def test_a_file_from_a_newer_build_is_refused_by_name() -> None:
    # Better a clear error than silently ignoring fields we do not understand.
    payload = level_io.to_dict(SIMPLE)
    payload["schema_version"] = level_io.SCHEMA_VERSION + 1
    with pytest.raises(LevelFormatError, match="newer build"):
        level_io.from_dict(payload)


def test_a_level_with_no_hero_marker_is_refused() -> None:
    with pytest.raises(LevelFormatError, match="no hero spawn"):
        level_io.from_dict({"rows": ["#####", "#...#", "#####"]})


def test_missing_rows_is_refused() -> None:
    with pytest.raises(LevelFormatError, match="'rows'"):
        level_io.from_dict({"name": "nothing"})


def test_malformed_json_names_the_file(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(LevelFormatError, match="broken.json"):
        level_io.load(path)
