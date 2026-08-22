"""The run.

Three jobs, in order: turn real input into an `Intent`, feed the fixed-timestep
accumulator, and draw. The scene never reasons about combat -- it cannot, since
everything that decides a fight lives behind `sim.step`, which takes an Intent
and nothing else. It does not reason about progression either: `Run` owns what
carries between stages and when one is cleared.

Hitstop is run here rather than in the sim. On a solid connect the world simply
stops being stepped for a few frames while the renderer keeps drawing, which is
what gives a hit weight without changing a single number in the fight.

The panels use the same trick at a different scale: while one is open the world
is not stepped and the accumulator is not fed, so the room behind it is
genuinely stopped rather than merely hidden. Those are the only real pauses in a
run -- the between-stage banner deliberately is not one.

**The shop is no longer one of the things that happens between two stages.** It
used to open on every transition, all thirty-nine of them. It is now a fixture
standing in a reward room, and `_open_panels_for_props` is the only thing that
opens it -- so a player who wants to spend has to have chosen the door with a
stall over it, two rooms earlier. The panel, its keys and its exit keys are all
unchanged; what went is the automatic trigger.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import pygame

from .. import config
from ..core.campaign import Campaign
from ..core.level import PropKind
from ..core.vec2 import ZERO, Vec2
from ..game import (
    actions,
    equipment,
    jobs,
    profile,
    progression,
    rooms,
    save,
    shop,
    skills,
)
from ..game.entities import DEFAULT_HERO, Bestiary
from ..game.intent import Intent
from ..game.difficulty import NORMAL as NORMAL_DIFFICULTY, Difficulty
from ..game.run import Run, RunOutcome
from ..game.sim import Accumulator, step
from ..render import level_panel as level_rows
from ..render import shop_panel as shop_rows
from ..render.atlas import Atlas
from ..render.camera import Camera
from ..render.effects import Effects
from ..render.hero_panel import HeroPanel
from ..render.hud import Hud
from ..render.job_panel import CHOICE_KEYS, JobPanel
from ..render.level_panel import ROW_KEYS as LEVEL_ROW_KEYS
from ..render.level_panel import LevelPanel
from ..render.pause_panel import ROWS as PAUSE_ROWS
from ..render.pause_panel import PausePanel
from ..render.renderer import Renderer
from ..render.shop_panel import ROW_KEYS, ShopPanel
from ..bindings import Action
from ..settings import Settings
from . import keymap
from .base import Scene
from .options import OptionsScene

#: Which way each movement action pushes. The *directions* are the game and the
#: *keys* are a preference, so this stays here as a constant while which key
#: reaches it lives in `bindings.py` and is edited on the Controls screen.
MOVE_DIRECTIONS = {
    Action.MOVE_UP: Vec2(0, -1),
    Action.MOVE_DOWN: Vec2(0, 1),
    Action.MOVE_LEFT: Vec2(-1, 0),
    Action.MOVE_RIGHT: Vec2(1, 0),
}

#: How many simulation ticks a dodge press stays live, waiting for the sim to be
#: willing to take it.
#:
#: One more than `actions.STAGGER_TICKS`, and that is the whole derivation. The
#: press a player most wants honoured is the one made in the freeze after a hit
#: lands on them -- and because `freeze` drains without stepping, the stagger has
#: not started counting down when the freeze ends. A buffer shorter than the
#: stagger is spent on ticks that were always going to refuse it.
#:
#: Deliberately short. Long enough that a press made a moment early still comes
#: out; short enough that it is never a roll the player has stopped wanting. It
#: grants nothing `can_dodge` would refuse -- the sim is asked afresh every tick
#: and gets the last word.
DODGE_BUFFER_TICKS = actions.STAGGER_TICKS + 1

#: Which slot each attack action spends. Positional, like the boss weapons: the
#: sim selects by index, so index meaning is a contract between the content
#: files, the input and the HUD -- and `game/skills.py` names the indices rather
#: than letting bare integers appear in three places.
#:
#: The keys that reach these slots, and the reasoning behind the ones that
#: shipped, are in `bindings.DEFAULTS`.
SKILL_SLOTS = {
    Action.NEUTRAL: skills.NEUTRAL,
    Action.HEAVY: skills.HEAVY,
    Action.ULTIMATE: skills.ULTIMATE,
}

#: How long the between-stage banner stays up, in frames. Long enough to read
#: what you recovered, short enough that it never feels like a loading screen --
#: the next stage is already running underneath it.
BANNER_FRAMES = 110

#: Keys that close the shop and start the stage. Two of them because the panel
#: says "Enter" and a player halfway through a run reaches for Escape by habit;
#: Escape is "leave to the menu" everywhere else, and the shop is the one place
#: it is worth overriding rather than dropping somebody out of a run they were
#: only trying to shut a panel on.
SHOP_EXIT_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE)

#: How long a row key is ignored after a purchase that shortened the shelf.
#:
#: A bought row leaves the stall, so the row under it moves up and inherits the
#: digit. Held keys are not the hazard -- `pygame.key.set_repeat` is never called
#: here, so a KEYDOWN is a real press -- but a fast double-tap on 1 used to be a
#: no-op on a greyed row and would now buy whatever slid into its place, which is
#: a piece of gear nobody chose and several hundred gold.
#:
#: Counted in frames rather than seconds because the world is not being stepped
#: and there are no ticks to count: `update` still runs every frame with a panel
#: open, and this is the one thing it does there. Eight frames is about 130ms at
#: `FPS`, which is under the gap between two presses a player means as two.
#:
#: Only a purchase that actually removed a row starts it. Buying the third of
#: five Tonics moves nothing, and swallowing the next press there would be a key
#: that mysteriously does not work.
SHOP_SETTLE_FRAMES = 8

#: The promotion panel has no exit key, which makes it the only screen in the
#: game that a player cannot dismiss.
#:
#: It used to take the shop's set. That was right while promotion was a capstone
#: on the way into the last fight: one stage as an unmeasured class was a thing
#: to be able to say no to. It stopped being right when twenty stages moved in
#: behind the fork -- declining now means playing acts V-VIII with a kit those
#: acts are not tuned for, which is not a choice so much as a way to break a run
#: with one keypress by habit, on the transition where Enter has meant "go" for
#: the previous nineteen.
#:
#: So the arena stays paused until 1 or 2. Esc still leaves to the menu nowhere
#: here, exactly as it does behind the shop.

#: The level panel closes on the shop's keys, and *does* have an exit -- which
#: is the one way it differs from the promotion panel above.
#:
#: The difference is recoverability. `Run.unspent_points` carries between
#: stages, so declining here banks the points for a boss rather than throwing
#: them away; a fork declined is half a campaign played with the wrong kit. A
#: panel should only be inescapable when leaving it is unrecoverable.
LEVEL_EXIT_KEYS = SHOP_EXIT_KEYS

#: The sheet's own key is `Action.SHEET`, read only from the branch that runs
#: when no panel is up -- so the sheet cannot be opened over the shop, the
#: shrine or the fork. Those three are decisions and this is a readout; a
#: readout has no business interrupting one.
#:
#: It toggles, so its own key closes it as well as opens it, and it takes the
#: shop's exit keys too -- which means **Escape closes the sheet rather than
#: leaving to the menu**. The same trade the shop makes, for the same reason: a
#: player reaching for Escape to shut a panel is not asking to end a forty-stage
#: run.
#:
#: Unlike the shop's, this panel is *only* recoverable -- nothing is decided
#: behind it and nothing is lost by closing it at any moment. So there is no
#: argument here for the promotion panel's no-exit treatment, and every key that
#: could plausibly mean "close" does.
#:
#: Derived per scene rather than as a constant, because the sheet key is
#: rebindable and a rebound key has to close the panel it just opened.


class PlayScene(Scene):
    def __init__(
        self,
        campaign: Campaign,
        bestiary: Bestiary,
        atlas: Atlas,
        seed: int = 0,
        on_exit=None,
        start_stage: int = 0,
        hero_type_id: str = DEFAULT_HERO,
        run: Optional[Run] = None,
        settings: Optional[Settings] = None,
        difficulty: Difficulty = NORMAL_DIFFICULTY,
    ) -> None:
        self.campaign = campaign
        self.bestiary = bestiary
        self.atlas = atlas
        self.on_exit = on_exit

        # Defaulted, so a scene built the way every test and tool builds one is
        # the scene that was always here.
        self.settings = settings or Settings()

        self.renderer = Renderer(atlas)
        self.hud = Hud()
        self.shop_panel = ShopPanel()
        self.job_panel = JobPanel()
        self.level_panel = LevelPanel()
        self.hero_panel = HeroPanel()
        self.pause_panel = PausePanel()
        self.accumulator = Accumulator()
        self.effects = Effects()
        self._reapply_settings()

        # A run handed in is a run loaded off disk. The three parameters that
        # describe how to *start* one are then read back off it rather than
        # taken from the arguments, because `restarted()` uses them and R has to
        # mean "this run again" for a loaded run exactly as it does for a fresh
        # one -- the same seed, the same class, the same place it began.
        self.run = run if run is not None else Run.start(
            campaign,
            bestiary,
            seed=seed,
            at_stage=start_stage,
            hero_type_id=hero_type_id,
            difficulty=difficulty,
        )
        self.seed = self.run.seed
        self.start_stage = self.run.start_index
        self.hero_type_id = self.run.hero_type_id

        # Read back off the run for the same reason the three above are: a run
        # loaded off disk carries the tier it was begun on, and R has to mean
        # "this run again" rather than "this run, at whatever the argument
        # happened to default to".
        self.difficulty = self.run.difficulty

        # Replaced immediately by _enter_stage, which needs the stage's real
        # size. A placeholder rather than an Optional so nothing downstream has
        # to cope with the camera briefly not existing.
        self.camera = Camera(1, 1, config.INTERNAL_W, config.VIEWPORT_H)
        self.freeze = 0
        self.banner = 0

        #: Frames left in which a row key means nothing, after a purchase moved
        #: the rows up under the player's finger. See `SHOP_SETTLE_FRAMES`.
        self._shop_settle = 0

        #: Open between stages. While it is up the world is not stepped at all,
        #: which is the one real pause in a run -- the between-stage banner
        #: deliberately is not one, and the arena keeps fighting behind it.
        #: Spending gold is a decision, and a decision taken while a grunt walks
        #: up behind you is a decision taken badly.
        self.shopping = False

        #: What the stall in front of the hero has on it, and what the shrine
        #: has on its plinth. Rolled once, in `_open_panels_for_props`, and held
        #: for as long as the panel is up.
        #:
        #: **Held rather than re-derived per frame, and re-derived rather than
        #: saved.** Both rolls come from `(seed, index)` through the stateless
        #: streams in `rooms.py`, so a `PlayScene` rebuilt from a save rolls
        #: again and gets the same answer -- which is why `save.py` says nothing
        #: about either and did not have to change. Holding them is what makes
        #: the tuple the keys index and the tuple the panel draws provably the
        #: same object rather than two calls that happen to agree.
        self.stall_offers: tuple[equipment.Offer, ...] = ()
        self.shrine_offers: tuple[str, ...] = ()

        #: Open once per run, on the way into `jobs.PROMOTION_STAGE`, and ahead
        #: of the shop on that one transition. Ordered that way so the Poultice
        #: clamps against the *promoted* maximum health -- buying 30 health and
        #: having it clipped away by a class change a moment later is the only
        #: ordering that would surprise anybody.
        self.promoting = False

        #: Open on any transition that arrives with points to spend, between
        #: the promotion and the shop. That ordering is the same argument the
        #: promotion/shop ordering makes, one step further along: a point put
        #: into health raises the maximum a Poultice fills to, so spending has
        #: to resolve before buying or the shop clamps against a ceiling that is
        #: about to move.
        #:
        #: Never opens at all while `data/progression.json` ships `xp_base: 0`,
        #: because no point is ever earned.
        self.levelling = False

        #: Open on a keypress, and the only panel in the game that is. The other
        #: three are opened *at* the player by something the run did -- a stall
        #: touched, a level reached, a fork arrived at -- and each of them is a
        #: decision. This one is asked for, and it decides nothing: closing it
        #: leaves the run exactly what it was.
        #:
        #: It still pauses, which is what makes it a panel rather than an
        #: overlay. Reading eight numbers off a strip that is being shaken by a
        #: brute walking into you is not reading them.
        self.inspecting = False

        #: The fifth thing that stops the world, and the only one that is not
        #: about the run. The other four ask a question the run has raised --
        #: which piece, which attribute, which path, what have I got. This one
        #: asks nothing and decides nothing; it exists because Escape used to end
        #: the fight on the first press, and Escape is the key this whole genre
        #: has taught players means "pause".
        #:
        #: Set only from the arena branch of `handle_event`, which no panel
        #: reaches -- and while it is set `update` returns before the tick loop,
        #: so `_open_panels_for_props` never runs and no panel can open behind
        #: it. The five are mutually exclusive by construction rather than by
        #: arbitration, and the handler order below is documentation of that.
        self.paused = False
        self.pause_index = 0
        self._enter_stage()

        #: Set whenever the run is standing at the start of a stage with nothing
        #: yet done to it, and cleared by the write. It is a flag rather than a
        #: call because the *moment* to save is not the moment the stage begins:
        #: the promotion, level and shop panels all open on that tick and all
        #: three change what the run is. Saving before they are answered would
        #: record a run that had not promoted, or had not spent its gold, and
        #: loading it would silently take the fork away -- on the one transition
        #: in the game where the fork is offered exactly once.
        #:
        #: So the write happens on the first update with no panel up, which is
        #: also the first update that would step the world. Nothing has moved by
        #: then, which is the property `save.restore` depends on.
        self._needs_save = True

        #: A run ends once. Guards the delete and the profile write, both of
        #: which sit in `update` and would otherwise fire on every frame of the
        #: death screen.
        self._ended = False

        if run is None:
            # Counted here rather than at the character select, so a run begun
            # by any route -- the menu, `--class`, `restarted()` -- is counted
            # exactly once and on the same line. A run handed in was counted
            # when it was first begun and must not be counted again for being
            # picked back up.
            profile.record_start()

        #: Ticks a dodge press stays live, counted down by `_consume_edges` and
        #: by nothing else. Not a bool, and the difference is what makes the
        #: fix worth having.
        #:
        #: A press has to survive two separate things to become a roll. It has
        #: to reach a tick at all -- a frame can pay out none, and hitstop
        #: consumes ticks without stepping -- and then the sim has to accept it,
        #: which `actions.can_dodge` refuses while the hero is staggered. Those
        #: two interact badly: `freeze` drains *without stepping*, so `stagger`
        #: does not count down during it, and a press made while frozen arrives
        #: on the first stepped tick with the full stagger still to run. A press
        #: that survives one tick is a press refused.
        #:
        #: So it survives `DODGE_BUFFER_TICKS` of them. This is not a
        #: dodge-cancel: it grants nothing `actions.can_dodge` would refuse, it
        #: only stops a press being thrown away for arriving a few ticks early.
        #: The scene still reasons about no combat rule -- it re-asks, and the
        #: sim answers.
        self._dodge_buffer = 0

        #: Which skill slot was pressed since the last tick, or None. Edge
        #: triggered for the same reason dodge is, and for one more: a held key
        #: read from the key state would re-fire the skill on the exact tick its
        #: cooldown expired, forever. The decision of *when* to spend a skill is
        #: most of what makes it one, and leaning on a key is not a decision.
        self._skill_pressed: Optional[int] = None

    @property
    def world(self):
        return self.run.world

    def _enter_stage(self) -> None:
        """Point the camera at the stage now in play.

        Rebuilt rather than reused: stages are different sizes, and a camera
        still clamping to the previous stage's bounds shows the edge of the map.
        """
        self.camera = Camera(
            *self.world.level.pixel_size, config.INTERNAL_W, config.VIEWPORT_H
        )
        hero = self.world.hero
        if hero is not None:
            self.camera.snap_to(hero.pos)

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if self.paused:
            # First, and it is not a priority decision either -- see the note on
            # the flag. Pause and the four panels cannot both be up: Escape is
            # read only from the arena branch below, which none of them reach,
            # and no panel can open while the world is not being stepped. First
            # position turns that invariant into an enforcement rather than an
            # assumption.
            return self._handle_pause_event(event)

        if self.inspecting:
            # First, and it is not a priority decision. The sheet can only be
            # open when the other three are closed, because the key that opens
            # it is read from the branch below that none of them reach.
            return self._handle_sheet_event(event)

        if self.promoting:
            # Checked before the shop because it is drawn on top of it. Both are
            # open on this one transition and only the front one takes keys.
            return self._handle_job_event(event)

        if self.levelling:
            # Between the two, and for the same reason it is drawn between them:
            # the class is settled before the points are spent, and the points
            # are spent before the gold is.
            return self._handle_level_event(event)

        if self.shopping:
            # The shop swallows everything. Aiming, swinging and rolling are all
            # meaningless against a world that is not being stepped, and a skill
            # pressed here would come out on the first tick of the next stage.
            return self._handle_shop_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.run.is_over:
                    # The death screen is drawn from this same branch -- there is
                    # no `is_over` check above it -- and it has exactly two
                    # answers, both printed on it. Pausing a run that has ended
                    # is not one of them: the overlay would cover the result and
                    # take away the only way off it, and its Quit row would
                    # promise a save file that `_settle` has already deleted.
                    return self.on_exit() if self.on_exit else None
                self.paused = True
                self.pause_index = 0
                # Nothing else this frame, for the sheet's reason: the world
                # stops on the next update. The edges are dropped there rather
                # than here, because `update`'s guard is the one place a press is
                # deliberately thrown away and pause is not a second one.
                return None
            if event.key in self.keys[Action.RESTART]:
                return self.restarted()
            if event.key in self.keys[Action.SHEET]:
                self.inspecting = True
                # Nothing else this frame. The world stops on the next update,
                # and a swing queued on the way in would come out on the far
                # side of the pause.
                return None
            if event.key in self.keys[Action.DODGE]:
                self._dodge_buffer = DODGE_BUFFER_TICKS
            if event.key in self.skill_keys:
                # Highest slot wins when two arrive in one frame, and the slots
                # ascend by commitment -- so mashing resolves toward the thing
                # you least want swallowed rather than toward the cheapest.
                slot = self.skill_keys[event.key]
                if self._skill_pressed is None or slot > self._skill_pressed:
                    self._skill_pressed = slot
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._dodge_buffer = DODGE_BUFFER_TICKS
        return None

    def _handle_pause_event(self, event: pygame.event.Event) -> Optional[Scene]:
        """Resume, go to Settings, or leave. Everything else is swallowed.

        Including the restart key, which is the panel convention and is what
        "restart stays on its own key" means in practice -- a row that threw away
        a fifty-stage run on one Enter is the hazard this overlay exists to
        remove, not one to add to it.
        """
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            # It toggles, so the key that opened it closes it. The one press a
            # player is certain to make is the one that got them here.
            self.paused = False
        elif event.key in (pygame.K_UP, pygame.K_w):
            self.pause_index = (self.pause_index - 1) % len(PAUSE_ROWS)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.pause_index = (self.pause_index + 1) % len(PAUSE_ROWS)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            return self._activate_pause()
        return None

    def _activate_pause(self) -> Optional[Scene]:
        """Take the row under the cursor. Branched on id, never on label."""
        row = PAUSE_ROWS[self.pause_index][0]

        if row == "resume":
            self.paused = False
            return None

        if row == "settings":
            # `paused` stays set, so leaving that screen lands back on this
            # overlay rather than in a fight the player is not looking at.
            return OptionsScene(self.settings, self._resume_from_settings, in_run=True)

        # Quit. Byte for byte what Escape did before this overlay existed --
        # nothing is written and nothing is deleted, so what survives is the
        # autosave from the start of this room, which is what the row promises.
        nxt = self.on_exit() if self.on_exit else None
        if nxt is None:
            # Nowhere to go -- the tools and every test build a scene with no
            # `on_exit`. Resume rather than leave an overlay up over a scene
            # nobody can leave.
            self.paused = False
        return nxt

    def _resume_from_settings(self) -> "PlayScene":
        """This fight again, still paused, with the new preferences in force.

        The live instance rather than a rebuild -- `OptionsScene._resume` one
        level up, and for a sharper version of the same reason: a rebuilt
        `PlayScene` builds a fresh `Run`, which is precisely the thing a scene
        holding a run in progress may never do.
        """
        self._reapply_settings()
        return self

    def _handle_job_event(self, event: pygame.event.Event) -> Optional[Scene]:
        """Choose a path. There is no third answer.

        Every other key is swallowed, Escape included -- the note beside
        SHOP_EXIT_KEYS says why this one screen refuses to close. Closing on a
        choice, because it is asked once per run and a panel that stayed up
        afterwards would have nothing left to offer: `jobs.offers_for` is empty
        the moment a promotion lands.
        """
        if event.type != pygame.KEYDOWN:
            return None

        if event.key in CHOICE_KEYS:
            offers = jobs.offers_for(self.run)
            index = CHOICE_KEYS.index(event.key)
            if index < len(offers):
                jobs.promote(self.run, offers[index])
                self.promoting = False
        return None

    def _handle_sheet_event(self, event: pygame.event.Event) -> Optional[Scene]:
        """Close it. There is nothing else the sheet can be asked.

        Every other key is swallowed, which is what the other panels do and is
        the whole of why this is a panel: a swing or a roll pressed here would be
        pressed against a world that is not being stepped, and would arrive on
        the first tick after the sheet closed.
        """
        if event.type != pygame.KEYDOWN:
            return None

        if event.key in self.sheet_exit_keys:
            self.inspecting = False
        return None

    def _handle_shop_event(self, event: pygame.event.Event) -> Optional[Scene]:
        """Buy, or press on. Nothing else happens while the panel is up.

        A refused purchase is silent on purpose: the row was already greyed out
        before the key was pressed, and `equipment.can_buy` / `shop.can_buy` are
        what greyed it, so there is nothing to explain that the panel was not
        already saying.
        """
        if event.type != pygame.KEYDOWN:
            return None

        if event.key in SHOP_EXIT_KEYS:
            self.shopping = False
            # The shelf belongs to the room, not to the run. Dropped on the way
            # out so a stall two rooms later cannot inherit it if anything ever
            # opens this panel without rolling first.
            self.stall_offers = ()
            self._shop_settle = 0
            return None

        if event.key in ROW_KEYS:
            if self._shop_settle:
                # The rows moved a few frames ago and this press was aimed at
                # where they were. See `SHOP_SETTLE_FRAMES`.
                return None

            # `shop_rows.rows`, which is the one list the panel draws from --
            # gear on top, goods underneath, one continuous run of digits. A
            # second call to `shop.available` here would be a list that merely
            # happens to agree with the drawn one.
            shelf = shop_rows.rows(self.run, self.stall_offers)
            index = ROW_KEYS.index(event.key)
            if index < len(shelf):
                kind, item = shelf[index]
                if kind == "gear":
                    equipment.buy(self.run, item)
                else:
                    shop.buy(self.run, item)

                # Measured rather than predicted: a purchase removes a row when
                # it was the last one in it, and only `rows()` knows that -- the
                # cap lives in `data/loot.json` and the gear rule in
                # `equipment.taken`. Asking the list again is cheaper than
                # teaching this handler either of them.
                if len(shop_rows.rows(self.run, self.stall_offers)) < len(shelf):
                    self._shop_settle = SHOP_SETTLE_FRAMES
        return None

    def _handle_level_event(self, event: pygame.event.Event) -> Optional[Scene]:
        """Spend a point, or keep them. Nothing else happens while this is up.

        The panel closes on its own once the last point is gone, so a player who
        means to spend everything never has to dismiss it -- and one who means
        to bank a level for the boss presses Enter and keeps them.
        """
        if event.type != pygame.KEYDOWN:
            return None

        if event.key in LEVEL_EXIT_KEYS:
            self.levelling = False
            self.shrine_offers = ()
            return None

        if event.key in LEVEL_ROW_KEYS:
            # The shrine's three, not all eight -- and through the same
            # `rows()` the panel draws, for the reason the stall's shelf is.
            plinth = level_rows.rows(self.shrine_offers)
            index = LEVEL_ROW_KEYS.index(event.key)
            if index < len(plinth):
                progression.spend(self.run, plinth[index])
                self.levelling = self.run.unspent_points > 0
                if not self.levelling:
                    self.shrine_offers = ()
        return None

    def _reapply_settings(self) -> None:
        """Everything this scene derives from `Settings`, in one place.

        Called from `__init__` and again whenever the player comes back from the
        options screen, which the pause overlay makes reachable **from inside a
        fight**. Before that it could only be reached between runs, and reading
        the settings once at construction was the whole story.

        One method rather than two lists that must agree. That is not tidiness:
        two lists is the shape that guarantees the *eighth* preference is
        silently inert on resume, and a player who turns something off and sees
        nothing happen is worse off than one who was never offered the row.

        **The two effect flags are mutated, never rebuilt.** A fresh `Effects`
        would drop the damage numbers and the shake currently in flight -- they
        would blank mid-air on resume -- and would reseed its `rng`, which cannot
        reach a fight (`test_effects.py` pins that) but does make
        `tools/screenshot.py` stop reproducing.

        **`settings.seed` is deliberately absent**, and it is the one row on that
        screen this method must keep ignoring. The run took its seed at
        construction and `Run._stage_seed` derives from `run.seed`, so typing a
        new one on a paused run changes nothing about the run in progress. That
        is true by where the seed is read rather than by anything here, so it is
        pinned by a test: a refactor that read `settings.seed` at stage entry
        would let a player re-roll act VIII from a pause menu.
        """
        self.effects.screenshake = self.settings.screenshake
        self.effects.damage_numbers = self.settings.damage_numbers

        self.keys = keymap.keycodes(self.settings)
        self.move_keys = {
            code: direction
            for action, direction in MOVE_DIRECTIONS.items()
            for code in self.keys[action]
        }
        self.skill_keys = {
            code: slot
            for action, slot in SKILL_SLOTS.items()
            for code in self.keys[action]
        }
        # See the note above `MOVE_DIRECTIONS` about why this one is derived.
        self.sheet_exit_keys = SHOP_EXIT_KEYS + self.keys[Action.SHEET]
        #: What the HUD prints on each cooldown pip. Passed down rather than
        #: read there, so a pip cannot go on saying Q after the buff moved.
        self.skill_labels = {
            slot: keymap.label(action, self.settings)
            for action, slot in SKILL_SLOTS.items()
        }

    def restarted(self) -> "PlayScene":
        """A fresh run from stage one, as the same class.

        Restarting a *stage* would let a player grind the run's hardest fight at
        full health, which is the tension the carry-over exists to create. The
        class is kept because restart means "try that again" -- going back to
        the character select is what Esc is for.

        **The settings come with it**, which they did not before rebinding
        landed. The difficulty was passed here and the preferences were not, so
        a restart quietly put screenshake and the damage numbers back to their
        defaults -- invisible enough to have gone unnoticed. With the key
        bindings on the same object it stops being invisible: it would mean the
        keys reverting under a player who pressed restart, which reads as a
        broken build rather than as a settings bug.
        """
        return PlayScene(
            self.campaign,
            self.bestiary,
            self.atlas,
            seed=self.seed,
            on_exit=self.on_exit,
            start_stage=self.start_stage,
            hero_type_id=self.hero_type_id,
            settings=self.settings,
            difficulty=self.difficulty,
        )

    def _autosave(self) -> None:
        """Write the run, if it is standing somewhere a snapshot describes.

        Every panel is answered and the world has not been stepped since it was
        built -- the one moment a snapshot describes the run completely. See the
        note on `_needs_save`.

        Called from the pause branch as well as the live one, so the promise the
        Quit row makes is true on the first frame of a stage as well as the
        thousandth. Not hoisted above the panel guard instead: saving before the
        promotion, level and shop panels are answered records a run that had not
        promoted, which is the whole reason `_needs_save` is a flag.
        """
        if self._needs_save and not self.run.is_over:
            save.write(self.run)
            profile.record_stage(self.run)
            self._needs_save = False

    def _read_intent(self) -> Intent:
        """What the player is asking for, without spending any of it.

        Deliberately a pure read. The one-shot inputs are aged by
        `_consume_edges`, from inside the tick loop and only where a `step`
        runs; spending them here instead is what silently ate a dodge on every
        frame that paid out no tick and on every frame swallowed by hitstop.

        Called once a frame, so `move` and `aim` are sampled once a frame. The
        dodge read here is the frame's opening value -- `update` re-reads the
        buffer per tick, for the reason given at that call site.
        """
        keys = pygame.key.get_pressed()

        move = ZERO
        for key, direction in self.move_keys.items():
            if keys[key]:
                move = move + direction

        aim = self._aim_direction()

        # A pressed skill wins over the light attack rather than queueing behind
        # it. Holding the mouse down is the normal state of playing this game,
        # so a skill that waited its turn would never come out.
        slot = self._skill_pressed
        attacking = (
            slot is not None
            or pygame.mouse.get_pressed()[0]
            or any(keys[code] for code in self.keys[Action.ATTACK])
        )

        return Intent(
            move=move.clamped(1.0),
            aim=aim,
            attack=attacking,
            dodge=self._dodge_buffer > 0,
            weapon=slot if slot is not None else skills.LIGHT,
        )

    def _consume_edges(self) -> None:
        """Age the one-shot inputs by one tick. Called only where a `step` runs.

        A rendered frame and a simulation tick are not the same thing, and this
        is the seam where forgetting that costs a keypress. `FPS` and
        `TICKS_PER_SEC` are both 60 and `clock.tick` deals in whole
        milliseconds, so the accumulator regularly banks a frame's worth of time
        without paying out a tick; and a connect sets `freeze` for up to eleven
        ticks, none of which step the world. Clearing on *read* threw the press
        away in both windows.

        The two are spent differently, and deliberately.

        **A skill lasts one tick.** Which cooldown to spend and when is most of
        what makes a skill a skill, so a press that arrives while the hero is
        committed is a press that missed its moment.

        **A dodge lasts `DODGE_BUFFER_TICKS`**, because the roll is the one
        thing pressed *reactively* -- and the moment it is most pressed in is
        the freeze after being hit, which is precisely when `can_dodge` refuses
        for the stagger. Delivering it once, on the first stepped tick, is
        delivering it into a refusal.
        """
        if self._dodge_buffer > 0:
            self._dodge_buffer -= 1
        self._skill_pressed = None

    def _drop_edges(self) -> None:
        """Forget what was pressed, without any of it reaching a tick.

        The counterpart to `_consume_edges` and used in exactly one place: a
        panel taking the screen. Separate from it rather than a flag on it,
        because "the tick took this" and "nobody will ever take this" are
        different events that happen to clear the same fields today.
        """
        self._dodge_buffer = 0
        self._skill_pressed = None

    def _aim_direction(self) -> Vec2:
        """From the hero toward the cursor, in world terms.

        The mouse arrives in window coordinates, so it has to come back through
        the same integer scale and letterbox the picture went out through --
        skip that and the aim is off by the size of the black bars.
        """
        hero = self.world.hero
        if hero is None:
            return ZERO

        window = pygame.display.get_surface()
        if window is None:
            return ZERO

        mx, my = pygame.mouse.get_pos()
        win_w, win_h = window.get_size()
        internal = config.window_to_internal(mx, my, win_w, win_h)

        hero_screen = self.camera.to_screen(hero.pos)
        aim = Vec2(internal[0] - hero_screen[0], internal[1] - hero_screen[1])
        # A cursor sitting exactly on the hero has no direction in it; keeping
        # the old facing is better than snapping to an arbitrary one.
        return aim.normalized() if aim.length() > 2.0 else ZERO

    def _open_panels_for_props(self) -> bool:
        """Answer whatever the hero just walked onto in a reward room.

        Returns whether a panel opened, and the caller breaks out of the tick
        loop when it did. That is not tidiness: a frame pays out up to fifteen
        ticks, so without the break the room would go on being stepped behind
        the panel -- which is the one thing the whole panel mechanism exists to
        prevent, and it is only invisible here because there is nothing in a
        reward room to take advantage of it.

        Two of the four fixtures need a panel and two do not. A fountain heals
        and a chest pays, both of which `Run._take_rewards` has already done by
        the time this runs -- there is nothing left to ask the player. A stall
        and a shrine are decisions, and a decision needs the arena stopped.

        This is the *only* thing that opens the shop now. It used to open on
        every transition; it opens when you walk up to a stall.
        """
        if not self.run.used:
            return False

        if PropKind.STALL in self.run.used:
            # Rolled here, on the tick the stall is touched, and held. Both
            # rolls are derived from `(seed, index)` and draw on their own
            # stateless streams, so neither can reach `world.rng` and neither
            # needs a line in the save file.
            self.stall_offers = equipment.offers(self.run)
            self.shopping = True

        if PropKind.SHRINE in self.run.used and self.run.unspent_points > 0:
            # Opened here as well as on the next transition, deliberately. The
            # points carry either way, so nothing is lost by declining -- but a
            # shrine that handed out a point and said nothing would look broken,
            # and the panel is the only thing in the game that says what a point
            # is worth.
            self.shrine_offers = progression.offers(
                self.run.seed, self.run.index, rooms.table().shrine_offers
            )
            self.levelling = True

        return self.shopping or self.levelling

    # --- update --------------------------------------------------------------
    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        if self.paused:
            self._drop_edges()
            # Written here too, and this is not belt-and-braces. A stage
            # transition *arms* `_needs_save` and breaks out of the tick loop;
            # the write lands on the next update. Escape inside that window --
            # the banner is up for 110 frames, so it is an easy window to hit --
            # used to leave to the menu with the previous stage still on disk.
            # That was already wrong; it becomes intolerable the moment a row on
            # screen says which stage quitting keeps. The precondition the note
            # on `_needs_save` states holds here by construction: every panel is
            # answered whenever this flag can be set.
            self._autosave()
            return None

        if self.promoting or self.levelling or self.shopping or self.inspecting:
            # Not stepped, and the accumulator is not fed either -- banking real
            # seconds while a panel is open would fast-forward the first moments
            # of the next stage the instant it closed.
            #
            # Dropped rather than aged, and this is the one place a press is
            # deliberately thrown away. A buffered dodge would otherwise sit
            # through the whole shop visit and come out on the first tick of the
            # next arena -- a roll nobody asked for, into a room the player has
            # not seen yet.
            self._drop_edges()

            # The one thing this scene still counts with a panel up. Frames,
            # because no tick is being paid out to count instead.
            if self._shop_settle > 0:
                self._shop_settle -= 1
            return None

        self._autosave()

        intent = self._read_intent()

        for _ in range(self.accumulator.ticks_for(elapsed_seconds)):
            if self.freeze > 0:
                # Frozen on a connect. The renderer keeps drawing; the world
                # simply does not advance -- so the edge flags are left alone,
                # and a dodge pressed during the freeze fires on the tick it
                # drains rather than being swallowed by it.
                self.freeze -= 1
                continue

            # Movement and aim are sampled once a frame, deliberately -- they
            # are continuous, and re-reading the mouse mid-frame would give one
            # frame several aims. The buffer is not continuous, so it is read
            # here, per tick, and `DODGE_BUFFER_TICKS` therefore means what it
            # says rather than "that, plus however many ticks this frame owed".
            #
            # An intent built once before the loop keeps `dodge=True` for every
            # tick of the frame, and a stall pays out up to fifteen of them
            # (`MAX_FRAME_TIME`). That does *not* roll twice today, and it is
            # worth being precise about why: `dodge_cooldown` is 18 ticks on the
            # shortest class in the game, so the second roll is refused by the
            # cooldown rather than by anything here. Reading per tick means the
            # buffer does not quietly depend on that being true.
            step(self.world, replace(intent, dodge=self._dodge_buffer > 0))

            # Aged after the tick that saw it, never before -- so the press is
            # live for exactly `DODGE_BUFFER_TICKS` stepped ticks.
            self._consume_edges()
            self.effects.feed(self.world.drain_events(), self.world.hitstop)
            if self.world.hitstop > 0:
                self.freeze = self.world.hitstop

            self.run.settle()
            if self._open_panels_for_props():
                # Out of the loop, not merely flagged -- see the note there.
                break

            if self.run.just_advanced:
                # A new stage means a new arena and new bounds; the damage
                # numbers from the last one would hang over empty floor.
                self.effects.clear()
                self._enter_stage()
                self.banner = BANNER_FRAMES

                # The shop used to open here, on all thirty-nine transitions,
                # whether or not there was anything to decide. It is now a
                # place: one of the four things a reward room can hold, reached
                # by choosing the door with a stall over it two rooms earlier.
                # `_open_panels_for_props` below is what opens it, and the only
                # thing that does.

                # Once per run, on the way into the half of the campaign
                # that is fought as an advanced class. The stage it happens on
                # is `jobs.PROMOTION_STAGE`, named there because the bot has to
                # promote on the same transition or it is measuring a game
                # nobody plays. `jobs.can_promote` is what makes deleting the
                # advanced classes from the JSON turn the whole feature off.
                if self.run.at_promotion_point and jobs.can_promote(self.run):
                    self.promoting = True

                # And whenever the stage just cleared paid for a level. Checked
                # after the promotion so the two open in the order they are
                # resolved in, and gated on the count rather than on "did we
                # level this stage" so points banked on an earlier transition
                # are offered again rather than stranded.
                #
                # **This is not a shrine**, so the offer is cleared and the panel
                # falls back to all eight attributes. A point banked at a shrine
                # and spent here would otherwise be spent against that shrine's
                # three, in a room the player is no longer standing in -- and the
                # only symptom would be a plinth that looked oddly familiar.
                self.shrine_offers = ()
                self.levelling = self.run.unspent_points > 0

                # Armed, not written. The three panels above are open on this
                # tick and each of them can still change the run.
                self._needs_save = True
                break

            if self.run.is_over and not self._ended:
                # However it ended, it is not somewhere to come back to. Leaving
                # the file behind would put a dead run on the menu's Load Game
                # row and hand the player back the arena they just died in.
                self._ended = True
                self._needs_save = False
                save.delete()
                profile.record_end(self.run)
                break

        self.effects.tick()
        if self.banner > 0:
            self.banner -= 1

        hero = self.world.hero
        if hero is not None:
            self.camera.follow(hero.pos, self._aim_direction())

        return None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.LETTERBOX)

        viewport = surface.subsurface((0, 0, config.INTERNAL_W, config.VIEWPORT_H))
        self.renderer.draw(viewport, self.world, self.camera, self.effects)
        self.hud.draw(
            surface,
            self.world,
            self.run,
            self.world.tick,
            skill_labels=self.skill_labels,
        )

        if self.paused:
            # A leading branch rather than a fifth `if` inside the block below,
            # which leaves that block exactly as it was. The bug the note there
            # records was an `elif` *between* those four; this adds none.
            self.pause_panel.draw(surface, self.run, self.pause_index)
        elif self.shopping or self.promoting or self.levelling or self.inspecting:
            # A panel, or the banner -- never both. Both at once puts the stage
            # name through the panel's title, and the banner is still counting
            # down underneath, so it gets its remaining frames once the panel is
            # dismissed.
            #
            # Written as one branch on "is any panel up" rather than as a chain.
            # An `elif` here would attach to whichever `if` happened to be last,
            # which is exactly how the banner started drawing over the shop when
            # the promotion panel was added between them.
            if self.shopping:
                self.shop_panel.draw(surface, self.run, self.stall_offers)
            if self.levelling:
                # Over the shop and under the promotion, matching the order the
                # three are resolved in and the order they take keys in.
                self.level_panel.draw(surface, self.run, self.shrine_offers)
            if self.promoting:
                # Over the shop, not instead of it. Both are open on the final
                # transition, and the class is the choice being asked for.
                self.job_panel.draw(surface, self.run, self.atlas)
            if self.inspecting:
                # Last, and alone -- it is the one panel that is never up at the
                # same time as another. Written as a fourth `if` rather than an
                # `elif` on the chain above, which is the shape this branch has
                # been burned by once already; see the note at the top of it.
                self.hero_panel.draw(
                    surface,
                    self.run,
                    close_key=keymap.label(Action.SHEET, self.settings),
                )
        elif self.banner > 0:
            self._draw_banner(surface)

        if self.run.is_over:
            self._draw_result(surface)

    def _draw_banner(self, surface: pygame.Surface) -> None:
        """Announces the stage just entered, over a fight already in progress.

        Not a pause: the arena is live behind it, so walking into the next stage
        badly positioned is a real thing that can happen.
        """
        font = pygame.font.Font(None, 26)
        small = pygame.font.Font(None, 15)

        # A room is not stage anything. Numbering one would put two screens in
        # a row claiming to be stage eight, and the second of them would be the
        # one with no enemies in it.
        heading = (
            self.world.level.kind.value.upper()
            if self.run.room is not None
            else f"STAGE {self.run.stage_number} OF {self.run.stage_count}"
        )
        title = font.render(heading, False, config.ACCENT)
        name = small.render(self.world.level.name, False, config.WHITE)

        top = 26
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, top))
        surface.blit(name, ((config.INTERNAL_W - name.get_width()) // 2, top + 22))

        if self.run.healed > 0:
            healed = small.render(f"+{self.run.healed} recovered", False, config.GOOD)
            surface.blit(
                healed, ((config.INTERNAL_W - healed.get_width()) // 2, top + 38)
            )

    def _draw_result(self, surface: pygame.Surface) -> None:
        won = self.run.outcome is RunOutcome.WON
        font = pygame.font.Font(None, 34)
        small = pygame.font.Font(None, 16)

        banner = font.render(
            "RUN COMPLETE" if won else "YOU DIED", False,
            config.GOOD if won else config.BAD,
        )
        detail = small.render(
            f"cleared all {self.run.stage_count} stages" if won
            else f"stage {self.run.stage_number} of {self.run.stage_count}",
            False, config.GREY,
        )
        # What the run was worth. Nothing carries out of it -- there is no save
        # file and gold does not persist -- so this is a score, and it is the
        # only one the game keeps.
        purse = small.render(f"{self.run.gold_total}g collected", False, config.GOLD)
        # The restart key is rebindable, so this is asked rather than written
        # down. Esc is not, which is why it is still a literal.
        restart = keymap.label(Action.RESTART, self.settings)
        hint = small.render(
            f"{restart} for a new run    Esc for the menu", False, config.GREY
        )

        # A dim wash rather than a solid panel, so the arena stays visible behind
        # the result -- seeing what killed you is part of the message.
        wash = pygame.Surface((config.INTERNAL_W, config.VIEWPORT_H), pygame.SRCALPHA)
        wash.fill((10, 10, 14, 150))
        surface.blit(wash, (0, 0))

        centre = config.INTERNAL_W // 2
        surface.blit(banner, (centre - banner.get_width() // 2, config.VIEWPORT_H // 2 - 32))
        surface.blit(detail, (centre - detail.get_width() // 2, config.VIEWPORT_H // 2 + 2))
        surface.blit(purse, (centre - purse.get_width() // 2, config.VIEWPORT_H // 2 + 20))
        surface.blit(hint, (centre - hint.get_width() // 2, config.VIEWPORT_H // 2 + 40))
