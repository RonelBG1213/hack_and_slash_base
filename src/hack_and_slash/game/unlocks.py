"""What a lost run leaves behind, and the one rule it lives under.

`game/profile.py` keeps four counters and says plainly that nothing in the sim,
in `Run`, or in anything deciding a fight ever reads one. This module is the
first thing that reads them -- and it is built so that reading them still cannot
move the recorded class-by-stage grid.

**Access only, and it is structural rather than a promise.** An unlock that
grants a *stat* moves the grid: a run that begins with numbers the reference bot
did not have is measuring a different game. An unlock that grants **access** --
a tier, a class, a modifier the player opts into -- does not, because the grid
measures a specified class over a specified stage and is indifferent to how the
player got the right to pick it. So there is no `attributes` key in the schema
below and no import of `attributes.py` above: a stat grant is not something this
file refuses, it is something it cannot express.

**Nothing is stored.** What is unlocked is *derived* from the profile every time
it is asked for, which is `promotes_from`, `variant_of` and `rooms._wall_of` a
fourth time -- one fact, derived, cannot disagree with itself. There is no
unlock state under `state/`, nothing to migrate, and `profile.load`'s int-only
filter never had to learn about a list.

**An empty table is today's game**, exactly, and that is the rollback: nothing
is locked unless an entry says it is locked, so `"unlocks": []` restores the
game that shipped before this file existed. That property is also why the loader
does *not* check that every modifier the code implements is reachable -- a
two-way check in `shop.stock`'s image would make the rollback illegal. A content
test asserts it of the shipped file instead, which is where the claim belongs.

Pure Python -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path

from .. import config
from .profile import Profile

#: The counters a requirement may name. Derived from `Profile` rather than
#: listed, so a fifth counter is usable by the data file the day it is declared,
#: and a typo in the data file is a load error rather than a row nobody can ever
#: earn.
COUNTERS: tuple[str, ...] = tuple(f.name for f in fields(Profile))


class Grant(str, Enum):
    """What an unlock hands over. Two members, and both are *access*.

    A third member is a decision point rather than a line of code: anything that
    is not "the player may now choose X" belongs in a design discussion and a
    sweep. `str`, so the value is what appears in `data/unlocks.json`.
    """

    DIFFICULTY = "difficulty"
    MODIFIER = "modifier"


#: Run modifiers this code implements. A `modifier` unlock naming anything else
#: is a load error -- the half of the data/code contract that can be checked
#: without making an empty table illegal.
MODIFIERS: tuple[str, ...] = ("champions",)

#: How a requirement reads on a screen. Keyed by counter name; a counter with no
#: phrase falls back to something plain but truthful, so adding a counter to
#: `Profile` cannot crash a menu.
PHRASES: dict[str, str] = {
    "runs_started": "start {n} runs",
    "runs_won": "win {n} runs",
    "deepest_stage": "reach stage {n}",
    "best_gold": "finish a run holding {n} gold",
}

#: The singular reading, where the plural one is wrong at one. "win 1 runs" is
#: the kind of thing that makes a menu look unfinished.
SINGULAR: dict[str, str] = {
    "runs_started": "start a run",
    "runs_won": "win a run",
}


@dataclass(frozen=True)
class Requirement:
    """What a profile has to show before an unlock is earned.

    Held as `(counter, threshold)` pairs rather than as named fields, so this
    dataclass does not carry a second copy of `Profile`'s schema that could
    drift out of step with it.

    Every comparison is `>=`, and every counter it can name only ever goes up
    (`profile.record_stage` takes a `max`). So an unlock cannot be taken back
    once it is earned, which is the only behaviour a player will accept from a
    screen with the word "unlocked" on it.
    """

    counters: tuple[tuple[str, int], ...] = ()

    @property
    def is_free(self) -> bool:
        """Whether this asks for nothing at all.

        Refused at load: an unlock nobody has to earn is not an unlock, it is a
        row that reads "unlocked" on a fresh profile and teaches the player that
        the screen is decoration.
        """
        return not any(threshold > 0 for _, threshold in self.counters)

    def met_by(self, profile: Profile) -> bool:
        return all(
            getattr(profile, name) >= threshold for name, threshold in self.counters
        )

    def describe(self) -> str:
        """One line, in the voice of `select.ROLES`. Empty for a free one."""
        parts = []
        for name, threshold in self.counters:
            if threshold <= 0:
                continue
            if threshold == 1 and name in SINGULAR:
                parts.append(SINGULAR[name])
            else:
                parts.append(PHRASES.get(name, name + " {n}").format(n=threshold))
        return ", ".join(parts)


@dataclass(frozen=True)
class Unlock:
    """One earnable piece of access."""

    id: str
    name: str
    kind: Grant
    target: str
    requires: Requirement
    blurb: str = ""

    def earned_by(self, profile: Profile) -> bool:
        return self.requires.met_by(profile)


@dataclass(frozen=True)
class Table:
    """Everything earnable, in the order the Unlockables screen draws it."""

    entries: tuple[Unlock, ...] = ()

    def __getitem__(self, unlock_id: str) -> Unlock:
        for entry in self.entries:
            if entry.id == unlock_id:
                return entry
        raise KeyError(unlock_id)

    def for_kind(self, kind: Grant) -> tuple[Unlock, ...]:
        return tuple(entry for entry in self.entries if entry.kind is kind)

    def gating(self, kind: Grant, target: str) -> Unlock | None:
        """The entry standing in front of a thing, or None if nothing does.

        None is the common answer and the important one: a tier no entry names
        is simply open, which is what makes an empty table the game that shipped
        before unlocks existed.
        """
        for entry in self.entries:
            if entry.kind is kind and entry.target == target:
                return entry
        return None

    @classmethod
    def load(cls, path: Path | None = None) -> "Table":
        """Read the table, refusing loudly on anything malformed.

        Loud for the reason `difficulty.Table.load` is loud: this is content,
        not preference. A requirement naming a counter that does not exist would
        otherwise be a row nobody can ever earn, discovered by a player rather
        than at startup.

        The `difficulty` target is checked against the tier table, and that is
        the one cross-file check here. It is deliberately one-way -- see the
        module docstring on why the reverse check would outlaw the rollback.
        """
        source = path or config.UNLOCKS_DATA
        payload = json.loads(source.read_text(encoding="utf-8"))

        entries: list[Unlock] = []
        seen: set[str] = set()
        for entry in payload["unlocks"]:
            unknown = set(entry) - {"id", "name", "kind", "target", "requires", "blurb"}
            if unknown:
                # Unknown keys raise rather than being ignored, exactly as
                # `Attributes.from_dict` and `difficulty._enemies` do -- and
                # here it is load-bearing rather than tidy, because the key
                # somebody will reach for first is `attributes`.
                raise ValueError(
                    f"{source}: {entry.get('id', '?')!r} has keys this file does "
                    f"not define: {', '.join(sorted(unknown))}. An unlock grants "
                    f"access and never numbers"
                )

            unlock_id = str(entry["id"])
            if unlock_id in seen:
                raise ValueError(f"{source}: two unlocks share the id {unlock_id!r}")
            seen.add(unlock_id)

            try:
                kind = Grant(str(entry["kind"]))
            except ValueError:
                raise ValueError(
                    f"{source}: {unlock_id!r} grants {entry['kind']!r}, which is "
                    f"not one of {', '.join(k.value for k in Grant)}"
                ) from None

            target = str(entry["target"])
            _check_target(source, unlock_id, kind, target)

            requires = _requirement(source, unlock_id, entry.get("requires"))
            if requires.is_free:
                raise ValueError(
                    f"{source}: {unlock_id!r} asks for nothing, and an unlock "
                    f"nobody has to earn is not an unlock"
                )

            entries.append(
                Unlock(
                    id=unlock_id,
                    name=str(entry["name"]),
                    kind=kind,
                    target=target,
                    requires=requires,
                    blurb=str(entry.get("blurb", "")),
                )
            )

        return cls(entries=tuple(entries))


def _check_target(source: Path, unlock_id: str, kind: Grant, target: str) -> None:
    """That the thing being unlocked exists.

    Per kind, because the two answer to different authorities: a tier is content
    and a modifier is code.
    """
    if kind is Grant.MODIFIER and target not in MODIFIERS:
        raise ValueError(
            f"{source}: {unlock_id!r} unlocks the modifier {target!r}, which "
            f"nothing implements. Known: {', '.join(MODIFIERS)}"
        )

    if kind is Grant.DIFFICULTY:
        # Imported here rather than at module scope: `difficulty.table()` reads
        # a file, and dragging that read to import time is the thing that
        # function's own docstring gives as the reason it is lazy.
        from . import difficulty

        known = [tier.id for tier in difficulty.table().tiers]
        if target not in known:
            raise ValueError(
                f"{source}: {unlock_id!r} unlocks the tier {target!r}, which "
                f"data/difficulty.json does not declare. Known: {', '.join(known)}"
            )


def _requirement(source: Path, unlock_id: str, payload: dict | None) -> Requirement:
    """One entry's `requires` block, refusing a counter nothing keeps."""
    if not payload:
        return Requirement()

    counters: list[tuple[str, int]] = []
    for name, value in payload.items():
        if name not in COUNTERS:
            raise ValueError(
                f"{source}: {unlock_id!r} waits on {name!r}, which the profile "
                f"does not keep. Known: {', '.join(COUNTERS)}"
            )
        counters.append((str(name), int(value)))
    return Requirement(counters=tuple(counters))


