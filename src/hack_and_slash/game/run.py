"""A run: one hero through the stages of a campaign.

A `World` is one stage. This is the layer above it -- what carries between stages
and what happens when one is cleared. The campaign itself is never mutated, so a
run can always be restarted from the top without touching the disk.

Health is the only thing that carries, and it comes back partway between stages.
That is the whole progression system: no upgrades, no inventory. What it buys is
that a stage cleared badly still costs you something on the next one, without a
single rough stage quietly ending the run three stages before you find out.

Pure Python -- no pygame.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.campaign import Campaign
from .entities import DEFAULT_HERO, Bestiary, EntityType
from .world import Outcome, World


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
        """The class being played, whether or not its body is still alive.

        Read from the bestiary rather than off `world.hero`, which is None once
        the hero has been culled -- the run still needs to know what it was.
        """
        return self.bestiary[self.hero_type_id]

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
    def level(self):
        return self.campaign[self.index]

    @property
    def is_over(self) -> bool:
        return self.outcome is not RunOutcome.RUNNING

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
            return

        if self.world.outcome is not Outcome.WON:
            return

        if self.on_final_stage:
            self.outcome = RunOutcome.WON
            return

        self._advance()

    def _advance(self) -> None:
        hero = self.world.hero
        # A cleared stage always leaves the hero alive -- the run would be lost
        # otherwise -- but the property is Optional, so this stays defensive.
        surviving = hero.hp if hero is not None else 1
        hero_type = self.hero_type
        heal = hero_type.heal_between_stages

        before = surviving
        carried = min(surviving + heal, hero_type.hp)

        self.index += 1
        self.world = World(
            self.campaign[self.index],
            self.bestiary,
            seed=self._stage_seed(self.seed, self.index),
            carry_hp=carried,
            hero_type_id=self.hero_type_id,
        )
        self.just_advanced = True
        self.healed = carried - before
