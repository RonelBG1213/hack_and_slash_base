"""The drawing layer, exercised headlessly.

These do not check that the game looks good -- no test does. They check that it
draws at all: that a frame is not blank, that nothing raises part-way through a
fight, and that the pixel pipeline is still nearest-neighbour. That last one is
the whole look of the game and the easiest thing to break without noticing.
"""

from __future__ import annotations

import pygame
import pytest

from hack_and_slash import config
from hack_and_slash.core import campaign_io
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game.intent import Intent
from hack_and_slash.game.sim import step
from hack_and_slash.render.atlas import load as load_atlas
from hack_and_slash.render.effects import Effects
from hack_and_slash.render.hud import Hud
from hack_and_slash.render.renderer import Renderer
from hack_and_slash.scenes import smoke
from hack_and_slash.scenes.menu import MenuScene
from hack_and_slash.scenes.play import PlayScene

from .helpers import BESTIARY, add_enemy, make_world


@pytest.fixture(scope="module")
def display():
    """A dummy display. conftest.py has already pointed SDL at the null driver,
    but fonts and surface conversion still need a display to exist."""
    pygame.init()
    pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))
    yield
    pygame.quit()


@pytest.fixture(scope="module")
def atlas(display):
    if not config.SPRITE_ATLAS.exists():
        pytest.skip("no atlas -- run `python tools/gen_art.py`")
    return load_atlas()


def campaign():
    return campaign_io.load(config.LEVELS_DIR / "campaign.json")


def is_blank(surface: pygame.Surface) -> bool:
    width, height = surface.get_size()
    first = surface.get_at((0, 0))
    return all(
        surface.get_at((x, y)) == first
        for y in range(0, height, 7)
        for x in range(0, width, 7)
    )


# --- pixel fidelity ----------------------------------------------------------
def test_sprites_survive_the_upscale_with_hard_edges(atlas) -> None:
    """The look of the game in one assertion.

    Everything is drawn at 384x216 and blown up by a whole number. Let a smooth
    scale in anywhere -- smoothscale, a fractional factor, the wrong convert --
    and the art turns to mush in a way that is easy to miss on a small screen.
    """
    assert smoke.check(atlas) == []


def test_the_upscale_used_by_the_app_invents_no_colours(atlas) -> None:
    source = pygame.Surface((8, 8))
    source.fill((10, 20, 30))
    pygame.draw.rect(source, (200, 100, 50), (0, 0, 4, 4))

    scaled = pygame.transform.scale(source, (24, 24))
    colors = {tuple(scaled.get_at((x, y))) for y in range(24) for x in range(24)}
    assert colors == {(10, 20, 30, 255), (200, 100, 50, 255)}


# --- scenes draw -------------------------------------------------------------
def test_the_menu_draws_something(atlas) -> None:
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    MenuScene(campaign(), BESTIARY, atlas).draw(surface)
    assert not is_blank(surface)


def test_the_opening_frame_of_a_fight_draws_something(atlas) -> None:
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    PlayScene(campaign(), BESTIARY, atlas).draw(surface)
    assert not is_blank(surface)


def test_a_fight_in_progress_draws_without_raising(atlas) -> None:
    """Covers the states a still frame misses: open hitboxes, arrows in flight,
    a charger telegraphing, damage numbers, bodies flashing."""
    scene = PlayScene(campaign(), BESTIARY, atlas)
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))

    press = Intent(move=Vec2(1, 0), aim=Vec2(1, 0), attack=True)
    for tick in range(600):
        step(scene.world, press)
        scene.effects.feed(scene.world.drain_events(), scene.world.hitstop)
        scene.effects.tick()
        if scene.world.hero is not None:
            scene.camera.follow(scene.world.hero.pos)
        if tick % 20 == 0:
            scene.draw(surface)

    assert not is_blank(surface)


def test_the_result_banner_draws_over_a_finished_run(atlas) -> None:
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.world.hero.hp = 0
    step(scene.world, Intent())

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.draw(surface)
    assert not is_blank(surface)


def test_restarting_gives_a_fresh_world(atlas) -> None:
    scene = PlayScene(campaign(), BESTIARY, atlas, seed=3)
    scene.world.hero.hp = 5
    restarted = scene.restarted()

    assert restarted.world.hero.hp == BESTIARY["hero"].hp
    assert restarted.world.tick == 0
    assert restarted.seed == 3, "a restart must replay the same run, not a new one"


# --- the renderer directly ---------------------------------------------------
def test_the_renderer_handles_an_empty_world(atlas) -> None:
    # A won arena has no enemies; a lost one has no hero. Neither may crash.
    world = make_world()
    world.entities = []
    surface = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H))

    from hack_and_slash.render.camera import Camera

    camera = Camera(*world.level.pixel_size, config.INTERNAL_W, config.VIEWPORT_H)
    Renderer(atlas).draw(surface, world, camera, Effects())


def test_the_hud_handles_a_dead_hero(atlas) -> None:
    world = make_world()
    add_enemy(world, "grunt", world.hero.pos + Vec2(100, 0))
    world.entities = [e for e in world.entities if not e.is_hero]

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    Hud().draw(surface, world, tick=10)


def test_the_hud_draws_the_danger_state(atlas) -> None:
    # The pulsing low-health bar depends on the tick, so both phases must draw.
    world = make_world()
    world.hero.hp = 5
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    for tick in (0, 12):
        Hud().draw(surface, world, tick=tick)
    assert not is_blank(surface)
