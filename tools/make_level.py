"""Writes the forty stages and the campaign manifest that orders them.

There is no level editor -- that was a deliberate scope cut. This script is the
compromise: a stage is described here as a size, a list of pillar rectangles and
a list of enemies, which is far easier to get right than counting characters in a
wall of ASCII. The output is plain readable JSON, so a small tweak can be made in
the file directly without coming back here.

    python tools/make_level.py

**The shape.** Eight acts of five. Each act opens by introducing one enemy,
spends three stages combining it with what came before, and ends on a boss:

    act I    1-4   grunt, bowman, charger, rat        5   The Warden
    act II   6-9   the brute                         10   The Houndmaster
    act III  11-14 the mage                          15   The Effigy
    act IV   16-19 everything at once                20   The Sovereign
    ------------------------------------------- the class forks here -------
    act V    21-24 the revenant                      25   The Herald
    act VI   26-29 the stalker                       30   The Gaoler
    act VII  31-34 both of them, together            35   The Choir
    act VIII 36-39 everything at once                40   The Hollow King

**Faces and creatures are different things.** Much of what a stage lists is a
`variant_of` -- a goblin is a grunt, an orc is a brute, a beastman is a revenant,
with every number copied. Substituting one changes what the player sees and
nothing the sim reads, which is why the campaign could be re-faced without
re-measuring a single cell of the balance grid.

Three stages are deliberately left un-re-faced, and each for its own reason:
**1** is the tutorial and teaches one creature, **3** (The Gauntlet) is the one
arena whose numbers are on record and the only thing the balance harness can be
checked against, and **12** (The Terraces) is the open xfail -- nothing should
change within sight of a cell that is under investigation.

> The demon does not appear here, and that is the interesting part. It was
> drafted one-per-stage across acts VII-VIII, standing where a revenant already
> stood, and taken back out: a single one took the assassin's stage 39 from 8/8
> to 0/8. See its entry in `data/entities.json` for what was measured and why the
> reference bot is the wrong instrument for that brain.

Enemy counts rise inside an act and reset at the start of the next one, because
an act opens on a new idea and a new idea deserves room. That is why the
difficulty test checks the curve per act rather than across the campaign.

**The line after stage 20 is the important one.** Clearing the Sovereign forks
the class in two, so every stage from 21 on is fought by an advanced class --
one with more health or less, and two attacks it has never used before. That is
the only place in the campaign where the hero's own numbers move, and it is why
acts V-VIII can ask for more than act IV does without any of it being a scaling
multiplier.

What it does *not* license is enemies that are simply bigger. The hero's light
attack is unchanged across the fork -- an advanced class inherits it -- and the
light is most of what a fight is made of. So the second half is built the same
way the first was: out of count, placement, cadence and reach, with two new
creatures that ask questions the first twenty stages never do.

Stages 1-3 are the originals and are kept at their original indices. That is not
sentiment: stage 3 ("The Gauntlet") is the arena the whole game was first tuned
around and the only stage whose numbers are on record, which makes it the one
thing the balance harness can be checked against. Moving it would throw that
reference away. Stages 1-20 are likewise untouched by the extension, so every
number recorded against them still means what it meant.

Health carries between stages, so these are not forty independent fights -- they
are one run, and stage 40 is fought at whatever you have left.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hack_and_slash import config  # noqa: E402
from hack_and_slash.core import campaign_io, level_io  # noqa: E402
from hack_and_slash.core.campaign import Campaign  # noqa: E402
from hack_and_slash.core.level import (  # noqa: E402
    FLOOR,
    WALL,
    EnemySpawn,
    Level,
    RoomKind,
)


@dataclass(frozen=True)
class Stage:
    """One arena, described the way a person would draw it on paper.

    `pillars` are (x, y, w, h) rectangles of wall in tiles. They exist to break
    line of sight so archers are a positioning problem rather than a damage tax,
    to give chargers something to miss you into, and to stop an arena reading as
    an empty box. Deliberately fat -- one-tile pillars vanish behind a sprite.

    **The constraint that is easy to get wrong:** nothing in this game paths
    around walls. Enemies walk straight at you. So a pillar that seals off a
    lane does not make a stage more interesting, it strands whatever is behind
    it -- and the player has to go and fetch a grunt that has spent the fight
    pushing into a wall. Keep pillars clear of the lanes between the hero spawn
    and the enemies, especially on the sparse early stages where one stuck enemy
    is the difference between a stage ending and not.

    **Three more, all learned building acts V-VIII, all of which produced stages
    that read as balance failures in every table:**

    1. *Nothing on an extreme row.* A spawn on row 3 of a thirty-tall arena is
       twelve tiles from the band the hero actually walks -- 192px against a
       grunt's 220px aggro. It engages only if the player happens to pass near
       its column, and otherwise sits at full health until the tick limit. Keep
       spawns inside the middle band.
    2. *No ranged enemy in a pocket.* An `archer` brain with no line of sight
       does not shoot, so it never becomes the nearest thing in the room, so
       nothing ever goes to it. Same outcome as (1), different cause.
    3. *Ranged enemies are a tax proportional to how late they die,* and the
       archer brain retreats, so on a big crowded stage they die last by
       construction. One mage on a twenty-enemy stage shoots for the entire
       fight. Acts V-VIII carry at most one, and the largest stages carry none
       -- which is the ranged-escort finding from the act III boss stage,
       arriving again once the rooms got big enough.

    The symptom for (1) and (2) is a stage that ends on the tick limit with the
    hero *healthy* and something *untouched*. `why_not()` in the playthrough
    suite reports exactly that, because three of these shipped and cost an
    afternoon of tuning the wrong dial.
    """

    name: str
    filename: str
    width: int
    height: int
    hero: tuple[int, int]
    enemies: list[EnemySpawn]
    pillars: list[tuple[int, int, int, int]] = field(default_factory=list)

    #: Declared, never derived. The eight act enders say `RoomKind.BOSS` in the
    #: table below with their own hands, so `tests/test_playthrough.py` -- which
    #: works the same eight indices out from `STAGES_PER_ACT` -- is checking a
    #: second, independent statement of the fact rather than reading back its
    #: own arithmetic. Two derivations from one formula agree even when the
    #: formula is wrong.
    kind: RoomKind = RoomKind.COMBAT

    def build(self) -> Level:
        grid = [[FLOOR] * self.width for _ in range(self.height)]

        for x in range(self.width):
            grid[0][x] = WALL
            grid[self.height - 1][x] = WALL
        for y in range(self.height):
            grid[y][0] = WALL
            grid[y][self.width - 1] = WALL

        for px, py, pw, ph in self.pillars:
            for y in range(py, py + ph):
                for x in range(px, px + pw):
                    grid[y][x] = WALL

        return Level(
            name=self.name,
            rows=tuple("".join(row) for row in grid),
            hero_spawn=self.hero,
            enemy_spawns=tuple(self.enemies),
            tile=config.TILE,
            kind=self.kind,
        )


def spawns(*entries: tuple[str, int, int]) -> list[EnemySpawn]:
    return [EnemySpawn(kind, (x, y)) for kind, x, y in entries]


STAGES = [
    # --- 1 -------------------------------------------------------------------
    # Small, open, grunts only. Teaches the swing and that things walk at you.
    # Pillars kept small and pushed to the edges: with four enemies and no
    # pathfinding, one stranded behind a wall is a stage that never ends. An
    # earlier draft put a three-tile pillar squarely on the hero's row and the
    # last grunt spent nine thousand ticks pressed against the far side of it.
    Stage(
        name="The Yard",
        filename="stage1.json",
        width=28,
        height=18,
        hero=(3, 9),
        pillars=[(7, 3, 2, 2), (7, 13, 2, 2), (19, 3, 2, 2), (19, 13, 2, 2)],
        enemies=spawns(
            ("grunt", 14, 9),
            ("grunt", 20, 7),
            ("grunt", 20, 11),
            ("grunt", 24, 9),
        ),
    ),
    # --- 2 -------------------------------------------------------------------
    # Archers arrive, and with them the reason pillars exist. The first charger
    # too, in the open middle where its telegraph is readable.
    Stage(
        name="The Pillars",
        filename="stage2.json",
        width=34,
        height=20,
        hero=(3, 10),
        pillars=[
            (8, 3, 3, 4),
            (8, 13, 3, 4),
            (15, 8, 4, 4),
            (23, 3, 3, 4),
            (23, 13, 3, 4),
        ],
        enemies=spawns(
            ("goblin", 13, 4),
            ("grunt", 13, 15),
            ("goblin", 21, 10),
            ("charger", 20, 4),
            ("goblin_slinger", 30, 5),
            ("bowman", 30, 15),
        ),
    ),
    # --- 3 -------------------------------------------------------------------
    # The original arena, unchanged. It is the fight the whole game was tuned
    # around and its numbers are on record, which makes it the one stage the
    # balance harness can be checked against.
    Stage(
        name="The Gauntlet",
        filename="stage3.json",
        width=40,
        height=24,
        hero=(3, 12),
        pillars=[
            (5, 4, 3, 3),
            (5, 17, 3, 3),
            (17, 3, 4, 2),
            (16, 10, 6, 4),
            (18, 19, 4, 2),
            (31, 5, 3, 3),
            (31, 16, 3, 3),
            (25, 8, 2, 2),
            (25, 14, 2, 2),
        ],
        enemies=spawns(
            ("grunt", 11, 6),
            ("grunt", 11, 17),
            ("grunt", 24, 5),
            ("grunt", 24, 18),
            ("grunt", 36, 12),
            ("charger", 14, 12),
            ("charger", 30, 12),
            ("bowman", 36, 4),
            ("bowman", 36, 20),
        ),
    ),
    # --- 4 -------------------------------------------------------------------
    # Rats, and a lot of them. The first stage that cannot be answered by facing
    # the one thing coming at you: a rat is barely slower than you are, so unlike
    # a grunt it cannot be walked away from and left. It has to be dealt with.
    #
    # Placed in loose pairs rather than a single mass. A mass of seven arrives as
    # one wall and is either survived or not; pairs arrive as a problem that
    # keeps changing shape while you solve it.
    Stage(
        name="The Warrens",
        filename="stage4.json",
        width=36,
        height=22,
        hero=(3, 11),
        pillars=[(9, 4, 3, 3), (9, 15, 3, 3), (17, 8, 4, 3), (25, 4, 3, 3), (25, 15, 3, 3)],
        enemies=spawns(
            ("goblin_pup", 14, 5),
            ("rat", 14, 17),
            ("goblin_pup", 20, 6),
            ("rat", 20, 16),
            ("goblin_pup", 27, 8),
            ("rat", 27, 14),
            ("rat", 31, 11),
            ("grunt", 22, 11),
            ("goblin", 30, 5),
            ("goblin", 30, 17),
            ("charger", 16, 11),
        ),
    ),
    # --- 5 -- ACT I BOSS -----------------------------------------------------
    # The boss, and deliberately little else. Four pillars in a wide ring: cover
    # from the volley, and something for a charge to end against. A crowd here
    # would bury the one fight the stage is about.
    Stage(
        name="The Keep",
        filename="stage5.json",
        kind=RoomKind.BOSS,
        width=32,
        height=22,
        hero=(3, 11),
        pillars=[(9, 4, 3, 3), (9, 15, 3, 3), (21, 4, 3, 3), (21, 15, 3, 3)],
        enemies=spawns(
            ("boss", 25, 11),
            ("grunt", 16, 4),
            ("grunt", 16, 17),
        ),
    ),
    # =========================================================================
    # ACT II -- the brute. Everything in this act is about not being allowed the
    # time something needs. A brute takes a long while to kill and cannot catch
    # you; every other enemy here exists to make sure you never get that while.
    # =========================================================================
    # --- 6 -------------------------------------------------------------------
    # The brute alone in the middle, with the rest of the room arranged to
    # interrupt. The stage 2 pillar layout, deliberately: the player has fought
    # in this shape before and can spend the attention on the new thing.
    Stage(
        name="The Kennels",
        filename="stage6.json",
        width=34,
        height=20,
        hero=(3, 10),
        pillars=[(8, 3, 3, 4), (8, 13, 3, 4), (16, 8, 4, 4), (24, 3, 3, 4), (24, 13, 3, 4)],
        enemies=spawns(
            ("brute", 20, 10),
            ("grunt", 13, 5),
            ("goblin", 13, 15),
            ("rat", 18, 4),
            ("goblin_pup", 18, 16),
            ("rat", 26, 7),
            ("bowman", 31, 5),
            ("goblin_slinger", 31, 15),
        ),
    ),
    # --- 7 -------------------------------------------------------------------
    # Long and shallow, with the cover in two ranks. Chargers get room to build
    # up, which is the point of the shape -- a charge down the length of this is
    # the most readable and most dangerous thing in the act.
    Stage(
        name="The Long Hall",
        filename="stage7.json",
        width=38,
        height=20,
        hero=(3, 10),
        pillars=[(10, 4, 4, 3), (10, 13, 4, 3), (19, 4, 4, 3), (19, 13, 4, 3), (28, 8, 3, 4)],
        enemies=spawns(
            ("grunt", 15, 10),
            ("goblin", 24, 10),
            ("rat", 12, 8),
            ("goblin_pup", 12, 12),
            ("rat", 21, 8),
            ("goblin_pup", 21, 12),
            ("charger", 26, 5),
            ("charger", 26, 15),
            ("bowman", 34, 6),
            ("goblin_slinger", 34, 14),
        ),
    ),
    # --- 8 -------------------------------------------------------------------
    # Two brutes, on opposite sides of a fat central block. They cannot both be
    # avoided by circling one way, which is the question the block is asking.
    Stage(
        name="The Cistern",
        filename="stage8.json",
        width=40,
        height=24,
        hero=(3, 12),
        pillars=[
            (9, 5, 4, 4),
            (9, 15, 4, 4),
            (18, 3, 3, 4),
            (18, 17, 3, 4),
            (26, 9, 5, 5),
            (34, 5, 3, 3),
            (34, 16, 3, 3),
        ],
        enemies=spawns(
            ("brute", 22, 12),
            ("orc", 33, 12),
            ("orc_charger", 31, 12),
            ("grunt", 14, 6),
            ("grunt", 14, 18),
            ("goblin", 24, 4),
            ("goblin", 24, 20),
            ("rat", 19, 8),
            ("rat", 19, 12),
            ("goblin_pup", 19, 16),
            ("bowman", 37, 7),
            ("goblin_slinger", 37, 17),
        ),
    ),
    # --- 9 -------------------------------------------------------------------
    # The act's summary, and the widest arena so far. Everything act II has shown
    # you, in one room, with enough space that none of it can be cornered into
    # being simple.
    Stage(
        name="The Muster",
        filename="stage9.json",
        width=44,
        height=26,
        hero=(3, 13),
        pillars=[
            (10, 5, 4, 4),
            (10, 17, 4, 4),
            (20, 3, 4, 3),
            (20, 11, 5, 4),
            (20, 20, 4, 3),
            (31, 6, 4, 4),
            (31, 16, 4, 4),
            (38, 8, 3, 4),
        ],
        enemies=spawns(
            ("grunt", 16, 13),
            ("goblin", 26, 7),
            ("goblin", 26, 19),
            ("grunt", 36, 13),
            ("rat", 14, 9),
            ("goblin_pup", 14, 17),
            ("rat", 26, 10),
            ("rat", 24, 15),
            ("goblin_pup", 29, 13),
            ("charger", 19, 7),
            ("orc_charger", 19, 19),
            ("orc", 33, 13),
            ("bowman", 41, 6),
            ("goblin_slinger", 41, 20),
        ),
    ),
    # --- 10 -- ACT II BOSS ---------------------------------------------------
    # The Houndmaster is the fast one, so the arena is tight and the pillars are
    # small. Nowhere to settle, and never far enough away to breathe.
    Stage(
        name="The Pit",
        filename="stage10.json",
        kind=RoomKind.BOSS,
        width=34,
        height=22,
        hero=(3, 11),
        pillars=[(10, 5, 3, 3), (10, 14, 3, 3), (22, 5, 3, 3), (22, 14, 3, 3)],
        enemies=spawns(
            ("houndmaster", 26, 11),
            ("rat", 16, 5),
            ("rat", 16, 17),
            ("rat", 29, 8),
        ),
    ),
    # =========================================================================
    # ACT III -- the mage. Ranged pressure that hurts enough to matter, from
    # further out than a bowman. The act is about position: every stage here has
    # something that punishes where you are standing while something else
    # decides where you can stand.
    # =========================================================================
    # --- 11 ------------------------------------------------------------------
    # A single large block in the middle, which is the mage's whole lesson: the
    # thing hurting you at range is behind cover, and getting to it means
    # spending time with everything else.
    Stage(
        name="The Sanctum",
        filename="stage11.json",
        width=40,
        height=24,
        hero=(3, 12),
        pillars=[(9, 4, 4, 4), (9, 16, 4, 4), (18, 9, 5, 6), (28, 4, 4, 4), (28, 16, 4, 4)],
        enemies=spawns(
            ("mage", 36, 6),
            ("mage", 36, 18),
            ("grunt", 15, 12),
            ("grunt", 25, 6),
            ("goblin", 25, 18),
            ("rat", 21, 4),
            ("goblin_pup", 21, 20),
            ("orc_charger", 24, 12),
            ("bowman", 33, 12),
        ),
    ),
    # --- 12 ------------------------------------------------------------------
    # Cover in staggered ranks rather than a ring, so crossing the room is a
    # sequence of short exposures instead of one long one.
    Stage(
        name="The Terraces",
        filename="stage12.json",
        width=44,
        height=26,
        hero=(3, 13),
        pillars=[
            (10, 4, 4, 3),
            (10, 19, 4, 3),
            (17, 10, 4, 3),
            (24, 4, 4, 3),
            (24, 19, 4, 3),
            (31, 10, 4, 3),
            (38, 6, 3, 4),
            (38, 16, 3, 4),
        ],
        enemies=spawns(
            ("mage", 41, 11),
            ("mage", 41, 15),
            ("bowman", 34, 7),
            ("bowman", 34, 19),
            ("grunt", 15, 13),
            ("grunt", 22, 8),
            ("grunt", 22, 18),
            ("grunt", 29, 13),
            ("rat", 19, 5),
            ("rat", 19, 21),
            ("charger", 27, 13),
            ("grunt", 31, 20),
        ),
    ),
    # --- 13 ------------------------------------------------------------------
    # Two brutes and two mages: the slowest things in the game and the ones that
    # do not need to reach you. Kill either pair first and the other punishes it.
    Stage(
        name="The Deep",
        filename="stage13.json",
        width=46,
        height=28,
        hero=(3, 14),
        pillars=[
            (10, 5, 4, 4),
            (10, 19, 4, 4),
            (19, 3, 4, 4),
            (19, 12, 5, 4),
            (19, 21, 4, 4),
            (30, 6, 4, 4),
            (30, 18, 4, 4),
            (39, 12, 3, 4),
        ],
        enemies=spawns(
            ("orc", 26, 14),
            ("grunt", 36, 14),
            ("mage", 43, 8),
            ("mage", 43, 20),
            ("bowman", 35, 11),
            ("goblin_slinger", 35, 17),
            ("orc_charger", 17, 8),
            ("rat", 17, 20),
            ("grunt", 15, 14),
            ("goblin", 28, 6),
            ("goblin", 28, 22),
            ("rat", 24, 10),
            ("goblin_pup", 24, 18),
            ("rat", 32, 14),
        ),
    ),
    # --- 14 ------------------------------------------------------------------
    # The most cover in the game and the most things behind it. Sixteen enemies
    # in a room this size is not a wall -- it is a room you only ever see part of
    # at a time, which is the whole difference.
    Stage(
        name="The Reliquary",
        filename="stage14.json",
        width=48,
        height=28,
        hero=(3, 14),
        pillars=[
            (10, 4, 4, 4),
            (10, 20, 4, 4),
            (20, 4, 4, 4),
            (20, 12, 5, 4),
            (20, 20, 4, 4),
            (31, 4, 4, 4),
            (31, 12, 4, 4),
            (31, 20, 4, 4),
            (41, 8, 3, 4),
            (41, 17, 3, 4),
        ],
        enemies=spawns(
            ("grunt", 16, 14),
            ("grunt", 27, 8),
            ("goblin", 27, 20),
            ("goblin", 37, 14),
            ("rat", 14, 10),
            ("rat", 14, 18),
            ("rat", 25, 4),
            ("goblin_pup", 25, 24),
            ("rat", 35, 10),
            ("goblin_pup", 35, 18),
            ("charger", 18, 8),
            ("orc_charger", 18, 20),
            ("orc", 29, 14),
            ("bowman", 44, 13),
            ("mage", 45, 5),
            ("mage", 45, 23),
        ),
    ),
    # --- 15 -- ACT III BOSS --------------------------------------------------
    # The Effigy is the slowest thing in the game, so it gets the most room. The
    # pillars are far apart and there are only four: this fight is about walking,
    # and walking needs somewhere to walk to.
    #
    # The escorts are grunts, and that is not an aesthetic choice. This stage was
    # two bowmen and was unwinnable on every seed -- not close. A ranged escort
    # on a boss stage never becomes the nearest thing in the room, so it is never
    # the thing you are fighting, so it never dies: it is a damage tax for the
    # length of the fight with no answer available. A grunt walks into the boss's
    # reach and dies to the swing you were making anyway. Every boss stage in the
    # game is escorted by melee for this reason.
    Stage(
        name="The Grove",
        filename="stage15.json",
        kind=RoomKind.BOSS,
        width=38,
        height=26,
        hero=(3, 13),
        pillars=[(11, 5, 3, 4), (11, 17, 3, 4), (25, 5, 3, 4), (25, 17, 3, 4)],
        enemies=spawns(
            ("effigy", 30, 13),
            ("grunt", 19, 5),
            ("grunt", 19, 21),
            ("grunt", 22, 13),
        ),
    ),
    # =========================================================================
    # ACT IV -- no new enemy. Everything the game has, in the largest arenas it
    # has, at whatever health the last fifteen stages left you. Introducing
    # something here would be asking the player to learn at the exact moment they
    # are least able to; the act is a test, not a lesson.
    # =========================================================================
    # --- 16 ------------------------------------------------------------------
    Stage(
        name="The Approach",
        filename="stage16.json",
        width=46,
        height=28,
        hero=(3, 14),
        pillars=[
            (11, 5, 4, 4),
            (11, 19, 4, 4),
            (21, 11, 5, 5),
            (31, 5, 4, 4),
            (31, 19, 4, 4),
            (40, 12, 3, 4),
        ],
        enemies=spawns(
            ("orc", 27, 14),
            ("grunt", 36, 14),
            ("mage", 43, 7),
            ("mage", 43, 21),
            ("bowman", 38, 10),
            ("goblin_slinger", 38, 18),
            ("charger", 18, 9),
            ("orc_charger", 18, 19),
            ("grunt", 16, 14),
            ("goblin", 29, 6),
            ("goblin", 29, 22),
            ("rat", 25, 8),
            ("goblin_pup", 25, 20),
        ),
    ),
    # --- 17 ------------------------------------------------------------------
    # The pillars form two gates rather than a ring -- a gap on the hero's line
    # and solid wall either side of it. Everything funnels, including you.
    Stage(
        name="The Ramparts",
        filename="stage17.json",
        width=48,
        height=28,
        hero=(3, 14),
        pillars=[
            (10, 4, 4, 4),
            (10, 20, 4, 4),
            (19, 10, 4, 3),
            (19, 15, 4, 3),
            (29, 4, 4, 4),
            (29, 20, 4, 4),
            (38, 10, 4, 3),
            (38, 15, 4, 3),
        ],
        enemies=spawns(
            ("grunt", 16, 14),
            ("grunt", 25, 7),
            ("goblin", 25, 21),
            ("goblin", 35, 14),
            ("rat", 14, 9),
            ("rat", 14, 19),
            ("rat", 23, 12),
            ("goblin_pup", 23, 16),
            ("rat", 33, 9),
            ("goblin_pup", 33, 19),
            ("charger", 27, 14),
            ("orc", 31, 14),
            ("bowman", 44, 8),
            ("goblin_slinger", 44, 20),
            ("mage", 45, 14),
        ),
    ),
    # --- 18 ------------------------------------------------------------------
    Stage(
        name="The Vault",
        filename="stage18.json",
        width=46,
        height=28,
        hero=(3, 14),
        pillars=[
            (11, 5, 4, 4),
            (11, 19, 4, 4),
            (20, 5, 4, 4),
            (20, 12, 5, 4),
            (20, 19, 4, 4),
            (30, 5, 4, 4),
            (30, 12, 4, 4),
            (30, 19, 4, 4),
            (39, 9, 3, 4),
        ],
        enemies=spawns(
            ("grunt", 17, 14),
            ("grunt", 27, 8),
            ("goblin", 27, 22),
            ("goblin", 36, 14),
            ("rat", 15, 10),
            ("rat", 15, 18),
            ("rat", 26, 4),
            ("goblin_pup", 26, 24),
            ("rat", 35, 10),
            ("goblin_pup", 35, 18),
            ("charger", 18, 9),
            ("orc_charger", 18, 20),
            ("brute", 28, 14),
            ("orc", 38, 14),
            ("mage", 43, 6),
            ("mage", 43, 22),
        ),
    ),
    # --- 19 ------------------------------------------------------------------
    # The most enemies in the game, and the last stage before the Sovereign --
    # which is the constraint that shapes it. It is fought immediately before a
    # boss and its cost is paid in that boss's fight, so it is dense rather than
    # large: an earlier draft was 52x30, the biggest arena in the game, and the
    # extra ground cost more health than the extra bodies did. Walking is not
    # difficulty. Crowding is.
    Stage(
        name="The Threshold",
        filename="stage19.json",
        width=46,
        height=28,
        hero=(3, 14),
        pillars=[
            (11, 4, 4, 4),
            (11, 20, 4, 4),
            (20, 4, 4, 4),
            (20, 12, 5, 4),
            (20, 20, 4, 4),
            (31, 4, 4, 4),
            (31, 12, 4, 4),
            (31, 20, 4, 4),
            (40, 10, 3, 5),
        ],
        enemies=spawns(
            ("grunt", 17, 14),
            ("grunt", 27, 8),
            ("goblin", 27, 21),
            ("grunt", 37, 14),
            ("goblin", 33, 24),
            ("rat", 15, 9),
            ("rat", 15, 19),
            ("rat", 26, 4),
            ("goblin_pup", 26, 24),
            ("rat", 36, 9),
            ("goblin_pup", 36, 19),
            ("charger", 18, 9),
            ("orc_charger", 18, 20),
            ("orc", 28, 14),
            ("bowman", 44, 8),
            ("goblin_slinger", 44, 20),
            ("mage", 43, 14),
        ),
    ),
    # --- 20 -- FINAL BOSS ----------------------------------------------------
    # Two grunts, and only so the arena is not silent when you walk in. The
    # Sovereign's volley is nine shots across a half-circle, so the pillars are
    # placed for cover rather than for shape -- they are the only answer to it
    # at range, and the fight is built around the player finding that out.
    Stage(
        name="The Sovereign's Hall",
        filename="stage20.json",
        kind=RoomKind.BOSS,
        width=40,
        height=26,
        hero=(3, 13),
        pillars=[
            (11, 4, 4, 5),
            (11, 17, 4, 5),
            (19, 11, 4, 4),
            (27, 4, 4, 5),
            (27, 17, 4, 5),
        ],
        enemies=spawns(
            ("sovereign", 32, 13),
            ("grunt", 20, 6),
            ("grunt", 20, 20),
        ),
    ),
    # =========================================================================
    # ACT V -- the revenant. Everything below this line is fought by an advanced
    # class: the Sovereign is cleared, the fork is taken, and the hero walking
    # into stage 21 is not the one that walked out of stage 20.
    #
    # The revenant is the answer to the one habit twenty stages have taught. A
    # brute can be left alone -- it is slow enough to ignore for as long as you
    # like, and its danger is the attention it costs rather than the damage it
    # does. The revenant has most of a brute's health at a grunt's walking pace,
    # so it cannot be left, and its health has to be spent instead of avoided.
    #
    # Counts restart at 12 rather than continuing from act IV's 17. A new idea
    # deserves room, and this is the first stage of the campaign's second half.
    # =========================================================================
    # --- 21 ------------------------------------------------------------------
    # Three revenants, spread wide, with the ordinary roster thinned out around
    # them so the new thing is legible. The two bowmen are parked at the far end
    # deliberately: crossing the room to deal with them is exactly the errand a
    # revenant is designed to make expensive.
    Stage(
        name="The Descent",
        filename="stage21.json",
        width=46,
        height=28,
        hero=(3, 14),
        pillars=[
            (10, 4, 4, 4),
            (10, 20, 4, 4),
            (19, 12, 4, 4),
            (28, 4, 4, 4),
            (28, 20, 4, 4),
            (37, 12, 3, 4),
        ],
        enemies=spawns(
            ("revenant", 16, 8),
            ("beastman", 16, 20),
            ("beastman", 25, 14),
            ("grunt", 21, 5),
            ("grunt", 21, 23),
            ("grunt", 34, 9),
            ("grunt", 34, 19),
            ("rat", 15, 14),
            ("rat", 24, 6),
            ("rat", 24, 22),
            ("bowman", 42, 8),
            ("bowman", 42, 20),
        ),
    ),
    # --- 22 ------------------------------------------------------------------
    # Chargers return alongside the revenants, top and bottom in the open lanes
    # where their telegraph is readable. The point of the pairing: a charger is
    # answered by moving, and a revenant is what makes moving cost something.
    Stage(
        name="The Ossuary",
        filename="stage22.json",
        width=48,
        height=28,
        hero=(3, 14),
        pillars=[
            (9, 3, 4, 5),
            (9, 20, 4, 5),
            (18, 11, 4, 5),
            (27, 3, 4, 5),
            (27, 20, 4, 5),
            (36, 11, 4, 5),
            (42, 4, 3, 4),
        ],
        enemies=spawns(
            ("revenant", 15, 9),
            ("beastman", 15, 19),
            ("beastman", 24, 14),
            ("grunt", 20, 5),
            ("grunt", 20, 23),
            ("grunt", 33, 8),
            ("grunt", 33, 20),
            ("rat", 14, 14),
            ("rat", 23, 9),
            ("rat", 23, 19),
            ("rat", 31, 14),
            ("charger", 25, 3),
            ("charger", 25, 25),
            ("bowman", 45, 14),
        ),
    ),
    # --- 23 ------------------------------------------------------------------
    # A fourth revenant and the act's first mage. Two rows of pillars down the
    # middle, so the mage at the far end has something to hide behind and the
    # player has something to break line of sight with -- the same pillar doing
    # both jobs is what makes the walk down this room a decision.
    Stage(
        name="The Wake",
        filename="stage23.json",
        width=48,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (19, 12, 5, 5),
            (29, 4, 4, 5),
            (29, 21, 4, 5),
            (38, 12, 4, 5),
            (43, 4, 3, 4),
        ],
        enemies=spawns(
            ("revenant", 16, 10),
            ("beastman", 16, 20),
            ("revenant", 26, 15),
            ("beastman", 35, 15),
            ("grunt", 21, 6),
            ("grunt", 21, 24),
            ("grunt", 34, 9),
            ("grunt", 34, 22),
            ("rat", 15, 15),
            ("rat", 25, 7),
            ("rat", 25, 23),
            ("charger", 27, 3),
            ("charger", 27, 27),
            ("grunt", 37, 10),
            ("bowman", 45, 20),
        ),
    ),
    # --- 24 ------------------------------------------------------------------
    # The act's largest, and the brute's reappearance -- deliberately at the far
    # end, behind everything else. A brute you can walk away from and a revenant
    # you cannot, in the same room, is the whole act stated once.
    Stage(
        name="The Long Vigil",
        filename="stage24.json",
        width=50,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (19, 12, 4, 5),
            (27, 4, 4, 5),
            (27, 21, 4, 5),
            (35, 12, 4, 5),
            (43, 4, 4, 5),
            (43, 21, 4, 5),
        ],
        enemies=spawns(
            ("revenant", 16, 10),
            ("beastman", 16, 20),
            ("revenant", 24, 15),
            ("beastman", 33, 15),
            ("grunt", 21, 6),
            ("grunt", 21, 24),
            ("grunt", 32, 10),
            ("grunt", 32, 20),
            ("grunt", 41, 15),
            ("rat", 15, 15),
            ("rat", 25, 7),
            ("rat", 25, 23),
            ("rat", 40, 8),
            ("charger", 24, 3),
            ("charger", 24, 27),
            ("brute", 45, 15),
            ("mage", 39, 10),
        ),
    ),
    # --- 25 -- ACT V BOSS ----------------------------------------------------
    # The Herald: the Houndmaster's shape at the Sovereign's reach. Quick body,
    # short tells, a seven-shot peal.
    #
    # Arena and escorts follow the act I template on purpose. This is the first
    # fight after the fork, and everything unfamiliar about it should be in the
    # player's own hands rather than in the room -- a class they have used for
    # five minutes against a pattern they have read four times.
    #
    # Escorts are melee, as on every boss stage in the game. See stage 15.
    Stage(
        name="The Herald's Gate",
        filename="stage25.json",
        kind=RoomKind.BOSS,
        width=40,
        height=26,
        hero=(3, 13),
        pillars=[(11, 4, 4, 5), (11, 17, 4, 5), (19, 11, 4, 4), (27, 4, 4, 5), (27, 17, 4, 5)],
        enemies=spawns(
            ("herald", 32, 13),
            ("grunt", 20, 6),
            ("grunt", 20, 20),
            ("revenant", 24, 13),
        ),
    ),
    # =========================================================================
    # ACT VI -- the stalker. A charger that commits from 210 where a charger
    # commits from 150, with a 26-tick tell against the charger's 32.
    #
    # It is here because of what the fork handed the player. An advanced class's
    # heavy and ultimate are the longest commitments the hero has ever had, and
    # a room with nothing in it that punishes spending one at the wrong moment
    # makes them free. The stalker is that punishment, and the act is built to
    # make sure it is never the only thing asking for attention.
    # =========================================================================
    # --- 26 ------------------------------------------------------------------
    # Deliberately open through the middle. The stalker's tell is short enough
    # that a first meeting in a cluttered room would read as being hit from
    # nowhere -- so it arrives where it can be seen coming, and the act tightens
    # the arena from here.
    Stage(
        name="The Snare",
        filename="stage26.json",
        width=46,
        height=28,
        hero=(3, 14),
        pillars=[(11, 4, 4, 4), (11, 20, 4, 4), (30, 4, 4, 4), (30, 20, 4, 4), (20, 12, 5, 4)],
        enemies=spawns(
            ("stalker", 18, 8),
            ("beastman_stalker", 18, 20),
            ("beastman_stalker", 27, 14),
            ("grunt", 22, 6),
            ("grunt", 22, 22),
            ("grunt", 36, 9),
            ("grunt", 36, 19),
            ("rat", 17, 14),
            ("rat", 26, 7),
            ("rat", 26, 21),
            ("revenant", 34, 14),
            ("beastman", 40, 10),
            ("bowman", 43, 20),
        ),
    ),
    # --- 27 ------------------------------------------------------------------
    # The same three stalkers in a corridor of pillars, which is the version of
    # the fight the last stage was preparing for: a committed dash is far worse
    # when the room decides where you can dodge to.
    Stage(
        name="The Culverts",
        filename="stage27.json",
        width=48,
        height=28,
        hero=(3, 14),
        pillars=[
            (9, 3, 4, 5),
            (9, 20, 4, 5),
            (18, 11, 4, 5),
            (27, 3, 4, 5),
            (27, 20, 4, 5),
            (36, 11, 4, 5),
            (42, 20, 3, 4),
        ],
        enemies=spawns(
            ("stalker", 15, 9),
            ("beastman_stalker", 24, 14),
            ("beastman", 21, 7),
            ("grunt", 33, 14),
            ("grunt", 23, 4),
            ("grunt", 23, 25),
            ("grunt", 34, 8),
            ("grunt", 34, 20),
            ("grunt", 16, 18),
            ("grunt", 26, 10),
            ("rat", 14, 14),
            ("rat", 25, 18),
            ("rat", 31, 9),
            ("grunt", 40, 8),
            ("grunt", 40, 18),
        ),
    ),
    # --- 28 ------------------------------------------------------------------
    # Eight pillars, four rats and a brute at the back. The stalkers are spread
    # rather than grouped: three arriving together is one decision, three
    # arriving from three places is three.
    Stage(
        name="The Gallows Walk",
        filename="stage28.json",
        width=50,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (19, 12, 4, 5),
            (28, 4, 4, 5),
            (28, 21, 4, 5),
            (37, 12, 4, 5),
            (44, 4, 4, 5),
            (44, 21, 4, 5),
        ],
        enemies=spawns(
            ("stalker", 16, 10),
            ("beastman_stalker", 16, 20),
            ("beastman_stalker", 25, 15),
            ("revenant", 23, 6),
            ("beastman", 23, 24),
            ("beastman", 34, 15),
            ("grunt", 21, 6),
            ("grunt", 21, 24),
            ("grunt", 33, 9),
            ("grunt", 33, 21),
            ("rat", 15, 15),
            ("rat", 26, 8),
            ("rat", 26, 22),
            ("rat", 42, 15),
            ("brute", 41, 10),
            ("mage", 41, 9),
        ),
    ),
    # --- 29 ------------------------------------------------------------------
    # The act's largest: four stalkers, and the last stage before the slowest
    # boss in the game. Ends on eighteen, which is the most the campaign has
    # asked for anywhere.
    Stage(
        name="The Black Ford",
        filename="stage29.json",
        width=50,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (18, 12, 4, 5),
            (26, 4, 4, 5),
            (26, 21, 4, 5),
            (34, 12, 4, 5),
            (42, 4, 4, 5),
            (42, 21, 4, 5),
        ],
        enemies=spawns(
            ("stalker", 16, 10),
            ("beastman_stalker", 16, 20),
            ("rat", 24, 15),
            ("revenant", 22, 7),
            ("beastman", 40, 15),
            ("grunt", 20, 6),
            ("grunt", 20, 24),
            ("grunt", 31, 9),
            ("grunt", 31, 21),
            ("grunt", 46, 15),
            ("rat", 15, 15),
            ("rat", 23, 11),
            ("rat", 23, 19),
            ("rat", 39, 8),
            ("rat", 33, 20),
            ("rat", 33, 10),
            ("charger", 30, 6),
            ("grunt", 38, 10),
        ),
    ),
    # --- 30 -- ACT VI BOSS ---------------------------------------------------
    # The Gaoler: the slowest body in the game swinging the longest reach in it.
    # A 50px chain across 240 degrees denies more floor than anything else, so
    # the arena is wide and the pillars are pushed out to the edges -- there has
    # to be somewhere to be that is not inside the swing.
    #
    # Escorts are melee. See stage 15.
    Stage(
        name="The Gaoler's Yard",
        filename="stage30.json",
        kind=RoomKind.BOSS,
        width=42,
        height=28,
        hero=(3, 14),
        pillars=[(12, 4, 4, 5), (12, 19, 4, 5), (21, 12, 4, 4), (30, 4, 4, 5), (30, 19, 4, 5)],
        enemies=spawns(
            ("gaoler", 34, 14),
            ("grunt", 22, 6),
            ("grunt", 22, 21),
            ("revenant", 26, 14),
        ),
    ),
    # =========================================================================
    # ACT VII -- no new enemy. Both of act V's and act VI's ideas in the same
    # rooms, which is the combination the two of them were separated to teach.
    #
    # The same shape act IV has, and for the same reason: an act that introduced
    # something here would be asking the player to learn at the point they are
    # least able to. Two acts of new creatures is enough for one campaign half.
    # =========================================================================
    # --- 31 ------------------------------------------------------------------
    Stage(
        name="The Antechamber",
        filename="stage31.json",
        width=48,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (19, 12, 4, 5),
            (28, 4, 4, 5),
            (28, 21, 4, 5),
            (37, 12, 4, 5),
            (43, 5, 3, 4),
        ],
        enemies=spawns(
            ("revenant", 16, 10),
            ("beastman", 25, 15),
            ("stalker", 23, 7),
            ("beastman_stalker", 34, 15),
            ("mage", 35, 8),
            ("imp", 35, 22),
            ("grunt", 21, 4),
            ("grunt", 21, 26),
            ("grunt", 33, 9),
            ("grunt", 17, 20),
            ("grunt", 27, 17),
            ("rat", 15, 15),
            ("rat", 30, 12),
            ("bowman", 41, 15),
        ),
    ),
    # --- 32 ------------------------------------------------------------------
    # Two mages at the very back, behind eight pillars and everything else in
    # the room. The act's recurring problem: the things worth killing first are
    # the things furthest away, and the room is full of reasons not to cross it.
    Stage(
        name="The Nave",
        filename="stage32.json",
        width=50,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (18, 12, 4, 5),
            (26, 4, 4, 5),
            (26, 21, 4, 5),
            (34, 12, 4, 5),
            (42, 4, 4, 5),
            (42, 21, 4, 5),
        ],
        enemies=spawns(
            ("revenant", 16, 10),
            ("beastman", 24, 15),
            ("stalker", 22, 7),
            ("beastman_stalker", 32, 15),
            ("grunt", 20, 6),
            ("grunt", 20, 24),
            ("grunt", 31, 9),
            ("grunt", 31, 21),
            ("rat", 15, 15),
            ("rat", 23, 12),
            ("rat", 23, 18),
            ("rat", 33, 11),
            ("rat", 33, 19),
            ("imp", 38, 9),
            ("rat", 38, 21),
            ("brute", 40, 15),
        ),
    ),
    # --- 33 ------------------------------------------------------------------
    Stage(
        name="The Undercroft",
        filename="stage33.json",
        width=50,
        height=30,
        hero=(3, 15),
        pillars=[
            (9, 4, 4, 5),
            (9, 21, 4, 5),
            (17, 12, 4, 5),
            (25, 4, 4, 5),
            (25, 21, 4, 5),
            (33, 12, 4, 5),
            (41, 4, 4, 5),
            (41, 21, 4, 5),
        ],
        enemies=spawns(
            ("revenant", 15, 10),
            ("revenant", 23, 15),
            ("beastman", 31, 15),
            ("stalker", 21, 7),
            ("beastman_stalker", 39, 15),
            ("grunt", 19, 6),
            ("grunt", 19, 24),
            ("grunt", 30, 9),
            ("grunt", 30, 21),
            ("grunt", 15, 20),
            ("grunt", 37, 10),
            ("rat", 14, 15),
            ("rat", 22, 12),
            ("rat", 22, 18),
            ("rat", 38, 8),
            ("grunt", 37, 9),
            ("hellhound", 29, 6),
        ),
    ),
    # --- 34 ------------------------------------------------------------------
    # Nineteen, the most in the campaign so far, in the longest room in it. The
    # two stalkers on the top and bottom edges have the whole length of the
    # arena to build up in, which is the worst version of that enemy.
    Stage(
        name="The Tribune",
        filename="stage34.json",
        width=52,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (18, 12, 4, 5),
            (26, 4, 4, 5),
            (26, 21, 4, 5),
            (34, 12, 4, 5),
            (42, 4, 4, 5),
            (42, 21, 4, 5),
            (48, 12, 3, 4),
        ],
        enemies=spawns(
            ("revenant", 16, 10),
            ("revenant", 24, 15),
            ("beastman", 32, 15),
            ("stalker", 22, 7),
            ("stalker", 30, 6),
            ("beastman_stalker", 30, 24),
            ("grunt", 20, 6),
            ("grunt", 20, 24),
            ("grunt", 31, 9),
            ("grunt", 31, 21),
            ("grunt", 40, 15),
            ("rat", 15, 15),
            ("rat", 23, 12),
            ("rat", 23, 18),
            ("rat", 39, 8),
            ("rat", 33, 20),
            ("rat", 17, 20),
            ("brute", 46, 15),
            ("imp", 44, 15),
        ),
    ),
    # --- 35 -- ACT VII BOSS --------------------------------------------------
    # The Choir: eleven shots across 130 degrees from 165 away, and the weakest
    # of the eight bosses up close. The fight is closing the distance, so this
    # is the most heavily pillared arena in the game -- eight of them in two
    # staggered rows, so there is always a next piece of cover rather than one
    # sprint through an open fan.
    #
    # Least health of the four late bosses on purpose: a long fight at range
    # against this one is the failure state rather than the fight.
    #
    # Escorts are melee. See stage 15.
    Stage(
        name="The Choir Loft",
        filename="stage35.json",
        kind=RoomKind.BOSS,
        width=44,
        height=28,
        hero=(3, 14),
        pillars=[
            (11, 4, 3, 4),
            (11, 19, 3, 4),
            (17, 11, 3, 4),
            (23, 4, 3, 4),
            (23, 19, 3, 4),
            (29, 11, 3, 4),
            (35, 4, 3, 4),
            (35, 19, 3, 4),
        ],
        enemies=spawns(
            ("choir", 38, 14),
            ("grunt", 21, 9),
            ("grunt", 21, 18),
            ("revenant", 27, 14),
        ),
    ),
    # =========================================================================
    # ACT VIII -- everything the game has, in the largest arenas it has, at
    # whatever health the last thirty-five stages left you. The same argument
    # act IV makes, one campaign half later.
    # =========================================================================
    # --- 36 ------------------------------------------------------------------
    Stage(
        name="The Outer Ward",
        filename="stage36.json",
        width=50,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (18, 12, 4, 5),
            (26, 4, 4, 5),
            (26, 21, 4, 5),
            (34, 12, 4, 5),
            (42, 4, 4, 5),
            (42, 21, 4, 5),
        ],
        enemies=spawns(
            ("revenant", 16, 10),
            ("beastman", 24, 15),
            ("stalker", 22, 7),
            ("beastman_stalker", 32, 15),
            ("grunt", 20, 6),
            ("grunt", 20, 24),
            ("grunt", 31, 9),
            ("grunt", 17, 19),
            ("grunt", 25, 12),
            ("rat", 15, 15),
            ("rat", 23, 12),
            ("rat", 23, 18),
            ("brute", 40, 15),
            ("imp", 38, 10),
            ("hellhound", 30, 21),
        ),
    ),
    # --- 37 ------------------------------------------------------------------
    Stage(
        name="The Inner Ward",
        filename="stage37.json",
        width=52,
        height=30,
        hero=(3, 15),
        pillars=[
            (10, 4, 4, 5),
            (10, 21, 4, 5),
            (18, 12, 4, 5),
            (26, 4, 4, 5),
            (26, 21, 4, 5),
            (34, 12, 4, 5),
            (42, 4, 4, 5),
            (42, 21, 4, 5),
            (48, 12, 3, 4),
        ],
        enemies=spawns(
            ("revenant", 16, 10),
            ("revenant", 24, 15),
            ("beastman", 32, 15),
            ("stalker", 22, 7),
            ("beastman_stalker", 40, 15),
            ("grunt", 20, 6),
            ("grunt", 20, 24),
            ("grunt", 31, 9),
            ("grunt", 31, 21),
            ("rat", 15, 15),
            ("rat", 23, 12),
            ("rat", 23, 18),
            ("rat", 33, 20),
            ("rat", 17, 20),
            ("brute", 46, 15),
            ("imp", 44, 15),
            ("charger", 30, 6),
        ),
    ),
    # --- 38 ------------------------------------------------------------------
    # The tallest arena in the game. Four stalkers, two of them on the long
    # edges where they have the whole room to run at you through.
    Stage(
        name="The Hollow Stair",
        filename="stage38.json",
        width=52,
        height=32,
        hero=(3, 16),
        pillars=[
            (10, 4, 4, 5),
            (10, 23, 4, 5),
            (18, 13, 4, 5),
            (26, 4, 4, 5),
            (26, 23, 4, 5),
            (34, 13, 4, 5),
            (42, 4, 4, 5),
            (42, 23, 4, 5),
            (48, 13, 3, 4),
        ],
        enemies=spawns(
            ("revenant", 16, 11),
            ("revenant", 24, 16),
            ("beastman", 32, 16),
            ("stalker", 22, 8),
            ("stalker", 30, 6),
            ("beastman_stalker", 30, 26),
            ("grunt", 20, 6),
            ("grunt", 20, 26),
            ("grunt", 31, 10),
            ("grunt", 31, 22),
            ("grunt", 16, 21),
            ("grunt", 25, 13),
            ("rat", 15, 16),
            ("rat", 23, 13),
            ("rat", 23, 19),
            ("brute", 40, 16),
            ("imp", 38, 9),
            ("grunt", 38, 23),
        ),
    ),
    # --- 39 ------------------------------------------------------------------
    # Twenty enemies, the most the campaign ever asks for, and the last stage
    # before the throne. Everything in the game is in this room.
    Stage(
        name="The King's Approach",
        filename="stage39.json",
        width=52,
        height=32,
        hero=(3, 16),
        pillars=[
            (10, 4, 4, 5),
            (10, 23, 4, 5),
            (18, 13, 4, 5),
            (26, 4, 4, 5),
            (26, 23, 4, 5),
            (34, 13, 4, 5),
            (42, 4, 4, 5),
            (42, 23, 4, 5),
        ],
        enemies=spawns(
            ("revenant", 16, 11),
            ("revenant", 24, 16),
            ("beastman", 32, 16),
            ("stalker", 22, 8),
            ("stalker", 30, 6),
            ("beastman_stalker", 30, 26),
            ("grunt", 20, 6),
            ("grunt", 20, 26),
            ("grunt", 31, 10),
            ("grunt", 31, 22),
            ("grunt", 40, 16),
            ("grunt", 16, 21),
            ("rat", 15, 16),
            ("rat", 23, 13),
            ("rat", 23, 19),
            ("rat", 39, 9),
            ("rat", 33, 21),
            ("brute", 47, 16),
            ("grunt", 38, 10),
            ("hellhound", 38, 24),
        ),
    ),
    # --- 40 -- FINAL BOSS ----------------------------------------------------
    # The Hollow King, and the same arena logic as the Sovereign's Hall twenty
    # stages earlier: pillars placed for cover rather than for shape, because
    # ten shots across 120 degrees have no answer at range except a wall.
    #
    # A revenant among the escorts rather than a third grunt. The Sovereign's
    # two grunts were there so the room was not silent; this one is the last
    # fight of a forty-stage run and gets something that has to be dealt with.
    #
    # Escorts are melee. See stage 15.
    Stage(
        name="The Hollow Throne",
        filename="stage40.json",
        kind=RoomKind.BOSS,
        width=42,
        height=28,
        hero=(3, 14),
        pillars=[(12, 4, 4, 5), (12, 19, 4, 5), (20, 11, 4, 4), (28, 4, 4, 5), (28, 19, 4, 5)],
        enemies=spawns(
            ("hollow_king", 34, 14),
            ("grunt", 21, 6),
            ("grunt", 21, 21),
            ("revenant", 25, 14),
        ),
    ),
]

CAMPAIGN_NAME = "Hack and Slash"


def build_campaign() -> Campaign:
    return Campaign(
        name=CAMPAIGN_NAME, stages=tuple(stage.build() for stage in STAGES)
    )


def main() -> int:
    campaign = build_campaign()

    problems = campaign.problems()
    if problems:
        # Refuse to write a campaign that cannot be played. A bad stage on disk
        # is worse than none: it fails at run time, far from the mistake, and
        # possibly minutes into somebody's run.
        print("campaign is not playable:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    for stage, level in zip(STAGES, campaign.stages):
        level_io.save(level, config.LEVELS_DIR / stage.filename)

    manifest = config.LEVELS_DIR / "campaign.json"
    campaign_io.save(campaign, manifest, [s.filename for s in STAGES])

    print(f"wrote {manifest.relative_to(ROOT)}  ({len(STAGES)} stages)")
    for index, (stage, level) in enumerate(zip(STAGES, campaign.stages), start=1):
        kinds: dict[str, int] = {}
        for spawn in level.enemy_spawns:
            kinds[spawn.type_id] = kinds.get(spawn.type_id, 0) + 1
        mix = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
        print(
            f"  {index}. {stage.name:<14} {level.width:>2}x{level.height:<2} "
            f"{len(level.enemy_spawns)} enemies  ({mix})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
