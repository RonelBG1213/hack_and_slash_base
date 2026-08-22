"""Choosing a class, which is the first decision the game asks for.

There is no inventory and nothing to equip: the shop between stages sells three
goods and none of them changes what a class *is*. So this screen is still the
whole of character building, and it has one job -- make the five readable enough
that the choice is informed rather than a coin toss. Hence the stat row and the
one-line role. A grid of five names would be a menu; this is supposed to be a
decision, and it is the only one that cannot be revisited for the rest of a run.

The roster comes from `bestiary.hero_classes`, which is every entity whose
faction is `hero`, in the order `data/entities.json` lists them. Adding a class
is an entry in that file and a painter in `tools/gen_art.py`; nothing here needs
touching, and there is no second list that can fall out of step with the data.

**The difficulty row is here rather than on the Settings screen, and that is a
deliberate placement rather than a convenient one.** `scenes/options.py` is
drawn on the line that nothing on it may change how a fight resolves -- a
difficulty row there would be a balance decision worn as a preference. Here it
is what it actually is: a decision taken once, beside the other decision taken
once, on the screen whose whole job is to be a decision rather than a
reference. The tiers themselves live in `data/difficulty.json` where they can
be swept, which is the other half of the same argument.

Up and down move it, left and right move the roster. Two axes rather than a
focus cursor: with exactly two things to choose there is nothing a cursor would
disambiguate, and it would put a mode between the player and a screen that has
never had one.
"""

from __future__ import annotations

from typing import Optional

import pygame

from .. import config
from ..core.campaign import Campaign
from ..game import difficulty as difficulty_module
from ..game import elites as elites_module
from ..game import profile as profile_module
from ..game import unlocks
from ..game.entities import Bestiary, EntityType
from ..render.atlas import Atlas
from ..settings import Settings
from .base import Scene
from .play import PlayScene

#: One line per class, spoken as a question the class answers. Keyed by type id
#: and looked up with a fallback, so a class added to the JSON without one shows
#: up playable rather than crashing the screen it is meant to appear on.
ROLES = {
    "knight": "slow, heavy, hard to kill",
    "rogue": "fragile and very fast",
    "archer": "fights at range",
    "magician": "one big hit, long commitment",
    "priest": "recovers twice as much between stages",
}

#: How far apart the five portraits sit, and how big they are drawn. The atlas
#: is a 16px grid, so the scale is a whole number -- a fractional one would
#: smear exactly the pixels this screen exists to show off.
PORTRAIT_SCALE = 3
COLUMN_WIDTH = 62

#: Baseline of the difficulty row, under the class's stat line and above the
#: prompt. Named because both the drawing and the hit-test read it, and two
#: copies of a coordinate is how a clickable row drifts off the thing it claims
#: to click. `_tier_spans` exists for the x axis for the same reason.
DIFFICULTY_Y = 174

#: What sits between two tier names. Measured rather than assumed by both the
#: drawing and the hit-test, so the gap is never counted twice or not at all.
DIFFICULTY_GAP = "   "


