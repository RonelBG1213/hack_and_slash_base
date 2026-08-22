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
from hack_and_slash.bindings import Action
from hack_and_slash.core import campaign_io
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import skills
from hack_and_slash.game.entities import ActionState
from hack_and_slash.game.intent import Intent
from hack_and_slash.game.sim import step
from hack_and_slash.render.atlas import load as load_atlas
from hack_and_slash.render.effects import Effects
from hack_and_slash.render.hud import PIP_ACTIVE, Hud
from hack_and_slash.render.pause_panel import ROWS as PAUSE_ROWS
from hack_and_slash.render.renderer import Renderer
from hack_and_slash.scenes import keymap, smoke
from hack_and_slash.scenes.menu import MenuScene
from hack_and_slash.game.run import RunOutcome
from hack_and_slash.scenes.play import BANNER_FRAMES, PlayScene
from hack_and_slash.scenes.select import CharacterSelectScene
from hack_and_slash.settings import Settings

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


def at_a_stall(scene):
    """Walk the hero onto a shop stall in the reward room it is standing in.

    The fixture is swapped rather than the room being rolled for, because which
    kind a room holds is the offer's business and this is a test about panels.
    `tests/test_rooms.py` is where the offer itself is pinned.
    """
    from hack_and_slash.core.level import PropKind

    scene.world.props[0].kind = PropKind.STALL
    scene.world.hero.pos = scene.world.props[0].pos
    scene.update(1.0)
    return scene


def out_through_a_door(scene, door: int = 0):
    """Leave the reward room, which is what starts the next arena."""
    doors = [prop for prop in scene.world.props if prop.is_door]
    scene.world.hero.pos = doors[door].pos
    scene.update(1.0)
    return scene


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


def _has_colour(surface: pygame.Surface, colour) -> bool:
    """Whether that exact colour is anywhere in the bottom strip.

    Every pixel, not the sampled grid `is_blank` uses -- a pip is eight pixels
    square and a stride of seven would find it or miss it depending on where
    the row happened to start.
    """
    top = config.INTERNAL_H - config.HUD_H
    return any(
        surface.get_at((x, y))[:3] == colour
        for y in range(top, config.INTERNAL_H)
        for x in range(config.INTERNAL_W)
    )


def test_the_buff_slot_takes_over_its_own_pip_while_it_is_live(atlas) -> None:
    """`PIP_ACTIVE` on screen exactly while the hero is buffed, for every class.

    Asserted on the colour rather than on "something was drawn", because the
    whole point of this pip is that it reads differently from the three around
    it -- a version that drew the buff in `PIP_FILLING` would be indis-
    tinguishable from the cooldown it replaces and would pass any `is_blank`
    check ever written.
    """
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    for cls in BESTIARY.hero_classes:
        world = make_world()
        world.hero.type = cls
        buff = cls.weapons[skills.NEUTRAL]

        Hud().draw(surface, world, tick=0)
        assert not _has_colour(surface, PIP_ACTIVE), (
            f"{cls.id} drew an active buff without one"
        )

        world.hero.buff = buff.buff
        world.hero.buff_ticks = buff.buff_ticks // 2
        world.hero.skill_cooldowns = {skills.NEUTRAL: buff.cooldown // 2}
        Hud().draw(surface, world, tick=0)
        assert _has_colour(surface, PIP_ACTIVE), (
            f"{cls.id}'s live buff drew as an ordinary cooldown"
        )


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
    `Intent` naming a slot, and the flag is spent so it does not fire again on
    the next tick. Held-to-repeat is right for the light attack and wrong for a
    skill -- a leant-on key would spend every cooldown the instant it expired,
    forever, which is the opposite of a decision.

    Spent by `_consume_edges` rather than by the read, which is the only part of
    this that changed: a press now waits for a tick that can take it instead of
    being discarded by the next frame. What it must not do is fire twice, and
    that is still what this asserts.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    intent = scene._read_intent()
    assert intent.attack and intent.weapon == skills.HEAVY

    scene._consume_edges()
    assert scene._read_intent().weapon == skills.LIGHT, "the press fired twice"


def rebound(action, name: str) -> Settings:
    """Settings with one action moved, built the way the screen builds them."""
    settings = Settings()
    assert keymap.assign(settings, action, name) is None
    return settings


def test_a_rebound_skill_fires_on_its_new_key(atlas) -> None:
    """The whole feature, in the units the sim cares about.

    Driven through the same three calls as the test at the top of this section:
    a keypress becomes an `Intent` naming a slot. The only difference is which
    key, which is the point.
    """
    scene = PlayScene(
        campaign(), BESTIARY, atlas, settings=rebound(Action.HEAVY, "v")
    )

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v))
    intent = scene._read_intent()
    assert intent.attack and intent.weapon == skills.HEAVY

    scene._consume_edges()
    assert scene._read_intent().weapon == skills.LIGHT, "the press fired twice"


def test_the_key_a_rebound_skill_used_to_be_on_stops_working(atlas) -> None:
    """Rebinding replaces, so the old key is a key like any other now."""
    scene = PlayScene(
        campaign(), BESTIARY, atlas, settings=rebound(Action.HEAVY, "v")
    )

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    assert scene._read_intent().weapon == skills.LIGHT


def test_a_rebound_dodge_buffers_from_its_new_key(atlas) -> None:
    scene = PlayScene(
        campaign(), BESTIARY, atlas, settings=rebound(Action.DODGE, "c")
    )

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    assert scene._read_intent().dodge


def test_a_rebound_sheet_key_closes_the_sheet_it_opened(atlas) -> None:
    """Derived rather than a constant, because the panel toggles on its own key.

    `SHEET_EXIT_KEYS` used to be a module constant built from the shipped keys.
    A rebound key that opened a panel it could not close would be a run ended by
    Escape, which is exactly the trade the shop's exit keys exist to avoid.
    """
    scene = PlayScene(
        campaign(), BESTIARY, atlas, settings=rebound(Action.SHEET, "c")
    )

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    assert scene.inspecting

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    assert not scene.inspecting


def test_the_hud_pip_names_the_key_that_actually_fires_it(atlas) -> None:
    """A pip still saying Q after the buff moved is confidently wrong.

    Worse than an unlabelled pip: a player reads it, presses it, and nothing
    happens. `SKILL_PIP_LABELS` stays in `render/hud.py` as the shipped default
    for the tools and the bare-`Hud()` tests, and `PlayScene` passes its own.
    """
    scene = PlayScene(
        campaign(), BESTIARY, atlas, settings=rebound(Action.NEUTRAL, "c")
    )

    # Spied rather than read off the scene: `scene.skill_labels` being right and
    # never reaching the HUD is exactly the bug this is here to catch.
    seen = {}
    scene.hud.draw = lambda *args, **kwargs: seen.update(kwargs)
    scene.draw(pygame.Surface((config.INTERNAL_W, config.INTERNAL_H)))

    labels = seen["skill_labels"]
    assert labels[skills.NEUTRAL] == "C"
    assert labels[skills.HEAVY] == "E", "an untouched slot moved"


def test_a_bare_hud_still_draws_the_keys_that_shipped() -> None:
    """The default is what `tools/screenshot.py` and half this file rely on."""
    from hack_and_slash.render.hud import SKILL_PIP_LABELS

    assert SKILL_PIP_LABELS[skills.NEUTRAL] == "Q"


def test_the_highest_slot_wins_when_two_keys_land_in_one_frame(atlas) -> None:
    # The slots ascend by commitment, so mashing resolves toward the thing you
    # least want swallowed rather than toward the cheapest.
    scene = PlayScene(campaign(), BESTIARY, atlas)
    for key in (pygame.K_f, pygame.K_q):
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    assert scene._read_intent().weapon == skills.ULTIMATE


def test_reading_an_intent_does_not_spend_the_press(atlas) -> None:
    """A rendered frame and a simulation tick are not the same thing.

    `_read_intent` is a pure read; `_consume_edges` is what ages the press, and
    it runs only where a `step` does. Collapsing the two is what threw a dodge
    away on every frame the accumulator paid out nothing, and this is the
    smallest statement of that.
    """
    from hack_and_slash.scenes.play import DODGE_BUFFER_TICKS

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

    for _ in range(5):
        assert scene._read_intent().dodge, "the press was spent by being looked at"

    # It survives exactly as many ticks as it says it does, and no more -- an
    # unbounded buffer is a roll the player stopped wanting.
    for _ in range(DODGE_BUFFER_TICKS):
        assert scene._read_intent().dodge
        scene._consume_edges()

    assert not scene._read_intent().dodge, "the buffer outlived its own limit"