_TABLE: Table | None = None


def table() -> Table:
    """The shipped table, read from disk once. Lazy, as every other one is."""
    global _TABLE
    if _TABLE is None:
        _TABLE = Table.load()
    return _TABLE


def reset_cache() -> None:
    """Forget the loaded table. For tests that supply their own."""
    global _TABLE
    _TABLE = None


# --- what a profile has earned -----------------------------------------------
def earned(profile: Profile, source: Table | None = None) -> frozenset[str]:
    """The ids this profile has earned. Derived, never stored."""
    entries = (source or table()).entries
    return frozenset(entry.id for entry in entries if entry.earned_by(profile))


def newly_earned(
    before: Profile, after: Profile, source: Table | None = None
) -> tuple[Unlock, ...]:
    """What crossed the line between two readings of the profile.

    Takes two profiles rather than a set of ids and a profile, so a caller
    cannot compare a set built from one table against a table that has since
    been reloaded. `profile.record_end` already hands back the profile it wrote,
    so the second reading is free at the one call site that needs it.
    """
    shared = source or table()
    crossed = earned(after, shared) - earned(before, shared)
    return tuple(entry for entry in shared.entries if entry.id in crossed)


def is_open(
    kind: Grant, target: str, profile: Profile, source: Table | None = None
) -> bool:
    """Whether the player may pick this thing.

    True when nothing gates it *or* the gate is earned -- the first half being
    the one that matters, because it is what an empty table answers for
    everything in the game.
    """
    gate = (source or table()).gating(kind, target)
    return gate is None or gate.earned_by(profile)
