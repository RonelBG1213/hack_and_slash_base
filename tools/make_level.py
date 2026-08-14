"""Writes the twenty stages and the campaign manifest that orders them.

There is no level editor -- that was a deliberate scope cut. This script is the
compromise: a stage is described here as a size, a list of pillar rectangles and
a list of enemies, which is far easier to get right than counting characters in a
wall of ASCII. The output is plain readable JSON, so a small tweak can be made in
the file directly without coming back here.

    python tools/make_level.py

**The shape.** Four acts of five. Each act opens by introducing one enemy, spends
three stages combining it with what came before, and ends on a boss:

    act I    1-4   grunt, bowman, charger, rat        5   The Warden
    act II   6-9   the brute                         10   The Houndmaster
    act III  11-14 the mage                          15   The Effigy
    act IV   16-19 everything at once                20   The Sovereign

Enemy counts rise inside an act and reset at the start of the next one, because
an act opens on a new idea and a new idea deserves room. That is why the
difficulty test checks the curve per act rather than across the campaign.

Stages 1-3 are the originals and are kept at their original indices. That is not
sentiment: stage 3 ("The Gauntlet") is the arena the whole game was first tuned
around and the only stage whose numbers are on record, which makes it the one
thing the balance harness can be checked against. Moving it would throw that
reference away.

Health carries between stages, so these are not twenty independent fights -- they
are one run, and stage 20 is fought at whatever you have left.
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
from hack_and_slash.core.level import FLOOR, WALL, EnemySpawn, Level  # noqa: E402


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
    """

    name: str
    filename: str
    width: int
    height: int
    hero: tuple[int, int]
    enemies: list[EnemySpawn]
    pillars: list[tuple[int, int, int, int]] = field(default_factory=list)

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
            ("grunt", 13, 4),
            ("grunt", 13, 15),
            ("grunt", 21, 10),
            ("charger", 20, 4),
            ("bowman", 30, 5),
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
            ("rat", 14, 5),
            ("rat", 14, 17),
            ("rat", 20, 6),
            ("rat", 20, 16),
            ("rat", 27, 8),
            ("rat", 27, 14),
            ("rat", 31, 11),
            ("grunt", 22, 11),
            ("grunt", 30, 5),
            ("grunt", 30, 17),
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
            ("grunt", 13, 15),
            ("rat", 18, 4),
            ("rat", 18, 16),
            ("rat", 26, 7),
            ("bowman", 31, 5),
            ("bowman", 31, 15),
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
            ("grunt", 24, 10),
            ("rat", 12, 8),
            ("rat", 12, 12),
            ("rat", 21, 8),
            ("rat", 21, 12),
            ("charger", 26, 5),
            ("charger", 26, 15),
            ("bowman", 34, 6),
            ("bowman", 34, 14),
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
            ("brute", 33, 12),
            ("charger", 31, 12),
            ("grunt", 14, 6),
            ("grunt", 14, 18),
            ("grunt", 24, 4),
            ("grunt", 24, 20),
            ("rat", 19, 8),
            ("rat", 19, 12),
            ("rat", 19, 16),
            ("bowman", 37, 7),
            ("bowman", 37, 17),
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
            ("grunt", 26, 7),
            ("grunt", 26, 19),
            ("grunt", 36, 13),
            ("rat", 14, 9),
            ("rat", 14, 17),
            ("rat", 26, 10),
            ("rat", 24, 15),
            ("rat", 29, 13),
            ("charger", 19, 7),
            ("charger", 19, 19),
            ("brute", 33, 13),
            ("bowman", 41, 6),
            ("bowman", 41, 20),
        ),
    ),
    # --- 10 -- ACT II BOSS ---------------------------------------------------
    # The Houndmaster is the fast one, so the arena is tight and the pillars are
    # small. Nowhere to settle, and never far enough away to breathe.
    Stage(
        name="The Pit",
        filename="stage10.json",
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
            ("grunt", 25, 18),
            ("rat", 21, 4),
            ("rat", 21, 20),
            ("charger", 24, 12),
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
            ("brute", 26, 14),
            ("grunt", 36, 14),
            ("mage", 43, 8),
            ("mage", 43, 20),
            ("bowman", 35, 11),
            ("bowman", 35, 17),
            ("charger", 17, 8),
            ("rat", 17, 20),
            ("grunt", 15, 14),
            ("grunt", 28, 6),
            ("grunt", 28, 22),
            ("rat", 24, 10),
            ("rat", 24, 18),
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
            ("grunt", 27, 20),
            ("grunt", 37, 14),
            ("rat", 14, 10),
            ("rat", 14, 18),
            ("rat", 25, 4),
            ("rat", 25, 24),
            ("rat", 35, 10),
            ("rat", 35, 18),
            ("charger", 18, 8),
            ("charger", 18, 20),
            ("brute", 29, 14),
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
            ("brute", 27, 14),
            ("grunt", 36, 14),
            ("mage", 43, 7),
            ("mage", 43, 21),
            ("bowman", 38, 10),
            ("bowman", 38, 18),
            ("charger", 18, 9),
            ("charger", 18, 19),
            ("grunt", 16, 14),
            ("grunt", 29, 6),
            ("grunt", 29, 22),
            ("rat", 25, 8),
            ("rat", 25, 20),
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
            ("grunt", 25, 21),
            ("grunt", 35, 14),
            ("rat", 14, 9),
            ("rat", 14, 19),
            ("rat", 23, 12),
            ("rat", 23, 16),
            ("rat", 33, 9),
            ("rat", 33, 19),
            ("charger", 27, 14),
            ("brute", 31, 14),
            ("bowman", 44, 8),
            ("bowman", 44, 20),
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
            ("grunt", 27, 22),
            ("grunt", 36, 14),
            ("rat", 15, 10),
            ("rat", 15, 18),
            ("rat", 26, 4),
            ("rat", 26, 24),
            ("rat", 35, 10),
            ("rat", 35, 18),
            ("charger", 18, 9),
            ("charger", 18, 20),
            ("brute", 28, 14),
            ("brute", 38, 14),
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
            ("grunt", 27, 21),
            ("grunt", 37, 14),
            ("grunt", 33, 24),
            ("rat", 15, 9),
            ("rat", 15, 19),
            ("rat", 26, 4),
            ("rat", 26, 24),
            ("rat", 36, 9),
            ("rat", 36, 19),
            ("charger", 18, 9),
            ("charger", 18, 20),
            ("brute", 28, 14),
            ("bowman", 44, 8),
            ("bowman", 44, 20),
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