def test_a_dodge_survives_a_frame_that_produced_no_tick(atlas) -> None:
    """`FPS` and `TICKS_PER_SEC` are both 60 and `clock.tick` deals in whole
    milliseconds, so the accumulator regularly banks a frame without paying out
    a tick. Measured: 2% of frames on a clean 16/17 alternation, 4-5% with
    ordinary jitter, 9% with a vsync hiccup -- and every one of them used to
    swallow whatever had just been pressed."""
    scene = PlayScene(campaign(), BESTIARY, atlas)
    before = scene.world.tick

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    scene.update(config.DT * 0.4)

    assert scene.world.tick == before, "the frame was meant to be too short to tick"
    assert scene._dodge_buffer, "a dodge was thrown away by a frame that did not tick"

    scene.update(config.DT * 2)
    assert scene.world.hero.state is ActionState.DODGING


def test_a_dodge_survives_hitstop(atlas) -> None:
    """The bigger of the two windows, and the one a player feels.

    `freeze` is set on every landed hit -- the hero's own and the ones it takes
    -- for up to eleven ticks. Those ticks are consumed without stepping, so
    clearing the flag once a frame meant a fifth of a second of dead dodge
    immediately after every connect, which is exactly when the roll is reached
    for.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.freeze = 6
    before = scene.world.tick

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    scene.update(config.DT * 4)

    assert scene.world.tick == before, "the world advanced during hitstop"
    assert scene._dodge_buffer, "a dodge pressed during hitstop was swallowed"

    scene.update(config.DT * 4)
    assert scene.world.hero.state is ActionState.DODGING, "the roll never came out"


def test_a_dodge_pressed_while_staggered_inside_hitstop_still_comes_out(atlas) -> None:
    """The case the buffer exists for, and the one that made a one-tick
    delivery worthless.

    Getting hit sets both `freeze` and `stagger`. `freeze` drains *without
    stepping*, so the stagger has not counted down at all by the time stepping
    resumes -- a press delivered on the first stepped tick is delivered into an
    `actions.can_dodge` that refuses it, and the player sees exactly what they
    saw when the press was being dropped outright.

    The buffer is one tick longer than the stagger, so the press is still live
    on the tick the hero becomes free.
    """
    from hack_and_slash.game import actions

    scene = PlayScene(campaign(), BESTIARY, atlas)
    hero = scene.world.hero
    hero.stagger = actions.STAGGER_TICKS
    scene.freeze = 8

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

    # Long enough to drain the freeze and then the stagger underneath it.
    for _ in range(20):
        scene.update(config.DT)
        if scene.world.hero.state is ActionState.DODGING:
            break

    assert scene.world.hero.state is ActionState.DODGING, (
        "the press was delivered while the hero was staggered and refused"
    )


def test_one_press_is_one_roll(atlas) -> None:
    """The buffer's other half. It re-asks the sim for a few ticks, which is
    only safe if a press that is *accepted* cannot be accepted twice.

    It cannot, and the reason is arithmetic rather than a guard: the buffer is
    six ticks, the shortest roll in the game is ten, and `dodge_cooldown` adds
    eighteen more behind it -- so the buffer is long spent before the hero could
    take a second. Pinned because both of those are balance numbers in a content
    file, and the day one of them drops this is a free extra roll that nothing
    else in the suite would report.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

    rolls, was = 0, None
    for _ in range(120):
        scene.update(config.DT)
        now = scene.world.hero.state
        if now is ActionState.DODGING and was is not ActionState.DODGING:
            rolls += 1
        was = now

    assert rolls == 1, f"one press produced {rolls} rolls"


def test_one_press_is_one_roll_even_when_a_frame_pays_out_many_ticks(atlas) -> None:
    """The stall case. `MAX_FRAME_TIME` lets one frame pay out fifteen ticks
    after a drag or a breakpoint, and the roll is ten to twelve -- so a frame
    can begin and finish a dodge without the player seeing a frame of it.

    Honest about what holds this up: the press surviving that frame is refused
    by `dodge_cooldown` (18 ticks at the shortest) rather than by the buffer, so
    this passes with the buffer read per tick *and* with it baked into the
    intent. It is pinned because the cooldown is a balance number on a content
    file -- the day a class ships a short enough one, this is the test that
    says so instead of a player finding a free second roll.
    """
    from hack_and_slash.game.events import EventKind

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

    # Counted off the sim's own event rather than by sampling the hero between
    # frames: a fifteen-tick frame can begin *and finish* a ten-tick roll
    # inside one `update`, so a sampler sees IDLE either side and reports
    # nothing at all. `feed` is the one place every tick's events pass through.
    rolls = 0
    feed = scene.effects.feed

    def spy(events, hitstop):
        nonlocal rolls
        events = list(events)
        rolls += sum(
            1 for e in events if e.kind is EventKind.DODGE and e.is_hero
        )
        feed(events, hitstop)

    scene.effects.feed = spy

    # One frame long enough to be clamped, then ordinary frames to carry the
    # hero out the far side of the roll.
    scene.update(config.MAX_FRAME_TIME)
    for _ in range(120):
        scene.update(config.DT)

    assert rolls == 1, f"a stalled frame turned one press into {rolls} rolls"


def test_the_dodge_buffer_is_shorter_than_every_roll_in_the_game() -> None:
    """What the test above depends on, stated where it can be checked against
    the content files rather than against one class."""
    from hack_and_slash.scenes.play import DODGE_BUFFER_TICKS

    rollers = [t for t in BESTIARY.types.values() if t.can_dodge]
    assert rollers, "no class can dodge, so this guarantees nothing"
    for hero_type in rollers:
        assert hero_type.dodge_ticks + hero_type.dodge_cooldown > DODGE_BUFFER_TICKS, (
            f"{hero_type.id} rolls for {hero_type.dodge_ticks} ticks and waits "
            f"{hero_type.dodge_cooldown}, against a {DODGE_BUFFER_TICKS}-tick "
            f"input buffer -- one press could roll twice"
        )


# --- loot on the floor -------------------------------------------------------
def test_the_renderer_draws_every_rarity_and_a_plain_coin(atlas) -> None:
    """One relic sprite serves all five tiers, and the colour is the whole
    difference between them -- so every tier has to survive being drawn."""
    from hack_and_slash.game.loot import Pickup, Rarity
    from hack_and_slash.render.camera import Camera

    world = make_world()
    world.pickups.append(Pickup(pos=world.hero.pos + Vec2(8, 0), gold=5))
    for index, rarity in enumerate(Rarity):
        world.pickups.append(
            Pickup(pos=world.hero.pos + Vec2(-20 - index * 6, 0), gold=10, rarity=rarity)
        )

    surface = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H))
    camera = Camera(*world.level.pixel_size, config.INTERNAL_W, config.VIEWPORT_H)
    camera.snap_to(world.hero.pos)
    Renderer(atlas).draw(surface, world, camera, Effects())

    assert not is_blank(surface)


def test_shading_a_sprite_keeps_its_shape(atlas) -> None:
    """MULT rather than MAX. The relic is drawn pale so it can take a colour,
    and MAX against a pale sprite gives the pale sprite straight back."""
    plain = atlas["relic"]
    shaded = atlas.shaded("relic", (255, 0, 0))

    assert shaded.get_size() == plain.get_size()
    assert any(
        shaded.get_at((x, y))[3] == plain.get_at((x, y))[3]
        for x in range(plain.get_width())
        for y in range(plain.get_height())
    )
    assert shaded.get_at((plain.get_width() // 2, plain.get_height() // 2)) != plain.get_at(
        (plain.get_width() // 2, plain.get_height() // 2)
    )


def test_the_hud_shows_the_purse_with_and_without_a_run(atlas) -> None:
    """A world stepped on its own -- a tool, half the tests -- has no run to ask
    what was banked earlier, and must still draw."""
    world = make_world()
    world.gold = 1234
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))

    Hud().draw(surface, world, tick=0)
    assert not is_blank(surface)

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.run.gold = 500
    scene.world.gold = 25
    assert scene.run.gold_total == 525
    scene.draw(pygame.Surface((config.INTERNAL_W, config.INTERNAL_H)))


