"""The sprite atlas, and the agreement between the art and the content files."""

from __future__ import annotations

import json

import pygame
import pytest

from hack_and_slash import config
from hack_and_slash.render.atlas import Atlas, MissingAtlasError, load

from .helpers import BESTIARY


@pytest.fixture(scope="module")
def atlas() -> Atlas:
    pygame.init()
    if not config.SPRITE_ATLAS.exists():
        pytest.skip("no atlas -- run `python tools/gen_art.py`")
    return load()


def test_every_sprite_named_in_the_order_is_present(atlas: Atlas) -> None:
    for name in config.SPRITE_ORDER:
        assert name in atlas


def test_every_entity_sprite_exists_in_the_atlas(atlas: Atlas) -> None:
    """The one that catches adding a monster and forgetting the art.

    `data/entities.json` names a sprite; if the atlas has no cell for it the
    game crashes on the first frame that enemy is on screen, which could be
    minutes into a run.
    """
    for type_id, entity_type in BESTIARY.types.items():
        assert entity_type.sprite in atlas, f"{type_id} wants a '{entity_type.sprite}' sprite"


def test_the_terrain_sprites_the_renderer_hard_codes_exist(atlas: Atlas) -> None:
    # Not named in any data file, so nothing else would notice them going missing.
    for name in ("floor", "wall", "arrow", "shadow"):
        assert name in atlas


def test_cells_are_one_tile_square(atlas: Atlas) -> None:
    for name in config.SPRITE_ORDER:
        assert atlas[name].get_size() == (config.TILE, config.TILE), name


def test_an_unknown_sprite_lists_what_is_available(atlas: Atlas) -> None:
    with pytest.raises(KeyError, match="charger"):
        atlas["basilisk"]


def test_tinting_keeps_the_sprite_s_shape(atlas: Atlas) -> None:
    # The hit flash must flood the body, not paint a white square over it.
    flashed = atlas.tinted("hero", (255, 255, 255))
    assert flashed.get_size() == atlas["hero"].get_size()
    assert flashed.get_at((0, 0))[3] == atlas["hero"].get_at((0, 0))[3]


def test_a_missing_atlas_says_which_command_builds_it(tmp_path) -> None:
    with pytest.raises(MissingAtlasError, match="gen_art"):
        load(tmp_path / "not_here.png")


def test_an_atlas_too_small_for_the_sprite_list_is_refused() -> None:
    """Catches an atlas built before a sprite was added to SPRITE_ORDER."""
    pygame.init()
    tiny = pygame.Surface((config.TILE, config.TILE), pygame.SRCALPHA)
    with pytest.raises(MissingAtlasError, match="too small"):
        Atlas(tiny)


def test_the_generator_paints_everything_the_order_asks_for() -> None:
    """Checks tools/gen_art.py against config.SPRITE_ORDER without running it."""
    import sys
    from pathlib import Path

    tools = Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(tools))
    try:
        import gen_art
    finally:
        sys.path.remove(str(tools))

    for name in config.SPRITE_ORDER:
        assert name in gen_art.PAINTERS, f"nothing paints '{name}'"
