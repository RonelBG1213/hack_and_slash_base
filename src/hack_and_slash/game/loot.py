"""What a kill leaves behind.

Two rules hold this module together, and both exist to keep the loot layer from
reaching into a fight:

* **Loot never draws from `world.rng`.** That generator feeds `roll_damage`, and
  a single extra draw from it shifts every damage roll for the rest of the run --
  which would move all hundred cells of the recorded class-by-stage grid without
  one balance number changing. Loot has its own stream, seeded from the same
  world seed, so a seeded run still replays exactly and the two are provably
  independent. `test_loot.py` asserts that directly.
* **A pickup is not an entity.** It has no health, no faction and no brain,
  nothing collides with it, and it lives in its own list. Put one in
  `world.entities` and the broadphase, the separation pass and every AI brain in
  the game would start taking an interest in a coin.

Every number is in `data/loot.json`. Nothing here holds a value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .. import config
from ..core.vec2 import Vec2


class Rarity(str, Enum):
    """How good a drop is, which in this game means only how much it is worth.

    Ordered worst to best, and that order is content: the shop panel and the
    floating numbers both read it, and `data/loot.json` is expected to list the
    tiers in it.
    """

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


@dataclass(frozen=True)
class Tier:
    """One rarity and the two numbers that define it."""

    rarity: Rarity
    weight: int  # relative, not a percentage; the table sums them
    worth: float  # multiplier on the gold the kill already produced


@dataclass
class Pickup:
    """Something on the floor waiting to be walked over.

    `rarity` of None means loose coin -- the gold every kill drops. Anything
    else is a valuable, and the rarity is the whole of what it is: there is no
    item list, no names, and nothing to equip. What a rarity buys you is a
    bigger number, which is why one can be rolled without any content existing
    for it to name.
    """

    pos: Vec2
    gold: int
    rarity: Rarity | None = None

    @property
    def is_item(self) -> bool:
        return self.rarity is not None

    @property
    def sprite(self) -> str:
        """Named here for the same reason `EntityType.sprite` is: what a thing
        looks like is a property of the thing, and the renderer should not be
        the place that decides a valuable is not a coin."""
        return "relic" if self.is_item else "coin"


#: How close the hero has to be to hoover something up, in pixels, on top of
#: their own body radius. Generous on purpose: a pickup you have to stand
#: exactly on is a pickup you circle twice, and nothing in this game is worth
#: interrupting a fight to line up on.
PICKUP_RADIUS = 7.0


@dataclass(frozen=True)
class LootTable:
    """The contents of `data/loot.json`, read once.

    Frozen, because it is content in the same sense the bestiary is: tuning the
    loot layer means editing the JSON, never this file.
    """

    gold_base: float
    floor_step: float
    variance: float
    item_chance: float
    scatter: float
    tiers: tuple[Tier, ...]
    shop: dict[str, dict]

    # --- loading -------------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "LootTable":
        payload = json.loads((path or config.LOOT_DATA).read_text(encoding="utf-8"))
        gold = payload["gold"]

        tiers = tuple(
            Tier(
                rarity=Rarity(entry["id"]),
                weight=int(entry["weight"]),
                worth=float(entry["worth"]),
            )
            for entry in payload["rarities"]
        )
        if not tiers:
            raise ValueError(f"{path or config.LOOT_DATA} lists no rarities")
        if sum(tier.weight for tier in tiers) <= 0:
            # Every weight zero is not "nothing drops", it is a division by zero
            # in the middle of a fight. Refuse it here, where the file is named.
            raise ValueError(
                f"{path or config.LOOT_DATA}: the rarity weights sum to zero, so "
                "no tier can ever be rolled"
            )

        return cls(
            gold_base=float(gold["base"]),
            floor_step=float(gold["floor_step"]),
            variance=float(gold["variance"]),
            item_chance=float(payload["item_chance"]),
            scatter=float(payload.get("scatter", 0.0)),
            tiers=tiers,
            shop={
                key: value
                for key, value in payload["shop"].items()
                if not key.startswith("_")
            },
        )

    # --- rolling -------------------------------------------------------------
    def gold_for(self, monster_level: int, floor: int, rng, find: float = 0.0) -> int:
        """What one kill pays, before anything is multiplied by a rarity.

        `find` is the run's gold-find bonus as a fraction -- 0.5 means half as
        much again. Applied here rather than at collection so that the number
        lying on the floor is already the number you get, and a Charm bought
        halfway through a stage does not retroactively enrich the coins behind
        you.
        """
        depth = 1.0 + self.floor_step * max(0, floor - 1)
        amount = self.gold_base * max(1, monster_level) * depth * (1.0 + find)
        if self.variance > 0:
            amount *= rng.uniform(1.0 - self.variance, 1.0 + self.variance)
        # Never zero. A kill that pays nothing reads as a bug, in exactly the
        # way combat.MIN_DAMAGE exists to prevent.
        return max(1, round(amount))

    def roll_rarity(self, rng) -> Rarity:
        """One tier, by weight.

        Rolled long-hand rather than with `random.choices` so the draw is a
        single call on the injected generator. `choices` is free to consume a
        different number of values between Python versions, and a seeded replay
        that depends on the interpreter build is not a seeded replay.
        """
        total = sum(tier.weight for tier in self.tiers)
        ticket = rng.uniform(0.0, total)
        running = 0.0
        for tier in self.tiers:
            running += tier.weight
            if ticket < running:
                return tier.rarity
        # Only reachable on floating-point drift at the very top of the range.
        return self.tiers[-1].rarity

    def worth_of(self, rarity: Rarity) -> float:
        for tier in self.tiers:
            if tier.rarity is rarity:
                return tier.worth
        raise KeyError(f"no tier for rarity '{rarity}'")

    def roll_drops(
        self,
        monster_level: int,
        floor: int,
        pos: Vec2,
        rng,
        find: float = 0.0,
    ) -> list[Pickup]:
        """Everything one death leaves on the floor.

        Always a coin, and on a successful chance roll a valuable beside it.
        Both are scattered a little so they read as two things; the valuable is
        worth the same kill's gold multiplied by its rarity, which is what makes
        a legendary off a boss deep in a run worth a stage of ordinary income.
        """
        base = self.gold_for(monster_level, floor, rng, find)
        drops = [Pickup(pos=self._scattered(pos, rng), gold=base)]

        if rng.random() < self.item_chance:
            rarity = self.roll_rarity(rng)
            drops.append(
                Pickup(
                    pos=self._scattered(pos, rng),
                    gold=max(1, round(base * self.worth_of(rarity))),
                    rarity=rarity,
                )
            )
        return drops

    def _scattered(self, pos: Vec2, rng) -> Vec2:
        if self.scatter <= 0:
            return pos
        return Vec2(
            pos.x + rng.uniform(-self.scatter, self.scatter),
            pos.y + rng.uniform(-self.scatter, self.scatter),
        )


_TABLE: LootTable | None = None


def table() -> LootTable:
    """The shipped loot table, read from disk once.

    Lazy rather than loaded at import. `test_architecture.py` imports every
    module in `game/` in a bare interpreter to prove none of them pulls in
    pygame, and a module that reads a file at import time turns a missing data
    file into a failure of that test, reported as an import error that names the
    wrong problem.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = LootTable.load()
    return _TABLE