# --- the shop ----------------------------------------------------------------
def test_the_shop_panel_draws_in_every_state(atlas) -> None:
    from hack_and_slash.game import shop

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.shopping = True

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))

    # Broke, so every row is greyed out.
    scene.draw(surface)
    assert not is_blank(surface)

    # Rich, hurt, and with every capped good bought out -- which now empties
    # the shelf down to the one uncapped row rather than greying five.
    scene.run.gold = 100000
    scene.world.hero.hp = 10
    for good in shop.stock():
        for _ in range(good.limit or 1):
            shop.buy(scene.run, good)
    scene.draw(surface)
    assert not is_blank(surface)

    assert [g.id for g in shop.available(scene.run)] == ["poultice"], (
        "the stall drew rows that can never be bought again"
    )


def test_the_shop_pauses_the_world_and_swallows_the_controls(atlas) -> None:
    """While the panel is up the world is not stepped at all.

    A skill pressed here would otherwise come out on the first tick of the next
    stage, which is a swing the player did not aim.

    The dodge half of this matters more than it used to. `_consume_edges` is now
    what clears the flags, and the shop is the one place a press is dropped
    without a tick having taken it -- otherwise a dodge pressed on the frame the
    stage was cleared would survive the whole visit and roll the hero into a
    room they have not seen.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.shopping = True
    before = scene.world.tick

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f))
    scene.update(1.0)

    assert scene.world.tick == before, "the world advanced while the shop was open"
    assert scene._skill_pressed is None, "a skill press leaked past the shop"

    # And a dodge banked on the frame the stage ended, before the panel opened.
    scene._dodge_buffer = 3
    scene.update(1.0)
    assert not scene._dodge_buffer, "a dodge press leaked past the shop"


def test_a_number_key_buys_the_good_on_that_row(atlas) -> None:
    from hack_and_slash.game import shop

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.shopping = True
    scene.run.gold = 100000
    tonic = shop.stock()[1]

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
    assert shop.bought(scene.run, tonic) == 1
    assert scene.run.gold == 100000 - tonic.price


def test_enter_closes_the_shop_and_play_resumes(atlas) -> None:
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.shopping = True

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert not scene.shopping

    before = scene.world.tick
    scene.update(0.5)
    assert scene.world.tick > before


def test_escape_shuts_the_shop_rather_than_leaving_the_run(atlas) -> None:
    """Escape is "back to the menu" everywhere else in this scene.

    The shop is the one place worth overriding it: a player shutting a panel
    reaches for Escape by habit, and dropping them out of a twenty-stage run for
    it is not a trade worth making.
    """
    exited = []
    scene = PlayScene(campaign(), BESTIARY, atlas, on_exit=lambda: exited.append(True))
    scene.shopping = True

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) is None
    assert not scene.shopping
    assert not exited


def test_clearing_a_stage_no_longer_opens_the_shop(atlas) -> None:
    """The headline of the rooms change, pinned from the side that was removed.

    This used to be the opposite assertion. The shop opened on all thirty-nine
    transitions whether or not there was anything to decide; it is now a fixture
    you have to have chosen a door towards, two rooms earlier.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)

    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)

    assert not scene.shopping, "clearing a stage still opens the shop by itself"
    assert scene.run.room is not None, "and it did not lead into a reward room either"


def test_walking_up_to_a_stall_opens_the_shop_with_the_takings_banked(atlas) -> None:
    """The order matters: `Run._enter_room` banks before it replaces the world,
    so the purse the panel shows is the real one rather than a stage behind."""
    scene = PlayScene(campaign(), BESTIARY, atlas)

    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)

    assert scene.shopping, "walking onto a stall did not open the shop"
    assert scene.run.gold > 0, "the shop opened on an empty purse after a full stage"
    assert scene.world.gold == 0


def test_no_shop_row_overflows_the_panel(atlas) -> None:
    """384 pixels wide, and a blurb that runs into the sold-out tally is the
    failure this catches -- it looks like a rendering bug and is a wording one.

    Measured with the panel's own fonts and columns rather than by counting
    characters, so shortening a template or moving a column both show up here.
    """
    from hack_and_slash.game import shop
    from hack_and_slash.render import shop_panel as panel

    drawn = panel.ShopPanel()
    for good in shop.stock():
        blurb_right = panel.LEFT + panel.BLURB_X + drawn.small.size(good.blurb)[0]
        assert blurb_right <= panel.TALLY_RIGHT, (
            f"{good.id}: '{good.blurb}' runs {blurb_right - panel.TALLY_RIGHT}px "
            "into the sold-out tally"
        )

        price_right = panel.LEFT + panel.PRICE_X + drawn.font.size(f"{good.price}g")[0]
        assert price_right <= panel.LEFT + panel.BLURB_X, f"{good.id}: the price runs into the blurb"
        name_right = panel.LEFT + panel.NAME_X + drawn.font.size(good.name)[0]
        assert name_right <= panel.LEFT + panel.PRICE_X, f"{good.id}: the name runs into the price"


def test_no_gear_row_overflows_the_panel(atlas) -> None:
    """The same measurement against the widest gear row that can ever be rolled.

    Worst case rather than a sample: the widest blurb is the whole pool at the
    top rarity, and the widest price is that piece on the last floor. Both are
    computed rather than rolled for, because a shelf drawn from one seed proves
    nothing about the seed that rolls a legendary Heartstone on floor forty.

    `equipment.MAX_ATTRIBUTES` is the rule this is enforcing the pixels of. If
    this fails, the answer is a shorter label or a narrower pool -- not a wider
    column, which would take the space from the rarity word.
    """
    from hack_and_slash.game import equipment, loot
    from hack_and_slash.render import shop_panel as panel

    drawn = panel.ShopPanel()
    table = equipment.table()
    top = max(table.rarity_scale.values())
    deepest = 40

    for piece in table.pieces:
        blurb = equipment.describe(piece.attributes.scaled(top))
        blurb_right = panel.LEFT + panel.BLURB_X + drawn.small.size(blurb)[0]
        widest_word = max(
            drawn.small.size(tier.rarity.value)[0] for tier in loot.table().tiers
        )
        assert blurb_right <= panel.TALLY_RIGHT - widest_word, (
            f"{piece.id}: '{blurb}' at the top rarity runs into the rarity word"
        )

        price = table.price_on(piece.price, top, deepest)
        price_right = panel.LEFT + panel.PRICE_X + drawn.font.size(f"{price}g")[0]
        assert price_right <= panel.LEFT + panel.BLURB_X, (
            f"{piece.id}: {price}g on floor {deepest} runs into the blurb"
        )
        name_right = panel.LEFT + panel.NAME_X + drawn.font.size(piece.name)[0]
        assert name_right <= panel.LEFT + panel.PRICE_X, f"{piece.id}: the name runs into the price"


def tallest_stall() -> int:
    """The most rows the stall can ever be asked to draw.

    `stock()` rather than `available(run)` on purpose: the panel grows a row in
    the second half of the campaign, and the layout has to hold for the tallest
    version rather than the one that happens to be on screen first. The gear
    section is `rooms.table().stall_offers` on top of that, and it does not vary.
    """
    from hack_and_slash.game import rooms, shop

    return rooms.table().stall_offers + len(shop.stock())


def test_the_shop_rows_and_hint_fit_above_the_hud(atlas) -> None:
    """Measured against the fullest the stall ever gets: gear plus the late shelf.

    This has been a failing test twice rather than a bug report from somebody
    playing act V, which is the whole reason it measures the worst case instead
    of what happens to be on screen.
    """
    from hack_and_slash.render import shop_panel as panel

    rows = tallest_stall()
    last_row = panel.ROW_Y + (rows - 1) * panel.ROW_H
    assert last_row < panel.hint_y(rows), "the last row of the stall draws through the hint"
    assert panel.hint_y(rows) + 13 <= config.VIEWPORT_H, (
        "the stall's hint line is drawn under the HUD"
    )

    # And the hint follows the rows up when there are fewer, rather than
    # marooning itself at the bottom of a short shelf.
    assert panel.hint_y(3) < panel.hint_y(rows)


def test_the_shop_has_a_key_for_every_row_it_can_draw(atlas) -> None:
    """The half of the row/key contract that lives with the keys.

    A good added to `data/loot.json`, or an offer added to `data/rooms.json`,
    without a key here is a row a player can read and cannot buy, and nothing
    else would say so.
    """
    from hack_and_slash.render import shop_panel as panel

    assert tallest_stall() <= len(panel.ROW_KEYS), (
        f"the stall can draw {tallest_stall()} rows and the panel has "
        f"{len(panel.ROW_KEYS)} keys"
    )


