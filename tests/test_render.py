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
from hack_and_slash.game.entities import ActionState
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

    # Rich, hurt, and with one good already capped out.
    scene.run.gold = 100000
    scene.world.hero.hp = 10
    for good in shop.stock():
        for _ in range(good.limit or 1):
            shop.buy(scene.run, good)
    scene.draw(surface)
    assert not is_blank(surface)


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


def test_clearing_a_stage_opens_the_shop_with_the_takings_already_banked(atlas) -> None:
    """The order matters: `Run._advance` banks before it replaces the world, so
    the purse the panel shows is the real one rather than a stage behind."""
    scene = PlayScene(campaign(), BESTIARY, atlas)

    for enemy in scene.world.enemies():
        enemy.hp = 0
    scene.update(1.0)

    assert scene.shopping, "clearing a stage did not open the shop"
    assert scene.run.stage_number == 2
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


def test_the_shop_rows_and_hint_fit_above_the_hud(atlas) -> None:
    """Measured against the fullest the shop ever gets, which is the late shelf.

    `stock()` rather than `available(run)` on purpose: the panel grows a row in
    the second half of the campaign, and the layout has to hold for the tallest
    version rather than the one that happens to be on screen first.
    """
    from hack_and_slash.game import shop
    from hack_and_slash.render import shop_panel as panel

    bottom = panel.ROW_Y + len(shop.stock()) * panel.ROW_H + 12 + 13
    assert bottom <= config.VIEWPORT_H, "the shop's hint line is drawn under the HUD"


def test_the_shop_has_a_key_for_every_row_it_can_draw(atlas) -> None:
    """The half of the row/key contract that lives with the keys.

    A good added to `data/loot.json` without a key here is a row a player can
    read and cannot buy, and nothing else would say so.
    """
    from hack_and_slash.game import shop
    from hack_and_slash.render import shop_panel as panel

    assert len(shop.stock()) <= len(panel.ROW_KEYS), (
        f"the shop stocks {len(shop.stock())} goods and the panel has "
        f"{len(panel.ROW_KEYS)} keys"
    )


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
        scene = PlayScene(campaign(), BESTIARY, atlas, start_stage=start)
        for enemy in scene.world.enemies():
            enemy.hp = 0
        scene.update(1.0)
        return scene

    early = cleared(0)
    assert early.shopping
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


def test_the_level_panel_fits_above_the_hud() -> None:
    """Seven rows is two more than any other panel in the game has, on a
    viewport 188px tall. Drafted at ROW_H 22 and the last row sat under the
    health bar."""
    from hack_and_slash.render import level_panel as panel

    last_row = panel.ROW_Y + (len(panel.ROW_KEYS) - 1) * panel.ROW_H
    assert last_row < panel.HINT_Y
    assert panel.HINT_Y + 11 <= config.VIEWPORT_H


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
