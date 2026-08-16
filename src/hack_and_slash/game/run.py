"""A run: one hero through the stages of a campaign.

A `World` is one stage. This is the layer above it -- what carries between stages
and what happens when one is cleared. The campaign itself is never mutated, so a
run can always be restarted from the top without touching the disk.

Two things carry: health, which comes back partway between stages, and gold.
Health is what makes a stage cleared badly cost you something on the next one,
without a single rough stage quietly ending the run three stages before you find
out. Gold is what you did about it -- the shop between stages turns a good stage
into a better next one.

There is still no inventory and nothing to equip. What the shop sells are the
three integers below: health now, health per stage from now on, and a better
share of what drops. All of them live on the run rather than on the hero,
because `EntityType` is frozen content and a class is a class for the whole run.

Pure Python -- no pygame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..core.campaign import Campaign
from . import jobs
from .entities import DEFAULT_HERO, Bestiary, EntityType
from .world import Outcome, Purse, World


class RunOutcome(str, Enum):
    """How the *run* is going, which is not the same as how the stage is going.

    `World.outcome` says whether the current arena is cleared. Clearing one is
    only a win if there is nothing after it -- everywhere else it is a doorway.
    """

    RUNNING = "running"
    WON = "won"
    LOST = "lost"


@dataclass
class Run:
    campaign: Campaign
    bestiary: Bestiary
    world: World
    index: int = 0
    seed: int = 0
    outcome: RunOutcome = RunOutcome.RUNNING

    #: Which class is being played. Fixed for the whole run -- it is chosen
    #: before stage one and there is no way to change it afterwards, which is
    #: what makes it a run and not a loadout.
    hero_type_id: str = DEFAULT_HERO

    #: Where this run began. Normally zero; non-zero only when a tool jumped
    #: straight to a stage, and remembered so a restart returns there rather
    #: than silently dropping the tool back to stage one.
    start_index: int = 0

    #: Set for one moment when a stage is cleared and the next begins, so the
    #: presentation layer can show a banner. Drained like an event -- the run
    #: never reads it back.
    just_advanced: bool = False
    healed: int = 0

    #: Gold banked from stages already finished. What is loose in the stage
    #: currently being fought lives on the `World` and is added on arrival at
    #: the next one -- so this is always a number that has survived a stage, and
    #: `gold_total` is the one to show a player mid-fight.
    gold: int = 0

    #: Bought from the shop, and the reason it is spelled out here rather than
    #: on the hero: `EntityType` is frozen content and shared by every run.
    #: `bonus_heal` adds to the class's own `heal_between_stages`; `gold_find`
    #: is a fraction, so 0.5 means half as much again from every drop.
    bonus_heal: int = 0
    gold_find: float = 0.0

    #: How many of each good has been bought, for the ones that are capped.
    #: Counted rather than inferred from `bonus_heal` and `gold_find`: those are
    #: the *effects*, and reading a cap back out of an effect would break the
    #: moment anything else moved one of them.
    purchases: dict[str, int] = field(default_factory=dict)

    #: The advanced class promoted into, or empty. Kept *beside* `hero_type_id`
    #: rather than overwriting it, and that separation does real work: both
    #: `restart()` here and `PlayScene.restarted()` read `hero_type_id`, so a
    #: restart returns to the class the run was begun as without either of them
    #: knowing promotion exists. Overwriting would silently make R start a fresh
    #: run at stage one as a Dark Knight -- a class the character select cannot
    #: offer and the balance grid has never seen.
    job_id: str = ""

    # --- lifecycle -----------------------------------------------------------
    @classmethod
    def start(
        cls,
        campaign: Campaign,
        bestiary: Bestiary,
        seed: int = 0,
        at_stage: int = 0,
        hero_type_id: str = DEFAULT_HERO,
    ) -> "Run":
        """Begin a run.

        `at_stage` starts partway in, for tuning and screenshots. It is not a
        difficulty option: the hero arrives at full health, so a stage reached
        this way is a different fight from the same stage reached through a run.
        """
        index = max(0, min(at_stage, len(campaign) - 1))
        return cls(
            campaign=campaign,
            bestiary=bestiary,
            world=World(
                campaign[index],
                bestiary,
                seed=cls._stage_seed(seed, index),
                hero_type_id=hero_type_id,
                # A run started partway in is on the floor it says it is, so a
                # tool jumping to stage 18 sees stage 18's payouts.
                purse=Purse(floor=index + 1),
            ),
            index=index,
            seed=seed,
            start_index=index,
            hero_type_id=hero_type_id,
        )

    def restart(self) -> "Run":
        """A fresh hero, back where this run began. Nothing carries over.

        The class does carry over -- restarting is a second attempt at the same
        run, not a return to the character select.
        """
        return Run.start(
            self.campaign,
            self.bestiary,
            seed=self.seed,
            at_stage=self.start_index,
            hero_type_id=self.hero_type_id,
        )

    @property
    def hero_type(self) -> EntityType:
        """The class being played *now*, whether or not its body is still alive.

        Read from the bestiary rather than off `world.hero`, which is None once
        the hero has been culled -- the run still needs to know what it was.

        Promotion wins where it has happened, which matters for the one caller
        that reads a number off this: `_advance` uses `heal_between_stages` and
        the maximum health to work out what carries into the next stage. At the
        trigger as it ships there is never a next stage after a promotion, so
        today this changes nothing -- it is written this way so that moving the
        trigger earlier is the one-line change it looks like, rather than a
        silent bug where a promoted hero heals as the class it used to be.
        """
        return self.bestiary[self.job_id or self.hero_type_id]

    @staticmethod
    def _stage_seed(seed: int, index: int) -> int:
        """Each stage rolls differently, but the whole run replays from one seed.

        Without the offset every stage would draw the same damage rolls in the
        same order, which is both duller and a poor test -- a bug that only shows
        up on a particular sequence of rolls would never appear twice.
        """
        return seed + index * 1013

    # --- where we are --------------------------------------------------------
    @property
    def stage_number(self) -> int:
        """1-based, for anything a player reads."""
        return self.campaign.stage_number(self.index)

    @property
    def stage_count(self) -> int:
        return self.campaign.length

    @property
    def on_final_stage(self) -> bool:
        return self.campaign.is_final(self.index)

    @property
    def at_promotion_point(self) -> bool:
        """Standing on the first stage that is fought as an advanced class.

        True for the whole of that stage rather than only on the tick it began,
        which is what the caller wants: the scene pairs it with `just_advanced`
        to open the panel once, and `jobs.can_promote` closes the offer for good
        once a choice is taken.

        Says nothing about whether there is a choice to make -- a campaign
        shorter than the trigger never reaches it, and a class with no
        promotions declared has nothing to offer wherever it stands.
        """
        return self.stage_number == jobs.PROMOTION_STAGE

    @property
    def level(self):
        return self.campaign[self.index]

    @property
    def is_over(self) -> bool:
        return self.outcome is not RunOutcome.RUNNING

    @property
    def gold_total(self) -> int:
        """Banked, plus whatever has been picked up in the stage in progress.

        The number to show a player. `gold` on its own is a bookkeeping figure
        that lags a stage behind, and a purse that visibly ignores the coin you
        just walked over is worse than no purse at all.
        """
        return self.gold + self.world.gold

    # --- advancing -----------------------------------------------------------
    def settle(self) -> None:
        """Act on a stage that finished during the tick just taken.

        Called after every `sim.step`. Cheap and idempotent while a stage is
        still running, which is what lets the play scene call it unconditionally.
        """
        self.just_advanced = False
        self.healed = 0

        if self.is_over:
            return

        if self.world.outcome is Outcome.LOST:
            self.outcome = RunOutcome.LOST
            self._bank()
            return

        if self.world.outcome is not Outcome.WON:
            return

        if self.on_final_stage:
            self.outcome = RunOutcome.WON
            self._bank()
            return

        self._advance()

    def _bank(self) -> None:
        """Move the stage's takings into the run's purse.

        Zeroing the world's side is what makes this safe to call more than once.
        `settle` is called every tick and is meant to be idempotent; a bank that
        did not clear its source would keep paying out for as long as the death
        screen was up.
        """
        self.gold += self.world.gold
        self.world.gold = 0

    def _advance(self) -> None:
        hero = self.world.hero
        # A cleared stage always leaves the hero alive -- the run would be lost
        # otherwise -- but the property is Optional, so this stays defensive.
        surviving = hero.hp if hero is not None else 1
        hero_type = self.hero_type
        heal = hero_type.heal_between_stages + self.bonus_heal

        before = surviving
        carried = min(surviving + heal, hero_type.hp)

        # Before the world is replaced, or the stage's takings go with it.
        self._bank()

        self.index += 1
        self.world = World(
            self.campaign[self.index],
            self.bestiary,
            seed=self._stage_seed(self.seed, self.index),
            carry_hp=carried,
            # `hero_type`, not `hero_type_id` -- the next stage is fought as
            # whatever the run is now, which is the advanced class once one has
            # been chosen. Passing the base id here builds the next body out of
            # the class the run *started* as, silently undoing the promotion on
            # the transition after it; it read correctly only for as long as
            # there was never a stage after the fork.
            hero_type_id=self.hero_type.id,
            purse=Purse(floor=self.index + 1, gold_find=self.gold_find),
        )
        self.just_advanced = True
        self.healed = carried - before