def test_the_stall_draws_its_gear_above_its_goods(atlas) -> None:
    """The row order is the key order, and gear is on top.

    Asserted on `rows()` rather than on pixels because that tuple is the thing
    both the panel and `PlayScene._handle_shop_event` index into -- if it were
    ever built twice, this is where the two would be seen to disagree.
    """
    from hack_and_slash.game import equipment, shop
    from hack_and_slash.render import shop_panel as panel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)

    shelf = panel.rows(scene.run, scene.stall_offers)
    kinds = [kind for kind, _ in shelf]
    assert kinds == ["gear"] * len(
        equipment.available(scene.run, scene.stall_offers)
    ) + ["good"] * len(shop.available(scene.run))
    assert all(isinstance(item, equipment.Offer) for kind, item in shelf if kind == "gear")


def test_walking_up_to_a_stall_rolls_a_shelf_of_gear(atlas) -> None:
    """The stall is a decision now, not the same five rows every time."""
    from hack_and_slash.game import rooms

    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)

    assert scene.shopping
    assert len(scene.stall_offers) == rooms.table().stall_offers
    assert len({offer.piece_id for offer in scene.stall_offers}) == len(scene.stall_offers)


def test_the_scene_rolls_the_shelf_the_game_layer_would(atlas) -> None:
    """The scene holds the tuple rather than re-deriving it per frame, so this
    is what ties the held one to the derivation a reloaded run would repeat."""
    from hack_and_slash.game import equipment

    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)

    assert scene.stall_offers == equipment.offers(scene.run)


def test_pressing_a_gear_key_spends_gold_and_writes_the_bonus(atlas) -> None:
    """End to end through the scene: the digit a player presses, the gold that
    leaves the purse, and the block that lands on the body standing in the room."""
    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)

    scene.run.gold = 100000
    offer = scene.stall_offers[0]
    before = scene.run.gold

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))

    assert scene.run.gold == before - offer.price
    assert scene.run.earned == offer.attributes
    assert scene.world.hero.bonus == scene.run.earned


def test_pressing_a_gear_key_with_no_gold_does_nothing(atlas) -> None:
    """A refused purchase is silent, and it is silent because the row was
    already greyed out by the same call that refused it."""
    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)

    scene.run.gold = 0
    earned = scene.run.earned

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))

    assert scene.run.gold == 0
    assert scene.run.earned == earned


# --- a bought row leaves the shelf -------------------------------------------
# The stall used to keep everything and grey what was finished. It was honest
# and it was also a receipt, and the rows a player still had a decision about
# were the two at the bottom of eight.
def test_a_bought_gear_row_is_gone_from_the_shelf(atlas) -> None:
    """Through the scene, which is where the two halves have to agree: the panel
    draws `rows()` and the key handler indexes the same call."""
    from hack_and_slash.render import shop_panel as panel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)
    scene.run.gold = 100000

    before = panel.rows(scene.run, scene.stall_offers)
    bought = before[0][1]

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))

    after = panel.rows(scene.run, scene.stall_offers)
    assert len(after) == len(before) - 1, "the shelf did not lose the bought row"
    assert bought not in [item for _, item in after]
    assert list(after) == list(before[1:]), "the other rows did not simply move up"

    # And the panel still draws, one row shorter.
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.draw(surface)
    assert not is_blank(surface)


def test_the_row_that_moved_up_is_not_bought_by_the_same_press(atlas) -> None:
    """The one hazard this feature introduces, and the only reason
    `SHOP_SETTLE_FRAMES` exists.

    A bought row leaves and the row under it inherits the digit. The second tap
    of a fast double-tap used to be a no-op on a greyed row; without the guard it
    is several hundred gold on a piece nobody chose.
    """
    from hack_and_slash.game import equipment
    from hack_and_slash.render import shop_panel as panel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)
    scene.run.gold = 100000

    shelf = panel.rows(scene.run, scene.stall_offers)
    assert [kind for kind, _ in shelf[:2]] == ["gear", "gear"], (
        "this test needs two gear rows to watch one slide up into the other"
    )
    first, second = shelf[0][1], shelf[1][1]
    gold = scene.run.gold

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))

    assert scene.run.gold == gold - first.price, "the second press bought as well"
    assert not equipment.taken(scene.run, second)

    # It is a pause, not a lock. The guard runs down on frames the world is not
    # being stepped on, and the row is buyable again once it has.
    for _ in range(scene_settle_frames()):
        scene.update(1 / 60)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
    assert equipment.taken(scene.run, second), "the guard never let go"


def scene_settle_frames() -> int:
    from hack_and_slash.scenes.play import SHOP_SETTLE_FRAMES

    return SHOP_SETTLE_FRAMES


def test_a_purchase_that_removes_nothing_does_not_swallow_the_next_press(atlas) -> None:
    """Buying the first of five Tonics moves no row, so nothing is guarded.

    A key that mysteriously does nothing after an ordinary purchase would be a
    worse bug than the one the guard is for, and it is the shape a guard on
    *every* purchase would have.
    """
    from hack_and_slash.game import shop
    from hack_and_slash.render import shop_panel as panel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)
    scene.run.gold = 100000

    shelf = panel.rows(scene.run, scene.stall_offers)
    row = next(
        i
        for i, (kind, item) in enumerate(shelf)
        if kind == "good" and item.id == "tonic"
    )
    tonic = shelf[row][1]
    assert tonic.limit > 2, "this test needs a good that survives two purchases"

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=panel.ROW_KEYS[row]))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=panel.ROW_KEYS[row]))

    assert shop.bought(scene.run, tonic) == 2, "the second press was swallowed"


def test_the_hint_says_how_many_rows_there_actually_are() -> None:
    """"1-8 to buy" was true while the row count was a property of the campaign.

    Both ends are worth pinning: "1-1 to buy" reads as a typo and "1-0 to buy"
    reads as a bug, and a shrinking shelf reaches both.
    """
    from hack_and_slash.render import shop_panel as panel

    assert panel._hint_for(8).startswith("1-8 to buy")
    assert panel._hint_for(2).startswith("1-2 to buy")
    assert panel._hint_for(1).startswith("1 to buy")
    assert "1-1" not in panel._hint_for(1)

    empty = panel._hint_for(0)
    assert "to buy" not in empty and "0" not in empty
    assert "Enter" in empty, "the way out is the one thing a bare shelf must say"


def test_a_goods_key_still_buys_the_good_under_the_gear(atlas) -> None:
    """The digits run continuously across both sections, so the first good is
    on key `stall_offers + 1` and not on key 1. A player counting rows and the
    scene indexing a list have to reach the same row."""
    from hack_and_slash.game import shop
    from hack_and_slash.render import shop_panel as panel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)
    at_a_stall(scene)

    scene.run.gold = 100000
    shelf = panel.rows(scene.run, scene.stall_offers)
    first_good = next(i for i, (kind, _) in enumerate(shelf) if kind == "good")
    good = shelf[first_good][1]
    scene.world.hero.hp = 1  # so a Poultice is not refused for doing nothing

    scene.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=panel.ROW_KEYS[first_good])
    )

    assert shop.bought(scene.run, good) == 1


# --- promotion ---------------------------------------------------------------
def promotion_scene(atlas, hero: str = "knight") -> PlayScene:
    """A scene sitting on the stage the fork opens onto, choice still open.

    `start_stage` is 0-based and `PROMOTION_STAGE` is 1-based, hence the offset.
    Taken from the constant rather than written out: this used to say 19 for
    "stage twenty", which was a number that had to be found and changed by hand
    every time the campaign moved.

    Built by starting there rather than by clearing twenty stages, because what
    is under test is the panel, not the campaign.
    """
    from hack_and_slash.game import jobs

    scene = PlayScene(
        campaign(),
        BESTIARY,
        atlas,
        start_stage=jobs.PROMOTION_STAGE - 1,
        hero_type_id=hero,
    )
    scene.promoting = True
    return scene


def test_the_job_panel_draws_for_every_class(atlas) -> None:
    """Ten advanced classes reached through five panels, and any one of them
    could be the one with a name too long or a sprite that does not exist."""
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    for cls in BESTIARY.hero_classes:
        scene = promotion_scene(atlas, cls.id)
        scene.draw(surface)
        assert not is_blank(surface), f"the {cls.id}'s promotion panel drew nothing"


