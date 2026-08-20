"""Putting a run down and picking it up again.

**A save is taken on the tick a room begins, and at no other moment.** That is
the entire design, and everything else here follows from it.

It used to say "a stage", and a reward room is the second thing that qualifies.
Not a widening of the rule -- a room meets it for exactly the same reason an
arena does: `Run._enter_room` builds one out of a level, a seed, the health
carried in and the purse, and nothing has moved by the time the first tick is
taken. Quitting inside a fountain and being handed back the arena before it
would be a stage replayed for no reason.

`Run._advance` builds the next stage's `World` out of four things: the level from
the campaign, `_stage_seed(seed, index)`, the health carried in, and the purse.
Nothing else. So a snapshot taken before `sim.step` has run once on that world
describes it *completely* -- restoring means handing the same four values back to
the same constructor and getting the same arena, enemy for enemy, down to the
first damage roll. `test_save.py` asserts that rather than trusting it.

The alternative was a save that works mid-fight, and it was refused for the
reason the shop refuses a stat upgrade: it would mean serialising every entity
position, every cooldown, every projectile in flight and the internal state of
three `Random`s, and the format would then be welded to the sim's internals --
so every change to a fight would become a change to the save format, and an old
save would come back as a subtly different fight with nothing to report it.

What this module does *not* do is touch the disk on its own account. `snapshot`
and `restore` are pure functions over a `dict`; `read`, `write` and `delete` take
a path and are called from `scenes/`. `tools/balance.py` and
`test_playthrough.py` drive `Run` directly and never construct a scene, so the
balance sweep cannot grow a dependency on a file.

Pure Python -- no pygame, like everything else in `game/`.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .. import config
from ..core.campaign import Campaign
from ..core.level import Direction, RoomKind
from . import rooms
from .attributes import NEUTRAL, Attributes
from .entities import DEFAULT_HERO, Bestiary
from .run import Run
from .world import Purse, World

#: Bumped when the shape of a snapshot changes in a way an older reader would
#: get wrong. A save from another version is refused rather than guessed at --
#: see `restore`, and the note there about what this does and does not catch.
SAVE_VERSION = 3


class SaveFormatError(Exception):
    """A save file that cannot be trusted to describe a run.

    Named and raised the way `core.campaign_io.CampaignFormatError` is, and for
    the same reason: the caller's answer is to say so and carry on, not to
    stumble on with half a run loaded.
    """


def snapshot(run: Run) -> dict:
    """Everything about `run` that a stage boundary does not recreate.

    Read from the run rather than from the world, with the single exception of
    the hero's health -- which is the one number that lives on the body and
    carries. `World.gold` and `World.xp` are deliberately absent: at a stage
    boundary `Run._bank` has already emptied both into the run, so reading them
    here would either be zero or would double-count whatever was still loose.
    """
    hero = run.world.hero
    return {
        "version": SAVE_VERSION,
        "seed": run.seed,
        "index": run.index,
        "start_index": run.start_index,
        "hero_type_id": run.hero_type_id,
        # Kept beside `hero_type_id`, never instead of it. See `restore`.
        "job_id": run.job_id,
        "hp": hero.hp if hero is not None else 1,
        "gold": run.gold,
        "bonus_heal": run.bonus_heal,
        "gold_find": run.gold_find,
        "xp": run.xp,
        "hero_level": run.hero_level,
        "unspent_points": run.unspent_points,
        "purchases": dict(run.purchases),
        "earned": dataclasses.asdict(run.earned),
        # Which reward room is being stood in, and which one the last door
        # chose. Both plain strings, and both empty in an arena.
        #
        # The doors themselves are *not* written down: `rooms.offer` is a pure
        # function of the seed and the index, so a loaded run is offered the
        # same three it was offered before. That is the whole reason the map
        # stream is stateless -- a held `Random` would have to be serialised
        # here, and a save format welded to a generator's internals is the
        # thing the module docstring above refuses.
        "room": run.room.value if run.room else "",
        "next_room": run.next_room.value if run.next_room else "",
        # ...and which wall each is entered by. Not derivable from anything else
        # in this payload: the doors are a pure function of the seed and the
        # index, but *which* of them was walked through is a choice the player
        # made, and it decides where the three doors of the room being restored
        # are standing. Restoring without it rebuilds a different room.
        "entered_from": run.entered_from.value,
        "next_entrance": run.next_entrance.value,
    }


def check_version(payload: dict) -> None:
    """Raise unless this build wrote the save.

    Split out of `restore` so `read` can make the same check without building a
    world. The menu greys its Load Game row on what `read` says, and a row that
    looks live until it is pressed and *then* admits it cannot load is worse
    than one that was honest about it first.
    """
    version = payload.get("version")
    if version != SAVE_VERSION:
        raise SaveFormatError(
            f"save version {version!r}, expected {SAVE_VERSION} -- "
            "this save was written by a different build of the game"
        )


def restore(payload: dict, campaign: Campaign, bestiary: Bestiary) -> Run:
    """Rebuild the run a snapshot describes.

    The world is *constructed*, not deserialised -- the same call `Run._advance`
    makes, with the same arguments. That is what makes a loaded stage the stage
    that was saved rather than one that merely resembles it.

    Raises `SaveFormatError` on anything it cannot read.
    """
    if not isinstance(payload, dict):
        raise SaveFormatError("the save file is not an object")

    check_version(payload)

    try:
        seed = int(payload["seed"])
        index = int(payload["index"])
        hero_type_id = str(payload["hero_type_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SaveFormatError(f"the save file is missing {exc}") from exc

    # `bestiary.types` rather than `bestiary`, deliberately: `Bestiary` has a
    # `__getitem__` and no `__contains__`, so `in` would fall back to the
    # integer-index protocol and come back with a KeyError about type `0`.
    if hero_type_id not in bestiary.types:
        raise SaveFormatError(f"the save names a class that does not exist: {hero_type_id!r}")

    job_id = str(payload.get("job_id", ""))
    if job_id and job_id not in bestiary.types:
        raise SaveFormatError(f"the save names a job that does not exist: {job_id!r}")

    # Clamped rather than refused. `levels/*.json` is generated, so a campaign
    # can legitimately be shorter than it was when the save was written -- and
    # dropping somebody back to the title screen over it is a worse answer than
    # putting them on the last stage there is.
    index = max(0, min(index, len(campaign) - 1))

    earned = _attributes(payload.get("earned"))
    gold_find = float(payload.get("gold_find", 0.0))

    room = _room(payload.get("room"))
    entered_from = _direction(payload.get("entered_from"))
    level = (
        rooms.chamber(room, rooms.offer(seed, index), entered_from)
        if room
        else campaign[index]
    )

    world = World(
        level,
        bestiary,
        # `Run._stage_seed` and `Run._room_seed`, private and reached for
        # across a module boundary on purpose. The alternative is writing
        # `seed + index * 1013` here, which is the same arithmetic in a second
        # place -- and the day somebody changes the offset, a loaded stage would
        # quietly become a different fight from the one that was saved, with
        # every number still plausible.
        seed=Run._room_seed(seed, index) if room else Run._stage_seed(seed, index),
        carry_hp=int(payload.get("hp", 1)),
        # `job_id or hero_type_id`, exactly as `Run.hero_type` reads it. Loading
        # a promoted run from `hero_type_id` alone would put the player back in
        # the class they grew out of, twenty stages into a campaign tuned for
        # the one they chose -- the same mistake `Run._advance` made when
        # promotion moved to the midpoint, wearing a different hat.
        hero_type_id=job_id or hero_type_id,
        purse=Purse(floor=index + 1, gold_find=gold_find),
        hero_bonus=earned,
    )

    return Run(
        campaign=campaign,
        bestiary=bestiary,
        world=world,
        index=index,
        seed=seed,
        hero_type_id=hero_type_id,
        start_index=int(payload.get("start_index", 0)),
        gold=int(payload.get("gold", 0)),
        bonus_heal=int(payload.get("bonus_heal", 0)),
        gold_find=gold_find,
        earned=earned,
        xp=int(payload.get("xp", 0)),
        hero_level=int(payload.get("hero_level", 1)),
        unspent_points=int(payload.get("unspent_points", 0)),
        purchases={str(k): int(v) for k, v in (payload.get("purchases") or {}).items()},
        room=room,
        next_room=_room(payload.get("next_room")),
        entered_from=entered_from,
        next_entrance=_direction(payload.get("next_entrance")),
        job_id=job_id,
    )


def _room(raw) -> RoomKind | None:
    """One of the reward kinds, or None for "standing in an arena".

    A value that names nothing is refused rather than defaulted to None. The
    difference matters: None means the run is in an arena, and quietly turning
    a typo into that would drop the player into stage N having already fought
    it, with nothing anywhere to say why.
    """
    if not raw:
        return None
    try:
        kind = RoomKind(str(raw))
    except ValueError:
        raise SaveFormatError(f"the save names a room that does not exist: {raw!r}") from None
    if kind not in rooms.REWARD_PROP:
        raise SaveFormatError(f"the save says the hero is standing in a {kind.value}")
    return kind


def _direction(raw) -> Direction:
    """One of the four walls, or the entrance every run starts from.

    Empty falls back rather than being refused, which is the opposite of what
    `_room` does above and is right for the opposite reason: a missing wall is
    what a run that has not been through a door yet looks like, and the room
    after arena one is entered from the west by definition. A value that *names*
    something and names it wrong is still refused -- that is a corrupt save, not
    an absent choice.
    """
    if not raw:
        return rooms.FIRST_ENTRANCE
    try:
        return Direction(str(raw))
    except ValueError:
        raise SaveFormatError(f"the save names a wall that does not exist: {raw!r}") from None


def _attributes(raw) -> Attributes:
    """The earned block, or the shared `NEUTRAL` singleton if it is empty.

    Returning `NEUTRAL` *itself* rather than an equal copy is not tidiness.
    `World._populate` tests `hero_bonus is not NEUTRAL` by identity, and takes a
    branch that re-fills the hero to full health when it fires. An equal-but-
    distinct block would take that branch on every load, which is a different
    code path from the one the same stage went through when it was played --
    exactly the kind of divergence this module exists to rule out.
    """
    if not isinstance(raw, dict):
        return NEUTRAL

    known = {f.name for f in dataclasses.fields(Attributes)}
    block = Attributes(
        **{k: int(v) for k, v in raw.items() if k in known and isinstance(v, int)}
    )
    return NEUTRAL if block == NEUTRAL else block


def describe(payload: dict, bestiary: Bestiary) -> str:
    """One line for the menu row: who, how far, how rich.

    Derived on read rather than stored. A label written into the file at save
    time is a second copy of facts already in it, and the two disagree the first
    time anything is renamed.
    """
    try:
        type_id = str(payload.get("job_id") or payload.get("hero_type_id") or DEFAULT_HERO)
        name = bestiary[type_id].name if type_id in bestiary.types else type_id
        stage = int(payload.get("index", 0)) + 1
        gold = int(payload.get("gold", 0))
    except (TypeError, ValueError):
        return "a saved run"
    return f"{name}  --  stage {stage}  --  {gold}g"


# --- the disk ----------------------------------------------------------------
def read(path: Path | None = None) -> dict | None:
    """The saved run, or None if there is not one.

    None for "no save" and an exception for "a save that is wrong" are two
    different answers on purpose: the menu greys its row for the first and has
    something to say about the second.
    """
    source = path or config.SAVE_FILE
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError:
        return None
    except ValueError as exc:
        raise SaveFormatError(f"{source} is not readable JSON: {exc}") from exc

    if not isinstance(payload, dict):
        return None

    # A save from another build is "wrong", not "absent" -- so it raises here
    # rather than reading as None, and the caller says so instead of silently
    # pretending the player never played.
    check_version(payload)
    return payload


def write(run: Run, path: Path | None = None) -> None:
    """Save `run`. Only ever called on the tick a stage begins -- see the module
    docstring for why that is the whole of the design.

    Written to a neighbouring file and moved into place, so a crash or a power
    cut during the write leaves the previous save intact rather than a truncated
    one. The autosave fires on every stage transition of a forty-stage run, so
    "halfway through a write" is a real moment that happens forty times a run.
    """
    target = path or config.SAVE_FILE
    payload = snapshot(run)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        scratch = target.with_suffix(".json.part")
        scratch.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        scratch.replace(target)
    except OSError:
        # A save that cannot be written must not end the run that was being
        # played. Same judgement as `settings.save`.
        pass


def delete(path: Path | None = None) -> None:
    """Forget the saved run. Called when one ends, however it ended."""
    target = path or config.SAVE_FILE
    target.unlink(missing_ok=True)
