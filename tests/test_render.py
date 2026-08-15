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
from hack_and_slash.game import skills
from hack_and_slash.game.intent import Intent
from hack_and_slash.game.sim import step
from hack_and_slash.render.atlas import load as load_atlas
from hack_and_slash.render.effects import Effects
from hack_and_slash.render.hud import Hud
from hack_and_slash.render.renderer import Renderer
from hack_and_slash.scenes import smoke
from hack_and_slash.scenes.menu import MenuScene
from hack_and_slash.scenes.play import PlayScene
from hack_and_slash.scenes.select import CharacterSelectScene

from .helpers import BESTIARY, HERO, add_enemy, make_world


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

    assert restarted.world.hero.hp == HERO.hp
    assert restarted.world.tick == 0
    assert restarted.seed == 3, "a restart must replay the same run, not a new one"


def test_restarting_keeps_the_class_you_picked(atlas) -> None:
    """R is 'try that again', not 'go back to the character select'.

    Worth its own test because the failure is quiet: the run restarts, it just
    restarts as somebody else, and the default is a real class so nothing looks
    broken until the player notices they are holding a different weapon.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas, hero_type_id="priest")
    restarted = scene.restarted()

    assert restarted.hero_type_id == "priest"
    assert restarted.world.hero.type.id == "priest"


# --- the character select ----------------------------------------------------
def test_the_character_select_draws_every_class(atlas) -> None:
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene = CharacterSelectScene(campaign(), BESTIARY, atlas)

    # Each one in turn, because a class whose sprite is missing from the atlas
    # raises only when it is the highlighted one being drawn at full brightness.
    for index in range(len(BESTIARY.hero_classes)):
        scene.index = index
        scene.draw(surface)
        assert not is_blank(surface)


def test_choosing_a_class_starts_the_run_as_that_class(atlas) -> None:
    """The one thing this screen exists to do.

    Reaching into `_begin` rather than synthesising a keypress: the binding is
    trivial and the handover is not, and it is the handover that would silently
    drop the choice and start everyone as the default.
    """
    scene = CharacterSelectScene(campaign(), BESTIARY, atlas, seed=9)
    scene.index = [c.id for c in BESTIARY.hero_classes].index("magician")

    play = scene._begin()
    assert play.hero_type_id == "magician"
    assert play.world.hero.type.id == "magician"
    assert play.world.hero.hp == BESTIARY["magician"].hp
    assert play.seed == 9, "the run must carry the seed through the select screen"


def test_the_roster_wraps_at_both_ends(atlas) -> None:
    scene = CharacterSelectScene(campaign(), BESTIARY, atlas)
    last = len(BESTIARY.hero_classes) - 1

    scene._move(-1)
    assert scene.index == last, "moving left off the start should wrap to the end"
    scene._move(1)
    assert scene.index == 0


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


def test_the_hud_draws_the_skill_pips_for_every_class(atlas) -> None:
    """Four cooldowns in a 384px strip that already holds a health bar, its
    readout and a stage counter. Drawn for all five classes and in both states,
    because the pip is a different shape when it is filling."""
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    for cls in BESTIARY.hero_classes:
        world = make_world()
        world.hero.type = cls
        Hud().draw(surface, world, tick=0)

        # Part-way through two of the three, which is the state the row spends
        # most of a fight in.
        world.hero.skill_cooldowns = {
            skills.NEUTRAL: cls.weapons[skills.NEUTRAL].cooldown // 2,
            skills.ULTIMATE: cls.weapons[skills.ULTIMATE].cooldown - 1,
        }
        world.hero.dodge_cooldown = cls.dodge_cooldown // 2
        Hud().draw(surface, world, tick=0)
    assert not is_blank(surface)


def test_the_hud_draws_for_a_body_with_no_skills(atlas) -> None:
    """A `World` can be built around any entity type -- the tools and half the
    tests do it -- so the pip row has to cope with a hero that has one attack
    rather than four. An IndexError here would break everything downstream of
    it, and only in the drawing layer, which is the last place anyone looks."""
    world = make_world()
    world.hero.type = BESTIARY["grunt"]
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    Hud().draw(surface, world, tick=0)


# --- input -------------------------------------------------------------------
def test_a_skill_key_selects_its_slot_and_fires_once(atlas) -> None:
    """The input path, which nothing covered before: a keypress becomes an
    `Intent` naming a slot, and the flag is cleared so it does not fire again on
    the next frame. Held-to-repeat is right for the light attack and wrong for a
    skill -- a leant-on key would spend every cooldown the instant it expired,
    forever, which is the opposite of a decision."""
    scene = PlayScene(campaign(), BESTIARY, atlas)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    intent = scene._read_intent()
    assert intent.attack and intent.weapon == skills.HEAVY

    assert scene._read_intent().weapon == skills.LIGHT, "the press fired twice"


def test_the_highest_slot_wins_when_two_keys_land_in_one_frame(atlas) -> None:
    # The slots ascend by commitment, so mashing resolves toward the thing you
    # least want swallowed rather than toward the cheapest.
    scene = PlayScene(campaign(), BESTIARY, atlas)
    for key in (pygame.K_f, pygame.K_q):
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    assert scene._read_intent().weapon == skills.ULTIMATE