def test_the_job_panel_draws_nothing_when_there_is_nothing_to_choose(atlas) -> None:
    """Belt and braces: the scene should not have opened it, but a panel that
    indexes into an empty tuple would crash on the last stage of a run."""
    from hack_and_slash.game import jobs
    from hack_and_slash.render.job_panel import JobPanel

    scene = promotion_scene(atlas)
    jobs.promote(scene.run, jobs.offers_for(scene.run)[0])
    assert jobs.offers_for(scene.run) == ()

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    surface.fill((0, 0, 0))
    JobPanel().draw(surface, scene.run, atlas)
    assert is_blank(surface), "the panel painted a frame with no choice in it"


def test_a_number_key_takes_that_path(atlas) -> None:
    scene = promotion_scene(atlas, "rogue")
    hero = scene.world.hero

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))

    assert scene.run.job_id == "shadow_rogue"
    assert hero.type is BESTIARY["shadow_rogue"]
    assert not scene.promoting, "the panel stayed up after a choice was made"


def test_enter_does_not_dismiss_the_choice(atlas) -> None:
    """The one screen in the game with no way out.

    Enter has meant "go" on the previous twenty transitions, so it is the key
    most likely to be pressed here by habit -- and half a campaign now sits
    behind this panel, tuned for a class the player would be declining to
    become. It used to close this panel, back when the answer only had to hold
    for one fight.
    """
    scene = promotion_scene(atlas)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert scene.promoting, "Enter dismissed the promotion panel"
    assert scene.run.job_id == ""
    assert scene.world.hero.type is BESTIARY["knight"]


def test_escape_neither_declines_nor_leaves_the_run(atlas) -> None:
    """Escape is swallowed here exactly as it is behind the shop.

    Two separate wrong outcomes to rule out: dropping somebody out of a run they
    were only trying to shut a panel on, and declining a fork there is no
    declining.
    """
    from hack_and_slash.game import jobs

    exited = []
    scene = PlayScene(
        campaign(),
        BESTIARY,
        atlas,
        start_stage=jobs.PROMOTION_STAGE - 1,
        on_exit=lambda: exited.append(True),
    )
    scene.promoting = True

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) is None
    assert scene.promoting, "Escape dismissed the promotion panel"
    assert not exited


def test_the_panel_pauses_the_world_and_swallows_the_controls(atlas) -> None:
    scene = promotion_scene(atlas)
    before = scene.world.tick

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f))
    scene.update(1.0)

    assert scene.world.tick == before, "the world advanced while the panel was open"
    assert scene._skill_pressed is None, "a skill press leaked past the panel"


def test_the_panel_takes_keys_ahead_of_the_shop(atlas) -> None:
    """Both are open on this one transition and the panel is drawn on top, so it
    is the one that must answer a keypress. Key 1 means a class here and a
    Poultice in the shop underneath."""
    from hack_and_slash.game import shop

    scene = promotion_scene(atlas)
    scene.shopping = True
    scene.run.gold = 100000
    scene.world.hero.hp = 10

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))

    assert scene.run.job_id == "dark_knight"
    assert shop.bought(scene.run, shop.stock()[0]) == 0, "the shop took the keypress too"


def test_the_choice_is_offered_on_one_transition_and_no_other(atlas) -> None:
    """Clearing stage one opens the shop and nothing else; clearing the stage
    before the fork opens both.

    The three cases are the whole contract: too early, the transition itself,
    and any transition after it -- the last one matters because `just_advanced`
    fires on all of them and only `at_promotion_point` tells them apart.
    """
    from hack_and_slash.game import jobs

    def cleared(start: int) -> PlayScene:
        """Clear the arena, then walk out of the room that follows it.

        Both halves, because the promotion fires on arriving at the *next
        arena* and a reward room now sits between the two. Stopping at the room
        would be testing that the fork is not offered inside a fountain, which
        is true and is not what this is about.
        """
        scene = PlayScene(campaign(), BESTIARY, atlas, start_stage=start)
        for enemy in scene.world.enemies():
            enemy.hp = 0
        scene.update(1.0)
        return out_through_a_door(scene)

    early = cleared(0)
    assert early.run.stage_number == 2
    assert not early.promoting, "promotion was offered on the way into stage two"

    fork = cleared(jobs.PROMOTION_STAGE - 2)
    assert fork.run.stage_number == jobs.PROMOTION_STAGE
    assert fork.promoting, "the fork did not offer a promotion"

    after = cleared(jobs.PROMOTION_STAGE)
    assert not after.promoting, "promotion was offered a second time"


def test_no_job_column_overflows_its_half_of_the_panel(atlas) -> None:
    """Two columns in 384 pixels, and the longest of them is 'Magic Archer' over
    'F Starfall 90'. Measured with the panel's own fonts so renaming a class or
    an attack shows up here rather than on screen."""
    from hack_and_slash.render import job_panel as panel

    drawn = panel.JobPanel()
    half = config.INTERNAL_W // len(panel.COLUMN_X)

    for base in BESTIARY.hero_classes:
        for index, advanced in enumerate(BESTIARY.promotions_for(base.id)):
            centre = panel.COLUMN_X[index]
            widest = max(
                drawn.font.size(advanced.name)[0],
                *(drawn.small.size(text)[0] for text, _ in drawn._lines(base, advanced)),
            )
            assert widest <= half, (
                f"{advanced.id}'s widest line is {widest}px in a {half}px column"
            )
            assert centre - widest // 2 >= 0, f"{advanced.id} runs off the left edge"
            assert centre + widest // 2 <= config.INTERNAL_W, (
                f"{advanced.id} runs off the right edge"
            )


def test_the_job_panel_clears_the_portrait_and_the_hud(atlas) -> None:
    """The name landed inside the portrait frame on the first draft. The frame
    is `cell + 6` tall and centred below `PORTRAIT_Y`, so the two numbers have
    to be checked against each other rather than eyeballed."""
    from hack_and_slash.render import job_panel as panel

    cell = config.TILE * panel.PORTRAIT_SCALE
    frame_bottom = panel.PORTRAIT_Y + cell // 2 + (cell + 6) // 2
    assert panel.NAME_Y >= frame_bottom, "the class name is drawn inside its own portrait"

    last_stat = panel.STAT_Y + 2 * panel.STAT_LINE_H
    assert last_stat < panel.HINT_Y, "the hint overlaps the stat lines"
    assert panel.HINT_Y + 13 <= config.VIEWPORT_H, "the hint is drawn under the HUD"


def test_the_stage_banner_never_draws_over_a_panel(atlas, monkeypatch) -> None:
    """Clearing a stage sets the banner *and* opens the shop, so both want the
    same pixels. The banner has to lose and keep its remaining frames for after.

    This is a regression test with a real regression behind it: when the
    promotion panel was inserted between the shop's `if` and the banner's
    `elif`, the `elif` re-attached to the new `if` and the banner started
    drawing straight through the shop's title on eighteen of a run's nineteen
    transitions. Asserted by watching whether `_draw_banner` is called rather
    than by reading pixels, so it fails for the right reason.
    """
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene = PlayScene(campaign(), BESTIARY, atlas)
    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)

    # Both live at once is now a stall reached while the room's own banner is
    # still counting down -- the same collision, one room later.
    at_a_stall(scene)
    assert scene.shopping and scene.banner > 0, "the trap needs both live at once"

    drawn = []
    monkeypatch.setattr(scene, "_draw_banner", lambda surface: drawn.append("banner"))

    scene.draw(surface)
    assert not drawn, "the stage banner drew over the shop"

    # And over the promotion panel, which sits on top of the shop.
    scene.promoting = True
    scene.draw(surface)
    assert not drawn, "the stage banner drew over the promotion panel"

    # Dismiss both and the banner gets the frames it still has left.
    scene.promoting = False
    scene.shopping = False
    scene.draw(surface)
    assert drawn == ["banner"], "the banner lost its remaining frames to the panel"


# --- the level panel ---------------------------------------------------------
def test_the_level_panel_draws_every_attribute(atlas) -> None:
    from hack_and_slash.game import progression
    from hack_and_slash.render.level_panel import LevelPanel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.run.hero_level = 4
    scene.run.unspent_points = 9

    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    LevelPanel().draw(surface, scene.run)
    assert not is_blank(surface)

    # Seven rows on seven keys, and the panel and the scene must agree about
    # which digit is which -- a mismatch spends a point on the wrong attribute
    # and nothing anywhere would report it.
    from hack_and_slash.render.level_panel import LABELS, ROW_KEYS

    assert len(ROW_KEYS) == len(progression.SPENDABLE)
    assert set(LABELS) == set(progression.SPENDABLE)


