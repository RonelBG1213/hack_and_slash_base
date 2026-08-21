"""How hard the fight is, chosen once per run.

**Why this is content and not a setting.** `scenes/options.py` is drawn on the
line that nothing on it may change how a fight resolves, and it names this
feature specifically: *a difficulty row would be a balance decision worn as a
preference, and the project's whole measurement culture rests on balance
decisions being made in `data/` where they can be swept.* That refusal still
stands and is still right. This module is the other half of the sentence -- the
decision lives in `data/difficulty.json`, beside every other tuning number, with
`tools/balance.py --difficulty` behind it.

**One dial.** `incoming` is a per-mille multiplier on damage arriving at the
hero. Nothing else moves: not enemy health, not cadence, not counts. Enemy
health is the obvious alternative and this project has already measured it as
close to inert -- the enrage threshold is a fraction, so a boss spends the same
*proportion* of a shorter fight enraged, and both late bosses were eventually
tuned by damage after health changes moved the win rate by nothing.

**`PER_MILLE` is the identity and that is load-bearing.** At 1000 `scaled`
takes an early return and the arithmetic is the arithmetic that was measured, so
"Normal is the game the recorded grid was measured against" is a millisecond
test rather than a sweep. The same trick `attributes.py` plays by defaulting
every field to the identity of its own operation, and it is here for the same
reason: it is what lets a dial be added to a tuned game and *proved* neutral.

The floor is deliberately **not** applied here. `combat.MIN_DAMAGE` is combat's
to own, and importing it would make this module depend on the one that depends
on it. Every caller applies the floor, and `test_combat.py` pins that they do.

Pure arithmetic on plain data -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .. import config
from .attributes import PER_MILLE


@dataclass(frozen=True)
class Difficulty:
    """One tier. Frozen, like every other piece of loaded content."""

    id: str = "normal"
    name: str = "Normal"

    #: One line for the select screen, in the voice of `select.ROLES`.
    blurb: str = ""

    #: Per-mille multiplier on damage the hero takes. 1000 changes nothing.
    incoming: int = PER_MILLE

    #: Whether the numbers above have been swept. False is not a defect -- it
    #: is the project's rule that a guess is flagged where it lives, exactly as
    #: `data/loot.json` separates its prices from its drop rates.
    measured: bool = True

    @property
    def is_identity(self) -> bool:
        """Whether this tier is arithmetically the game that was measured."""
        return self.incoming == PER_MILLE

    def scaled(self, damage: int) -> int:
        """This hit, on this tier. Callers apply `combat.MIN_DAMAGE` underneath.

        The early return is the point of the method rather than an optimisation:
        at the identity it must be provable that nothing happened at all.
        """
        if self.incoming == PER_MILLE:
            return damage
        return (damage * self.incoming) // PER_MILLE


#: The tier every default in the codebase reaches for. Constructed rather than
#: loaded, so a `World` built by a test that has never heard of difficulty is
#: still the fight that test was written against, with no file read at all.
NORMAL = Difficulty()


@dataclass(frozen=True)
class Table:
    """Every tier the game offers, in the order the select screen draws them."""

    tiers: tuple[Difficulty, ...]
    default_id: str

    def __getitem__(self, tier_id: str) -> Difficulty:
        for tier in self.tiers:
            if tier.id == tier_id:
                return tier
        raise KeyError(tier_id)

    def get(self, tier_id: str) -> Difficulty:
        """The named tier, or the default. For a save file naming a tier that
        no longer exists -- which is a reason to carry on at Normal, not a
        reason to refuse to load somebody's run."""
        try:
            return self[tier_id]
        except KeyError:
            return self.default

    @property
    def default(self) -> Difficulty:
        return self[self.default_id]

    @property
    def index_of_default(self) -> int:
        return [tier.id for tier in self.tiers].index(self.default_id)

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        """Read the tiers, refusing loudly on anything malformed.

        Loud because this is content, not preference: `settings.py` is forgiving
        about a half-written file because the worst case there is somebody
        setting their window scale twice. A typo in a damage multiplier is a bug
        somebody has to see, and it is better said at startup than discovered by
        a hero dying twice as fast as the screen promised.
        """
        source = path or config.DIFFICULTY_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))

        entries = payload["tiers"]
        if not entries:
            raise ValueError(f"{source}: no tiers, and the game needs one to start")

        tiers: list[Difficulty] = []
        seen: set[str] = set()
        for entry in entries:
            tier_id = str(entry["id"])
            if tier_id in seen:
                raise ValueError(f"{source}: two tiers share the id {tier_id!r}")
            seen.add(tier_id)

            incoming = int(entry["incoming"])
            if incoming < 1:
                # Zero is not a gentler setting, it is a different game: a hero
                # nothing can hurt runs every stage to the tick limit, and every
                # instrument in this project reports that as a balance failure.
                # `combat.MIN_DAMAGE` makes the same argument one layer down.
                raise ValueError(
                    f"{source}: {tier_id!r} has incoming {incoming}, and a hero "
                    f"that cannot be hurt runs the stage out rather than winning it"
                )

            tiers.append(
                Difficulty(
                    id=tier_id,
                    name=str(entry["name"]),
                    blurb=str(entry.get("blurb", "")),
                    incoming=incoming,
                    measured=bool(entry.get("_measured", False)),
                )
            )

        default_id = str(payload["default"])
        table = cls(tiers=tuple(tiers), default_id=default_id)

        if default_id not in seen:
            raise ValueError(
                f"{source}: default is {default_id!r}, which is not one of "
                f"{', '.join(sorted(seen))}"
            )

        if not table.default.is_identity:
            # The whole claim this feature rests on. A default that scales
            # damage means every recorded number in the project silently
            # describes a game nobody plays by default any more.
            raise ValueError(
                f"{source}: the default tier {default_id!r} has incoming "
                f"{table.default.incoming}, so the game it starts is not the "
                f"game the recorded balance grid was measured against"
            )

        return table


_TABLE: Table | None = None


def table() -> Table:
    """The shipped tiers, read from disk once.

    Lazy rather than at import, for the reason `loot.table()` gives: a module
    that reads a file at import time turns a missing data file into a failure of
    `test_architecture.py`, reported as an import error naming the wrong problem.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


def reset_cache() -> None:
    """Forget the loaded table. For tests that supply their own."""
    global _TABLE
    _TABLE = None
