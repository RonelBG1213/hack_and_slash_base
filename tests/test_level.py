"""The level model, its validation, and the arena that actually ships."""

from __future__ import annotations

from hack_and_slash import config
from hack_and_slash.core import level_io
from hack_and_slash.core.level import EnemySpawn, Level
from hack_and_slash.core.vec2 import Vec2

SIMPLE = Level(
    name="test",
    rows=(
        "#####",
        "#...#",
        "#.#.#",
        "#...#",
        "#####",
    ),
    hero_spawn=(1, 1),
    enemy_spawns=(EnemySpawn("grunt", (3, 3)),),
    tile=16,
)


def test_walls_and_floor_read_back_correctly() -> None:
    assert SIMPLE.is_solid(0, 0)
    assert SIMPLE.is_solid(2, 2)
    assert SIMPLE.is_walkable(1, 1)


def test_outside_the_map_is_solid() -> None:
    # This is what closes the arena. A body that ends up outside gets pushed
    # back in rather than sailing off forever.
    assert SIMPLE.is_solid(-1, 2)
    assert SIMPLE.is_solid(2, -1)
    assert SIMPLE.is_solid(99, 2)
    assert SIMPLE.is_solid(2, 99)


def test_tile_center_is_the_middle_not_the_corner() -> None:
    # Spawning on a corner starts a body overlapping up to three other tiles.
    assert SIMPLE.tile_center(0, 0) == Vec2(8, 8)
    assert SIMPLE.tile_center(2, 3) == Vec2(40, 56)


def test_tile_at_is_the_inverse_of_tile_center() -> None:
    for tx, ty in ((0, 0), (1, 3), (4, 2)):
        assert SIMPLE.tile_at(SIMPLE.tile_center(tx, ty)) == (tx, ty)


def test_pixel_size_covers_the_whole_grid() -> None:
    assert SIMPLE.pixel_size == (80, 80)


# --- validation --------------------------------------------------------------
def test_a_good_level_reports_no_problems() -> None:
    assert SIMPLE.problems() == []
    assert SIMPLE.is_playable


def test_a_spawn_inside_a_wall_is_reported_not_raised() -> None:
    # Reported so a tool can list every fault at once instead of one per run.
    broken = Level(
        name="broken",
        rows=SIMPLE.rows,
        hero_spawn=(2, 2),  # the pillar
        enemy_spawns=(EnemySpawn("grunt", (0, 0)),),
        tile=16,
    )
    problems = broken.problems()
    assert any("hero spawns inside a wall" in p for p in problems)
    assert any("grunt spawns inside a wall" in p for p in problems)
    assert not broken.is_playable


def test_a_level_with_nothing_to_fight_is_not_playable() -> None:
    empty = Level(name="empty", rows=SIMPLE.rows, hero_spawn=(1, 1), enemy_spawns=())
    assert any("nothing to fight" in p for p in empty.problems())


def test_ragged_rows_are_reported() -> None:
    ragged = Level(
        name="ragged",
        rows=("#####", "#..#", "#####"),
        hero_spawn=(1, 1),
        enemy_spawns=(EnemySpawn("grunt", (2, 1)),),
    )
    assert any("same length" in p for p in ragged.problems())


# --- the shipped arena -------------------------------------------------------
def shipped_stages():
    from hack_and_slash.core import campaign_io

    path = config.LEVELS_DIR / "campaign.json"
    assert path.exists(), "run `python tools/make_level.py` first"
    return campaign_io.load(path).stages


def test_every_shipped_stage_is_playable() -> None:
    """Guards the level files themselves, not just the model.

    A hand-edited stage that spawns an enemy in a pillar would otherwise only
    show up as something stuck in a wall, possibly several stages into a run.
    """
    for stage in shipped_stages():
        assert stage.problems() == [], stage.name
        assert stage.tile == config.TILE

        # Every spawn must have room to stand, not merely be on a non-wall tile.
        for spawn in stage.enemy_spawns:
            tx, ty = spawn.tile
            assert stage.is_walkable(tx, ty), f"{stage.name}: {spawn.type_id} at {spawn.tile}"


def test_every_stage_is_bigger_than_one_screen() -> None:
    # So the camera has work to do and a fight has somewhere to move to.
    for stage in shipped_stages():
        width_px, height_px = stage.pixel_size
        assert width_px > config.INTERNAL_W, stage.name
        assert height_px > config.VIEWPORT_H, stage.name


def test_every_stage_is_fully_enclosed() -> None:
    for stage in shipped_stages():
        for x in range(stage.width):
            assert stage.is_solid(x, 0) and stage.is_solid(x, stage.height - 1), stage.name
        for y in range(stage.height):
            assert stage.is_solid(0, y) and stage.is_solid(stage.width - 1, y), stage.name


def test_every_stage_has_cover_to_break_line_of_sight() -> None:
    # Archers and the boss volley are only interesting with somewhere to hide.
    for stage in shipped_stages():
        interior_walls = sum(
            1
            for y in range(1, stage.height - 1)
            for x in range(1, stage.width - 1)
            if stage.is_solid(x, y)
        )
        assert interior_walls > 15, f"{stage.name} is an empty box"