def test_the_level_panel_draws_only_what_the_shrine_offered(atlas) -> None:
    """Three of eight, not all eight -- that is what makes a point a decision.

    Asserted on `rows()` because that tuple is the thing both the panel and
    `PlayScene._handle_level_event` index into. If it were ever built twice, a
    digit would spend a point on the row above or below the one drawn and
    nothing anywhere would report it.
    """
    from hack_and_slash.game import progression
    from hack_and_slash.render import level_panel as panel

    offered = progression.offers(5, 3, 3)
    assert panel.rows(offered) == offered
    assert len(offered) == 3


def test_the_level_panel_falls_back_to_every_attribute(atlas) -> None:
    """`shrine.offers: 8` is the rollback to the panel this used to be, and an
    empty offer is what a level reached outside a reward room hands it -- which
    is the shape the day `xp_base` stops being zero."""
    from hack_and_slash.game import progression
    from hack_and_slash.render import level_panel as panel

    assert panel.rows(()) == progression.SPENDABLE


def test_the_shrine_panel_is_named_for_the_room(atlas) -> None:
    """`LEVEL n` is kept for a level reached on a stage boundary, where there is
    no shrine standing in front of anybody to name."""
    from hack_and_slash.core.level import RoomKind
    from hack_and_slash.render.level_panel import LevelPanel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.run.unspent_points = 1

    drawn = LevelPanel()
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))

    scene.run.room = RoomKind.SHRINE
    drawn.draw(surface, scene.run, ("damage", "defense", "regen"))
    shrine = surface.copy()

    surface.fill((0, 0, 0))
    scene.run.room = None
    drawn.draw(surface, scene.run, ("damage", "defense", "regen"))

    assert not is_blank(shrine)
    assert pygame.image.tobytes(shrine, "RGB") != pygame.image.tobytes(surface, "RGB")


def test_pressing_a_shrine_key_spends_on_the_row_that_was_drawn(atlas) -> None:
    """The end-to-end version of the row/key contract, through the scene.

    Key 1 must spend on offer 0 and not on `SPENDABLE[0]` -- those were the same
    attribute before the shrine rolled anything, and a test that did not force
    them apart would pass either way.
    """
    from hack_and_slash.game import progression

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.run.unspent_points = 1
    scene.shrine_offers = ("regen", "defense", "damage")
    scene.levelling = True

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))

    assert scene.run.earned.regen == progression.table().points["regen"]
    assert scene.run.earned.max_hp == 0, "key 1 spent on SPENDABLE[0] instead"
    assert not scene.levelling, "the panel stayed up with no points left"


def test_a_shrine_key_past_the_offer_does_nothing(atlas) -> None:
    """Eight keys, three rows. Pressing 4 at a shrine must not reach a row that
    is not on the plinth."""
    from hack_and_slash.game.attributes import NEUTRAL

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.run.unspent_points = 1
    scene.shrine_offers = ("regen", "defense", "damage")
    scene.levelling = True

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4))

    assert scene.run.unspent_points == 1
    assert scene.run.earned is NEUTRAL, "key 4 spent on a row that is not there"
    assert scene.levelling


def test_the_level_panel_fits_above_the_hud() -> None:
    """Seven rows is two more than any other panel in the game has, on a
    viewport 188px tall. Drafted at ROW_H 22 and the last row sat under the
    health bar."""
    from hack_and_slash.render import level_panel as panel

    rows = len(panel.ROW_KEYS)
    last_row = panel.ROW_Y + (rows - 1) * panel.ROW_H
    assert last_row < panel.hint_y(rows)
    assert panel.hint_y(rows) + 11 <= config.VIEWPORT_H

    # A shrine draws three, and the hint comes up to meet them.
    assert panel.hint_y(3) < panel.hint_y(rows)


def test_the_hud_says_nothing_about_levels_until_there_is_one(atlas) -> None:
    """While progression ships off the hero is level 1 for the whole game, so
    this strip has to stay exactly the one that was there before attributes
    existed -- the pixel counterpart of the arithmetic claim."""
    scene = PlayScene(campaign(), BESTIARY, atlas)
    quiet = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.hud.draw(quiet, scene.world, scene.run, 0)

    scene.run.hero_level = 7
    loud = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.hud.draw(loud, scene.world, scene.run, 0)

    assert pygame.image.tobytes(quiet, "RGB") != pygame.image.tobytes(loud, "RGB")


def test_a_level_panel_opened_on_a_stage_boundary_offers_everything(atlas) -> None:
    """A point banked at a shrine and spent at the next transition is spent
    against all eight, not against that shrine's three.

    The shrine's roll belongs to the room it was rolled in. Left standing, the
    player would be offered a plinth from a room they walked out of two stages
    ago, and the only symptom would be that it looked oddly familiar.
    """
    from hack_and_slash.game import progression
    from hack_and_slash.render import level_panel as panel

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.shrine_offers = ("regen", "defense", "damage")
    scene.run.unspent_points = 1

    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)          # into the reward room
    out_through_a_door(scene)  # and on to the next arena

    assert scene.levelling, "a banked point did not reopen the panel"
    assert scene.shrine_offers == ()
    assert panel.rows(scene.shrine_offers) == progression.SPENDABLE


# --- the hero panel ----------------------------------------------------------
def test_the_hero_panel_draws_every_attribute(atlas) -> None:
    """Eight rows, every time. That is the one way it differs from the shrine's
    plinth, which draws the three it rolled -- a decision is about what is in
    front of you, and a readout that hid five of your numbers is a worse answer
    to every question it gets opened for."""
    from hack_and_slash.game import progression
    from hack_and_slash.render.hero_panel import ROWS, HeroPanel
    from hack_and_slash.render.level_panel import LABELS

    scene = PlayScene(campaign(), BESTIARY, atlas)
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    HeroPanel().draw(surface, scene.run)

    assert not is_blank(surface)
    assert ROWS == progression.SPENDABLE
    assert set(LABELS) == set(ROWS), "an attribute with no name to draw"


def test_the_hero_panel_splits_the_class_from_what_the_run_earned(atlas) -> None:
    """The middle column is the whole point of the panel.

    A piece bought at a stall dissolves into `run.earned` on the way in, so
    before this there was nowhere at all to see that it had done anything --
    seven of the eight attributes had no readout in the shipped game.
    """
    from hack_and_slash.game.attributes import Attributes
    from hack_and_slash.render.hero_panel import values

    scene = PlayScene(campaign(), BESTIARY, atlas)
    run = scene.run

    base, earned, total = values(run, "crit_chance")
    assert base == run.hero_type.attributes.crit_chance
    assert earned == 0, "a fresh run has earned nothing"
    assert total == base

    run.earned = run.earned + Attributes(crit_chance=45)
    base, earned, total = values(run, "crit_chance")
    assert (earned, total) == (45, base + 45)


def test_the_hero_panels_health_row_agrees_with_the_health_bar(atlas) -> None:
    """`max_hp` is the one row that is not a field of two blocks, and it is the
    one row a player can check against something else on screen.

    A class's health lives in `EntityType.hp`, which predates the attribute
    layer; its block carries only what is added on top. So the literal reading
    prints `Health 0 + 24 = 24` beside a HUD saying `154/154` -- not a rounding
    disagreement, but the panel and the health bar meaning different things by
    one word.
    """
    from hack_and_slash.game.attributes import Attributes
    from hack_and_slash.game.progression import grant
    from hack_and_slash.render.hero_panel import values

    scene = PlayScene(campaign(), BESTIARY, atlas)
    grant(scene.run, Attributes(max_hp=24))

    base, earned, total = values(scene.run, "max_hp")
    assert base == scene.run.hero_type.full_hp
    assert earned == 24
    assert total == scene.run.max_hp
    assert total == scene.world.hero.max_hp, "the sheet and the health bar disagree"


def test_the_hero_panels_damage_row_is_a_light_swing(atlas) -> None:
    """The second row that is not a field of two blocks, and it is not a
    decoration.

    Every hero in `data/entities.json` ships a fully neutral attribute block, so
    read literally the class column would be zeroes all the way down for every
    class in the game -- and a Knight whose sword does twelve would be told his
    class brings 0 Damage.

    `combat.resolve_damage` adds `Attributes.damage` flat to the rolled weapon
    number before the crit, so the total here is exactly what a light swing hits
    for before variance.
    """
    from hack_and_slash.game import skills
    from hack_and_slash.game.attributes import Attributes
    from hack_and_slash.game.progression import grant
    from hack_and_slash.render.hero_panel import values

    scene = PlayScene(campaign(), BESTIARY, atlas)
    grant(scene.run, Attributes(damage=3))

    light = scene.run.hero_type.weapons[skills.LIGHT].damage
    assert light > 0, "the fixture class has no light attack to measure"

    base, earned, total = values(scene.run, "damage")
    assert base == light
    assert (earned, total) == (3, light + 3)


