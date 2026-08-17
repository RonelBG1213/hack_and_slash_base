"""Experience, levels, and spending what they pay out.

The layer that turns kills into `Attributes`. It owns the arithmetic and none of
the numbers -- those are in `data/progression.json`, which also carries the
reasoning for each of them and the warning about turning the thing on.

Named `progression` and not `levels` on purpose: `levels/` at the repo root is
the forty stage files, and two meanings for one word across one project is a
half hour somebody spends in the wrong directory.

**It ships switched off.** `xp_base` is zero in the shipped table, so nothing is
earned, no level is reached, and every attribute in the game stays neutral. That
is what makes the claim "the recorded grid is unmoved" a fact about the code
rather than a hope -- and setting it back to zero is the rollback.

**It draws no dice, ever.** A kill is worth exactly `xp_base * monster_level`.
There is no third RNG stream here because there is nothing to roll, which is
also why this layer cannot disturb a damage roll however it is tuned.

Pure arithmetic -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from .. import config
from .attributes import Attributes

#: Every attribute name, derived rather than listed, so a new one is spendable
#: the day it is declared -- and, through the check in `Table.load`, refuses to
#: start until `data/progression.json` says what a point in it buys.
SPENDABLE: tuple[str, ...] = tuple(f.name for f in dataclasses.fields(Attributes))


@dataclass(frozen=True)
class Curve:
    """What a level costs and what it pays."""

    first: int
    step: int
    max_level: int
    points_per_level: int

    def cost_of(self, level: int) -> int:
        """Experience needed to reach `level` from the one below it.

        Linear rather than exponential. Forty stages of gently rising value is
        the shape this has to fit, and a curve that bends either way puts every
        level in one act.
        """
        return self.first + self.step * (level - 2)


@dataclass(frozen=True)
class Table:
    """The contents of `data/progression.json`, read once.

    Frozen, because it is content in the same sense the bestiary and the loot
    table are: tuning progression means editing the JSON, never this file.
    """

    xp_base: int
    curve: Curve

    #: What one point buys, per attribute name, in that attribute's own units.
    points: dict[str, int]

    @property
    def is_off(self) -> bool:
        """Whether the whole layer is inert.

        The single switch, and the rollback. Nothing is earned at zero, so no
        level is reached, so no point is ever spendable, so every attribute
        stays neutral and the game is arithmetically the one that was measured.
        """
        return self.xp_base <= 0

    def xp_for(self, monster_level: int) -> int:
        """What killing something of this level pays.

        Reuses `EntityType.level` -- already tuned, already meaning "how
        dangerous was that" -- rather than inventing a second danger scale
        beside it for the same job.
        """
        return max(0, self.xp_base * max(1, monster_level))

    def gain(self, attribute: str, points: int) -> Attributes:
        """The attribute block `points` spent on one attribute buys."""
        if attribute not in self.points:
            raise KeyError(
                f"'{attribute}' is not spendable; the {len(self.points)} are "
                f"{sorted(self.points)}"
            )
        return Attributes(**{attribute: self.points[attribute] * points})

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        source = path or config.PROGRESSION_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))
        curve = payload["curve"]

        points = {
            name: int(value)
            for name, value in payload["points"].items()
            if not name.startswith("_")
        }
        # Bidirectional, the way `shop.stock()` validates its goods: a table
        # that prices all but one attribute leaves that one silently
        # unspendable, and a table that prices something that is not an
        # attribute is a typo that would otherwise sit there costing nothing.
        # Both halves fire loudly at startup, which is how an attribute added to
        # the dataclass without a price is caught on the day it is added.
        missing = sorted(set(SPENDABLE) - set(points))
        unknown = sorted(set(points) - set(SPENDABLE))
        if missing or unknown:
            raise KeyError(
                f"{source}: points prices {unknown or 'nothing unknown'} and is "
                f"missing {missing or 'nothing'}; the {len(SPENDABLE)} are "
                f"{sorted(SPENDABLE)}"
            )

        return cls(
            xp_base=int(payload["xp_base"]),
            curve=Curve(
                first=int(curve["first"]),
                step=int(curve["step"]),
                max_level=int(curve["max_level"]),
                points_per_level=int(curve["points_per_level"]),
            ),
            points=points,
        )


_TABLE: Table | None = None


def table() -> Table:
    """The shipped progression table, read from disk once.

    Lazy rather than at import, for the reason `loot.table()` gives: a module
    that reads a file at import time turns a missing data file into a failure of
    `test_architecture.py`, reported as an import error naming the wrong problem.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


# --- what a run does with it -------------------------------------------------
def bank(run, amount: int) -> None:
    """Take experience the stage accumulated, and level up if it is enough.

    Called from `Run._bank`, beside the gold, and the two travel the same road
    for the same reason: `sim` knows nothing about a `Run`. A stage accumulates
    onto `World.xp` exactly as it accumulates onto `World.gold`, and the layer
    above collects it. Putting the levelling in the sim would mean handing the
    tick a `Run`, which is the seam the whole architecture is built to avoid.

    A single stage can carry more than one level when the table is generous, so
    this loops rather than testing once.
    """
    progression = table()
    if progression.is_off or amount <= 0:
        return

    run.xp += amount
    curve = progression.curve
    while run.hero_level < curve.max_level and run.xp >= curve.cost_of(run.hero_level + 1):
        run.xp -= curve.cost_of(run.hero_level + 1)
        run.hero_level += 1
        run.unspent_points += curve.points_per_level


def spend(run, attribute: str, points: int = 1) -> bool:
    """Put points into one attribute. False if the run cannot afford it.

    Refused rather than clamped, the way `shop.buy` refuses: a partial purchase
    the player did not ask for is worse than one that visibly did not happen.

    Writes both halves -- `run.earned`, which survives into the next stage, and
    the live body's `Entity.bonus`, which is what the sim actually reads. Doing
    only the first would leave the point inert until the next stage boundary,
    and doing only the second would lose it at that boundary.
    """
    if points <= 0 or run.unspent_points < points:
        return False

    run.earned = run.earned + table().gain(attribute, points)
    run.unspent_points -= points

    hero = run.world.hero
    if hero is not None:
        hero.bonus = run.earned
    return True