class CharacterSelectScene(Scene):
    def __init__(
        self,
        campaign: Campaign,
        bestiary: Bestiary,
        atlas: Atlas,
        seed: int = 0,
        on_exit=None,
        start_stage: int = 0,
        index: int = 0,
        settings: Optional[Settings] = None,
    ) -> None:
        self.campaign = campaign
        self.bestiary = bestiary
        self.atlas = atlas
        self.seed = seed
        self.on_exit = on_exit
        self.start_stage = start_stage

        #: Carried through, and read for exactly one thing. This screen is on
        #: the road between the menu that owns the settings and the run that
        #: reads them, and dropping them here would mean a player's toggles
        #: applied to a loaded run and not to a new one.
        #:
        #: The one thing is `reduce_flashing`: the prompt below blinks, which
        #: makes this the only screen outside the arena that does. It has no
        #: opinion about screenshake or about the palette -- nothing it draws
        #: means something by hue.
        self.settings = settings or Settings()

        self.classes: tuple[EntityType, ...] = bestiary.hero_classes
        self.index = max(0, min(index, len(self.classes) - 1))

        #: The tiers, and where the cursor starts. `index_of_default` rather
        #: than zero: the default tier is the one every recorded number in the
        #: project was measured against, and a screen that opened on anything
        #: else would quietly make the unmeasured tier the normal way to play.
        self.difficulties = difficulty_module.table()
        self.difficulty_index = self.difficulties.index_of_default

        #: What this machine has earned the right to pick. Read once, at open:
        #: nothing on this screen can earn an unlock, and a file read per frame
        #: for a number that cannot move is a file read per frame.
        #:
        #: `unlocks.is_open` answers True for anything no entry names, so an
        #: empty `data/unlocks.json` leaves every tier reachable and this whole
        #: gate inert -- which is what makes the empty table the rollback.
        self.profile = profile_module.load()
        self.locked = tuple(
            not unlocks.is_open(unlocks.Grant.DIFFICULTY, tier.id, self.profile)
            for tier in self.difficulties.tiers
        )

        self.title = pygame.font.Font(None, 30)
        self.body = pygame.font.Font(None, 17)
        self.small = pygame.font.Font(None, 14)
        self.tick = 0

    # --- input ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> Optional[Scene]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return self.on_exit() if self.on_exit else None
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self._move(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._move(1)
            elif event.key in (pygame.K_UP, pygame.K_w):
                self._move_difficulty(-1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._move_difficulty(1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self._begin()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            tier = self._tier_at(event.pos)
            if tier is not None:
                # The tier that was clicked, not the next one along. An earlier
                # draft advanced by one per click on a band spanning the whole
                # row, which -- because `_move_difficulty` clamps rather than
                # wrapping -- walked to the hardest tier and stuck there with no
                # way back. A mouse could reach exactly one of the three.
                if not self.locked[tier]:
                    # A locked tier refuses the click rather than selecting and
                    # then failing to start: the row is greyed and says what it
                    # wants, so a click on it has already been answered.
                    self.difficulty_index = tier
                return None

            hit = self._column_at(event.pos)
            if hit is None:
                return None
            # Click to select, click again to commit. A single click starting
            # the run means a misclick costs a whole run rather than a keypress.
            if hit == self.index:
                return self._begin()
            self.index = hit
        return None

    def _move(self, step: int) -> None:
        # Wraps, because five items in a row have two ends and stopping dead at
        # them is worse than the one moment of surprise wrapping costs.
        self.index = (self.index + step) % len(self.classes)

    def _move_difficulty(self, step: int) -> None:
        # Clamped, where the roster wraps. Difficulty is an ordered scale and
        # wrapping one puts Relentless one keypress below Forgiving, which is
        # the single worst misread available on this screen.
        #
        # A locked tier is stepped *over* rather than stopped at, and the walk
        # gives up rather than clamping onto one: landing the cursor on a row
        # that cannot start a run would strand the screen, which is the same
        # fault the clamp above was written to avoid in the other direction.
        count = len(self.difficulties.tiers)
        index = self.difficulty_index
        while True:
            index += step
            if not 0 <= index < count:
                return
            if not self.locked[index]:
                self.difficulty_index = index
                return

    def _tier_spans(self) -> list[tuple[int, int]]:
        """Where each tier name sits on the row, as `(x, width)`.

        The single source of that layout: `_draw_difficulty` blits from it and
        `_tier_at` hit-tests against it, so a name can never be drawn somewhere
        the click does not reach. Summing the parts rather than measuring the
        joined string, because the two do not always agree to the pixel and the
        difference is exactly the drift this method exists to remove.
        """
        names = [tier.name for tier in self.difficulties.tiers]
        widths = [self.small.size(name)[0] for name in names]
        gap = self.small.size(DIFFICULTY_GAP)[0]

        total = sum(widths) + gap * (len(names) - 1)
        x = (config.INTERNAL_W - total) // 2

        spans = []
        for width in widths:
            spans.append((x, width))
            x += width + gap
        return spans

    def _tier_at(self, window_pos: tuple[int, int]) -> Optional[int]:
        """Which tier a window-space click landed on, if any.

        Padded by the same three pixels the selection box is drawn with, so the
        border of the thing that looks clickable is clickable.
        """
        window = pygame.display.get_surface()
        if window is None:
            return None

        win_w, win_h = window.get_size()
        x, y = config.window_to_internal(*window_pos, win_w, win_h)
        if not DIFFICULTY_Y - 3 <= y <= DIFFICULTY_Y + 10:
            return None

        for i, (left, width) in enumerate(self._tier_spans()):
            if left - 3 <= x <= left + width + 3:
                return i
        return None

    def _column_at(self, window_pos: tuple[int, int]) -> Optional[int]:
        """Which portrait a window-space click landed on, if any.

        The mouse arrives in window coordinates and everything here is laid out
        in the 384x216 internal space, so it has to come back through the same
        integer scale and letterbox the picture went out through.
        """
        window = pygame.display.get_surface()
        if window is None:
            return None

        win_w, win_h = window.get_size()
        x, y = config.window_to_internal(*window_pos, win_w, win_h)
        if not 60 <= y <= 130:
            return None

        left = self._first_column_x()
        column = (x - left + COLUMN_WIDTH // 2) // COLUMN_WIDTH
        if 0 <= column < len(self.classes):
            return int(column)
        return None

    def _first_column_x(self) -> int:
        span = COLUMN_WIDTH * (len(self.classes) - 1)
        return (config.INTERNAL_W - span) // 2

    def _begin(self) -> Optional[PlayScene]:
        """Start the run, unless the cursor is standing on a locked tier.

        The mouse path refuses a locked row before it ever moves the cursor, and
        this is the same refusal on the key path. It is unreachable with the
        shipped table -- `index_of_default` opens on a tier nothing gates and
        `_move_difficulty` steps over the locked ones -- but both of those are
        properties of `data/unlocks.json`, and a run begun on a tier the player
        has not earned is not something a data file should be able to arrange.
        """
        if self.locked[self.difficulty_index]:
            return None

        return PlayScene(
            self.campaign,
            self.bestiary,
            self.atlas,
            seed=self.seed,
            start_stage=self.start_stage,
            hero_type_id=self.chosen.id,
            settings=self.settings,
            on_exit=self.on_exit,
            difficulty=self.difficulty,
            elites=self.elites,
        )

    @property
    def elites(self) -> elites_module.Table:
        """The champion layer this run will meet, or the layer switched off.

        **Two conditions, and the second is the safety net.** The player has to
        have turned it on, and the profile has to have earned the right to --
        because `Settings` is a file a player can edit and a profile is a file a
        player can erase, and a preference outliving the unlock that justified
        it would be the one route by which a run met champions without anybody
        deciding it should.

        Read here rather than held, so the answer is taken at the moment a run
        is built. `Run` then copies it and nothing re-reads it for the length of
        the campaign.
        """
        if not self.settings.champions:
            return elites_module.OFF
        if not unlocks.is_open(unlocks.Grant.MODIFIER, "champions", self.profile):
            return elites_module.OFF
        return elites_module.table()

    @property
    def chosen(self) -> EntityType:
        return self.classes[self.index]

    @property
    def difficulty(self) -> difficulty_module.Difficulty:
        return self.difficulties.tiers[self.difficulty_index]

    def update(self, elapsed_seconds: float) -> Optional[Scene]:
        self.tick += 1
        return None

    # --- draw ----------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(config.DARK)

        title = self.title.render("CHOOSE YOUR HERO", False, config.ACCENT)
        surface.blit(title, ((config.INTERNAL_W - title.get_width()) // 2, 22))

        self._draw_roster(surface)
        self._draw_details(surface)
        self._draw_difficulty(surface)

        # Blinks at 1Hz to say "this screen is waiting for you", and holds
        # steady when the player has asked for less flashing. Well under the
        # health bar's rate and well under the threshold anyone tunes for -- but
        # a row that says "reduce flashing" and leaves the game's other blink
        # running is a row that does not mean what it says.
        if self.settings.reduce_flashing or (self.tick // 30) % 2 == 0:
            prompt = self.small.render(
                "left / right  hero     up / down  difficulty     enter  begin",
                False,
                config.GOOD,
            )
            surface.blit(
                prompt,
                ((config.INTERNAL_W - prompt.get_width()) // 2, config.INTERNAL_H - 22),
            )

    def _draw_roster(self, surface: pygame.Surface) -> None:
        left = self._first_column_x()
        cell = config.TILE * PORTRAIT_SCALE

        for i, entity_type in enumerate(self.classes):
            centre_x = left + i * COLUMN_WIDTH
            selected = i == self.index

            sprite = self.atlas[entity_type.sprite]
            portrait = pygame.transform.scale(sprite, (cell, cell))
            box = pygame.Rect(0, 0, cell + 6, cell + 6)
            box.center = (centre_x, 84)

            # The unselected four are dimmed rather than shrunk. Changing size on
            # selection makes the whole row twitch as the cursor moves; changing
            # brightness leaves the layout still and reads just as clearly.
            pygame.draw.rect(surface, config.PANEL, box)
            if selected:
                pygame.draw.rect(surface, config.ACCENT, box, 1)
            else:
                portrait.set_alpha(90)

            surface.blit(portrait, portrait.get_rect(center=box.center))

            label = self.small.render(
                entity_type.name, False, config.WHITE if selected else config.GREY
            )
            surface.blit(label, (centre_x - label.get_width() // 2, 112))

    def _draw_details(self, surface: pygame.Surface) -> None:
        chosen = self.chosen
        centre = config.INTERNAL_W // 2

        role = self.body.render(
            ROLES.get(chosen.id, chosen.name), False, config.WHITE
        )
        surface.blit(role, (centre - role.get_width() // 2, 136))

        # Four numbers rather than a bar chart. Bars invite comparing lengths,
        # and these are not on comparable scales -- the weapon's name says more
        # about how a class plays than any of them.
        stats = "   ".join(
            (
                f"hp {chosen.full_hp}",
                f"speed {chosen.speed:g}",
                f"heal {chosen.heal_between_stages}",
                chosen.weapon.name.lower(),
            )
        )
        line = self.small.render(stats, False, config.GREY)
        surface.blit(line, (centre - line.get_width() // 2, 156))

    def _draw_difficulty(self, surface: pygame.Surface) -> None:
        """The tier, with the ones either side of it shown greyed.

        Drawn as a scale rather than as the selected name alone, because what
        this row is asking is *how hard*, and a single word answers that only
        for somebody who already knows what the other words are. The arrows are
        omitted at the ends, which is the whole of how the row says it is
        clamped rather than wrapping.
        """
        chosen = self.difficulty
        centre = config.INTERNAL_W // 2

        for i, (left, width) in enumerate(self._tier_spans()):
            tier = self.difficulties.tiers[i]
            selected = i == self.difficulty_index
            # Three states rather than two, the same way `menu._draw_rows`
            # greys a row it cannot open: a locked tier is dimmer than an
            # unselected one, because "not chosen" and "not available" are
            # different things and the row already uses brightness for the
            # first of them.
            if selected:
                colour = config.WHITE
            elif self.locked[i]:
                colour = config.PANEL
            else:
                colour = config.GREY
            label = self.small.render(tier.name, False, colour)
            if selected:
                # A box rather than a brighter colour alone: this row sits
                # between two other centred lines of small grey text, and
                # brightness on its own does not read as "this one is armed".
                box = pygame.Rect(left - 3, DIFFICULTY_Y - 3, width + 6, 13)
                pygame.draw.rect(surface, config.PANEL, box)
                pygame.draw.rect(surface, config.ACCENT, box, 1)
            surface.blit(label, (left, DIFFICULTY_Y))

        # The line under the row says one of two things, and the tier's own
        # blurb is the one that wins. A lock is explained only when the player
        # is standing right in front of it -- see `_locked_hint` -- because the
        # `(untuned)` flag below is a recorded decision about saying an
        # unmeasured number on the screen rather than only in the data file, and
        # a hint that covered it would quietly undo that.
        wanted = self._locked_hint()
        if wanted:
            line = self.small.render(wanted, False, config.GREY)
            surface.blit(line, (centre - line.get_width() // 2, DIFFICULTY_Y + 14))
            return

        blurb = chosen.blurb
        if not chosen.measured:
            # Said on the screen, not only in the data file. Every other
            # unmeasured number in this project is flagged where it lives, and
            # for a tier the place it lives, as far as a player is concerned,
            # is here.
            blurb = f"{blurb}  (untuned)" if blurb else "untuned"
        if blurb:
            line = self.small.render(blurb, False, config.GREY)
            surface.blit(line, (centre - line.get_width() // 2, DIFFICULTY_Y + 14))

    def _locked_hint(self) -> str:
        """What the tier *one step harder* is waiting for, or empty.

        Only that one, and only from the row beside it. Two reasons, and the
        second is the one that decided it:

        * It is the moment the answer is needed. The tiers are an ordered scale
          and the locks are earned in that order, so the tier after the cursor
          is the next one a player can have -- and pressing down onto it is
          exactly when they will ask why nothing happened.
        * It leaves the `(untuned)` flag alone everywhere else. That flag is a
          recorded decision about saying an unmeasured number on the screen and
          not only in `data/difficulty.json`, and a hint that sat on top of it
          would undo that quietly, on the tier a fresh player is standing on.
        """
        nxt = self.difficulty_index + 1
        if nxt >= len(self.difficulties.tiers) or not self.locked[nxt]:
            return ""

        tier = self.difficulties.tiers[nxt]
        gate = unlocks.table().gating(unlocks.Grant.DIFFICULTY, tier.id)
        if gate is None:
            return ""
        return f"{tier.name}: {gate.requires.describe()}"