def test_the_hero_panels_class_column_is_never_empty(atlas) -> None:
    """The panel has to say something about the class on a fresh run, for every
    class in the game.

    While the attribute blocks all ship neutral, health and damage are the only
    two rows that can -- which is the whole argument for special-casing them, and
    the day somebody puts crit on the Assassin this test goes on passing.
    """
    from hack_and_slash.render.hero_panel import ROWS, values

    for hero_type in BESTIARY.hero_classes + BESTIARY.advanced_classes:
        scene = PlayScene(campaign(), BESTIARY, atlas, hero_type_id=hero_type.id)
        columns = [values(scene.run, name)[0] for name in ROWS]
        assert any(columns), f"{hero_type.name} is told its class brings nothing"


def test_the_hero_panel_follows_a_promotion(atlas) -> None:
    """`Run.hero_type` reads `job_id or hero_type_id`, so a promoted sheet is the
    advanced class's for free. Pinned because that property has been read
    correctly and used wrongly once already -- see the note in `Run._advance`."""
    from hack_and_slash.game import jobs
    from hack_and_slash.render.hero_panel import values

    scene = PlayScene(campaign(), BESTIARY, atlas)
    offers = jobs.offers_for(scene.run)
    if not offers:
        pytest.skip("this class has no promotions declared")

    jobs.promote(scene.run, offers[0])

    assert scene.run.hero_type.id == offers[0].id
    assert values(scene.run, "max_hp")[0] == scene.run.hero_type.full_hp


def test_i_opens_and_closes_the_hero_panel(atlas) -> None:
    scene = PlayScene(campaign(), BESTIARY, atlas)
    assert not scene.inspecting

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
    assert scene.inspecting

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
    assert not scene.inspecting, "the sheet does not toggle"


def test_the_hero_panel_stops_the_arena(atlas) -> None:
    """It pauses, which is what makes it a panel rather than an overlay.

    The accumulator is not fed either -- banking real seconds behind it would
    fast-forward the fight the instant it closed, which is the trap the shop
    already records.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.update(1.0)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
    tick = scene.world.tick
    scene.update(1.0)
    assert scene.world.tick == tick, "the arena was stepped behind the sheet"

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
    scene.update(1.0)
    assert scene.world.tick > tick, "the arena did not resume"


def test_the_hero_panel_changes_nothing_at_all(atlas) -> None:
    """The one panel with no function in `game/` behind it. Every other one sits
    in front of a decision; this one is a readout, and closing it has to leave
    the run exactly what it was."""
    from hack_and_slash.game import save

    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.update(1.0)
    before = save.snapshot(scene.run)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.draw(surface)
    # Not Space -- that is one of the exit keys, deliberately, because every
    # other panel in the game closes on it.
    for key in (pygame.K_1, pygame.K_q, pygame.K_j):
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
    scene.update(1.0)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))

    assert not scene.inspecting, "Tab did not close the sheet"
    assert save.snapshot(scene.run) == before


def test_escape_closes_the_hero_panel_rather_than_leaving_the_run(atlas) -> None:
    """The shop's trade, made again. Dropping somebody out of a forty-stage run
    because they reached for Escape to shut a panel is not worth making."""
    left = []

    def on_exit():
        left.append(True)
        return "menu"

    scene = PlayScene(campaign(), BESTIARY, atlas, on_exit=on_exit)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
    result = scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert result is None and not left, "Escape left the run from behind the sheet"
    assert not scene.inspecting

    # And once the sheet is shut it pauses rather than leaving. It used to mean
    # the menu here, on one press; the menu is now a row on the overlay.
    onward = scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert onward is None and not left, "Escape still left the run in one press"
    assert scene.paused


# --- the pause overlay -------------------------------------------------------
def paused(atlas, **kwargs) -> PlayScene:
    scene = PlayScene(campaign(), BESTIARY, atlas, **kwargs)
    scene.update(1 / 60)  # one live frame, so the world is genuinely running
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert scene.paused, "Escape did not pause"
    return scene


def test_a_fight_never_begins_paused(atlas) -> None:
    """One line, and it is the whole "the recorded grid is untouched" argument.

    `tools/balance.py` and `autoplay` drive `sim.step` and never build a scene,
    and `tests/test_playthrough.py` imports nothing from `scenes/` -- so the only
    way this feature could reach a measured number is by a constructor that
    started a fight already stopped. `tools/screenshot.py` builds one too.
    """
    assert PlayScene(campaign(), BESTIARY, atlas).paused is False
    assert PlayScene(campaign(), BESTIARY, atlas).restarted().paused is False


def test_escape_pauses_instead_of_leaving_the_run(atlas) -> None:
    """The whole feature, in the one press it exists to reinterpret.

    Escape used to call `on_exit` here and drop the scene on the floor. Every
    player presses it once expecting a pause.
    """
    left = []
    scene = PlayScene(
        campaign(), BESTIARY, atlas, on_exit=lambda: left.append(True) or "menu"
    )

    result = scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert result is None and not left, "Escape still left the run"
    assert scene.paused


def test_escape_resumes_a_paused_fight(atlas) -> None:
    """It toggles. The one press a player is certain to make is the one that
    got them here, so it has to be the one that gets them out."""
    scene = paused(atlas)

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) is None
    assert not scene.paused


def test_the_resume_row_resumes(atlas) -> None:
    scene = paused(atlas)
    scene.pause_index = [row for row, _ in PAUSE_ROWS].index("resume")

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)) is None
    assert not scene.paused


def test_the_quit_row_leaves_exactly_the_way_escape_used_to(atlas) -> None:
    scene = paused(atlas, on_exit=lambda: "menu")
    scene.pause_index = [row for row, _ in PAUSE_ROWS].index("quit")

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)) == "menu"


def test_quitting_with_nowhere_to_go_resumes_rather_than_stranding(atlas) -> None:
    """`on_exit=None` is not hypothetical -- the tools and most of this file
    build a scene without one. Leaving the overlay up over a scene nobody can
    leave is the one way this feature could trap somebody."""
    scene = paused(atlas)
    scene.pause_index = [row for row, _ in PAUSE_ROWS].index("quit")

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)) is None
    assert not scene.paused


def test_the_restart_key_is_swallowed_while_paused(atlas) -> None:
    """Restart stays on its own key, which means the overlay does not take it.

    A row that threw away a fifty-stage run on one Enter is the hazard this
    overlay exists to remove, not one to add to it.
    """
    scene = paused(atlas)

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)) is None
    assert scene.paused


def test_escape_on_the_death_screen_still_leaves(atlas) -> None:
    """The guard, and the reason it exists.

    `handle_event` has no `run.is_over` check of its own -- the death screen is
    drawn from the same arena branch that takes keys. Without this the overlay
    would open over the result and take away the only way off it, and its Quit
    row would name a save file that `_settle` has already deleted.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas, on_exit=lambda: "menu")
    scene.run.outcome = RunOutcome.LOST
    assert scene.run.is_over

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) == "menu"
    assert not scene.paused, "the overlay opened over the death screen"


def test_the_cursor_wraps_both_ways(atlas) -> None:
    scene = paused(atlas)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
    assert scene.pause_index == len(PAUSE_ROWS) - 1
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    assert scene.pause_index == 0


# --- what "paused" actually means --------------------------------------------
@pytest.mark.parametrize(
    "flag", ["paused", "shopping", "promoting", "levelling", "inspecting"]
)
def test_no_real_seconds_are_banked_behind_a_panel(atlas, flag) -> None:
    """The claim `update` has made in prose since it was written, asserted.

    Reaching into `Accumulator._banked` on purpose. The observable symptom of
    getting this wrong is a fight that fast-forwards the instant a panel closes,
    and `MAX_FRAME_TIME` bounds it to fifteen ticks -- small enough to be missed
    in play, and impossible to catch from `world.tick` alone, because a scene
    that banked the time and paid it out later looks identical until it does.

    Parametrised over all five because the four that predate the overlay have
    never been checked either.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.update(1 / 60)
    setattr(scene, flag, True)

    banked, tick = scene.accumulator._banked, scene.world.tick
    scene.update(5.0)

    assert scene.accumulator._banked == banked, "real seconds were banked"
    assert scene.world.tick == tick, "the world was stepped"

    setattr(scene, flag, False)
    scene.update(config.DT)
    assert scene.world.tick == tick + 1, "the banked seconds arrived late"


def test_pausing_drops_a_buffered_dodge(atlas) -> None:
    """Free -- it is the guard being extended, not new code -- but it is the
    behaviour that stops a roll coming out into a room the player cannot see."""
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert scene._dodge_buffer > 0

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    scene.update(1 / 60)
    assert scene._dodge_buffer == 0


def test_hitstop_survives_a_pause(atlas) -> None:
    """Correct only by where the counter lives, so it is worth pinning.

    `freeze` is decremented *inside* the tick loop, which the guard returns
    before -- so a pause holds it rather than draining it, and the hit the
    player was in the middle of feeling still lands with its full weight.
    """
    scene = paused(atlas)
    scene.freeze = 5

    for _ in range(10):
        scene.update(1 / 60)
    assert scene.freeze == 5, "hitstop drained behind the overlay"

    scene.paused = False
    scene.update(config.DT)
    assert scene.freeze == 4


def test_the_banner_does_not_count_down_behind_the_overlay(atlas) -> None:
    scene = paused(atlas)
    scene.banner = 60

    scene.update(1.0)
    assert scene.banner == 60


def test_no_panel_can_open_while_paused(atlas) -> None:
    """The invariant the handler ordering documents, checked from the other end.

    `_open_panels_for_props` runs inside the tick loop, which the guard returns
    before -- so a hero standing on a stall cannot have it open behind a pause.
    """
    scene = paused(atlas)
    asked = []
    scene._open_panels_for_props = lambda: asked.append(True) or False

    scene.update(1.0)
    assert not asked, "a panel was offered behind the overlay"
    assert not (scene.shopping or scene.levelling or scene.promoting)


@pytest.mark.parametrize("panel", ["shopping", "levelling", "promoting", "inspecting"])
def test_escape_does_not_pause_from_behind_a_panel(atlas, panel) -> None:
    """Each of the four already answers Escape, and none of those answers moved.

    The promotion panel is the one that matters: it deliberately has no exit key
    at all, and a pause overlay reachable from it would be a way to walk out of
    the fork with the run intact.
    """
    scene = PlayScene(campaign(), BESTIARY, atlas, on_exit=lambda: "menu")
    setattr(scene, panel, True)

    assert scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) is None
    assert not scene.paused, f"Escape paused from behind the {panel} panel"

    if panel == "promoting":
        assert scene.promoting, "Escape dismissed the promotion panel"


# --- the overlay on screen ---------------------------------------------------
def test_the_overlay_draws_something(atlas) -> None:
    scene = paused(atlas)
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))
    scene.draw(surface)
    assert not is_blank(surface)


def test_the_banner_never_draws_behind_the_overlay(atlas) -> None:
    """Same trade the four panels make, and pinned the same way.

    Compared pixel for pixel rather than by stubbing, because the overlay is a
    leading `elif` and the failure mode is the banner's text bleeding through
    the wash rather than a call that did or did not happen.
    """
    scene = paused(atlas)
    surface = pygame.Surface((config.INTERNAL_W, config.INTERNAL_H))

    scene.banner = BANNER_FRAMES
    scene.draw(surface)
    with_banner = pygame.image.tobytes(surface, "RGB")

    scene.banner = 0
    scene.draw(surface)
    assert pygame.image.tobytes(surface, "RGB") == with_banner


def test_every_pause_row_fits_beside_its_note(atlas) -> None:
    """Measured with the panel's own fonts, in the shape the other panels use.

    The note is the half that grows: `kept()` carries a stage number, and the
    campaign is fifty stages long now where it was twenty twice before.
    """
    from hack_and_slash.render import pause_panel as panel

    drawn = panel.PausePanel()
    for i, (row, label) in enumerate(panel.ROWS):
        assert panel.ROW_X + drawn.font.size(label)[0] <= panel.NOTE_X, (
            f"'{label}' runs into its note"
        )
        assert panel.row_y(i) + 11 <= panel.hint_y(len(panel.ROWS)), (
            f"'{label}' is drawn through the hint"
        )

    widest = max(f"keeps stage {n}" for n in (1, 50))
    assert panel.NOTE_X + drawn.small.size(widest)[0] <= config.INTERNAL_W
    assert panel.TITLE_Y + 17 <= panel.ROW_Y, "the title is drawn over the first row"
    assert panel.hint_y(len(panel.ROWS)) + 8 <= config.VIEWPORT_H, (
        "the hint line is drawn under the HUD"
    )
    assert drawn.small.size(panel.HINT)[0] <= config.INTERNAL_W


def test_the_hero_panel_cannot_open_over_a_decision(atlas) -> None:
    """The other three panels are decisions and this is a readout. A readout has
    no business interrupting one -- and the digits those panels are listening for
    would be swallowed by the sheet's handler if it could sit in front of them."""
    scene = PlayScene(campaign(), BESTIARY, atlas)

    for panel in ("shopping", "levelling", "promoting"):
        setattr(scene, panel, True)
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
        assert not scene.inspecting, f"the sheet opened over the {panel} panel"
        setattr(scene, panel, False)


def test_opening_the_hero_panel_drops_a_buffered_dodge(atlas) -> None:
    """A roll pressed on the way in must not come out on the far side of the
    pause -- the same reason the shop drops its edges rather than ageing them."""
    scene = PlayScene(campaign(), BESTIARY, atlas)

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert scene._dodge_buffer > 0

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i))
    scene.update(1.0)
    assert scene._dodge_buffer == 0


def test_the_hero_panel_takes_the_screen_from_the_banner(atlas) -> None:
    """A panel or the banner, never both. An `elif` on that chain is how the
    banner started drawing over the shop when the promotion panel was added
    between them, which is why the fourth panel is a fourth `if`."""
    scene = PlayScene(campaign(), BESTIARY, atlas)
    scene.banner = 60
    scene.inspecting = True

    drawn = []
    scene._draw_banner = lambda surface: drawn.append("banner")
    scene.hero_panel.draw = lambda *args, **kwargs: drawn.append("sheet")

    scene.draw(pygame.Surface((config.INTERNAL_W, config.INTERNAL_H)))
    assert drawn == ["sheet"], "the banner drew over the character sheet"


def test_the_hero_panel_fits_above_the_hud() -> None:
    """Eight rows is the tallest any panel in this game gets, on a viewport
    188px tall -- so this one is `level_panel.py`'s geometry at its limit, which
    is exactly why it imports those constants rather than redrafting them."""
    from hack_and_slash.render import hero_panel as panel

    rows = len(panel.ROWS)
    last_row = panel.ROW_Y + (rows - 1) * panel.ROW_H
    assert last_row < panel.hint_y(rows)
    assert panel.hint_y(rows) + 11 <= config.VIEWPORT_H

    # The columns are inset by the same margin on both sides, and ascend.
    assert panel.TOTAL_RIGHT == config.INTERNAL_W - panel.LEFT
    assert panel.LEFT < panel.BASE_RIGHT < panel.EARNED_RIGHT < panel.TOTAL_RIGHT


def test_the_hero_panels_columns_clear_its_labels_and_its_title(display) -> None:
    """Measured against the real fonts and the longest class in the game, the way
    `test_menu.py` measures the controls list -- fixed columns are only fixed
    until somebody adds a name that runs through them."""
    from hack_and_slash.render import hero_panel as panel
    from hack_and_slash.render.hero_panel import HeroPanel
    from hack_and_slash.render.level_panel import LABELS

    drawn = HeroPanel()

    widest = max(drawn.font.size(label)[0] for label in LABELS.values())
    first_column = panel.BASE_RIGHT - max(
        drawn.small.size(head)[0] for head, _ in panel.COLUMN_HEADS
    )
    assert panel.LEFT + widest < first_column, "a label runs into the class column"

    # The name shares the column-head line, which is why it is left-aligned.
    # Both halves of the roster: the longest name in the game belongs to an
    # advanced class, and a sheet is read on the far side of the fork too.
    every = BESTIARY.hero_classes + BESTIARY.advanced_classes
    longest = max(every, key=lambda t: len(t.name)).name
    line = f"{longest}  --  Lv 40"
    assert panel.LEFT + drawn.font.size(line)[0] < first_column, (
        f"'{line}' runs into the column heads"
    )
