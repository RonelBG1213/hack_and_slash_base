"""Writes the reward-room template that sits between the arenas.

    python tools/make_rooms.py

One file, `levels/rooms/chamber.json`, and `game/rooms.py` stamps a kind and a
set of doors onto a copy of it. One template rather than four because the four
reward rooms differ by exactly one prop -- the fountain, stall, shrine or chest
at the centre -- and four near-identical files would be four places for a layout
fix to be applied three times.

**The layout is not decorative, and the rule behind it is the same one
`make_level.py` spends a page on: nothing in this game paths around walls.**

In an arena a blocked lane costs a slow fight -- the player walks over and
fetches the stranded grunt. Here there is nothing to kill, so the room ends only
when the hero reaches a door, and a wall between the entrance and that door is a
run that cannot continue. So the chamber is an open box with no pillars at all,
and `Level.problems()` re-checks the straight line from the entrance to every
prop rather than trusting this file to have got it right.

Small on purpose: the whole room is on screen at once and there is nothing to
explore. A reward room is a beat, not a level.

**But not smaller than the viewport.** 26x14 tiles is 416x224 pixels against a
384x188 view, so the camera has something to clamp against on both axes. Drafted
at 22 wide -- 352 pixels -- and the arena did not reach the edge of the screen:
the renderer filled the remainder with letterbox, which reads as a rendering
fault rather than as a small room. `tools/make_level.py` has a test demanding
every *arena* is bigger than a screen; this is the same constraint arrived at
from the other end, and the reason is worth writing down rather than leaving as
two numbers that happen to work.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hack_and_slash import config  # noqa: E402
from hack_and_slash.core import level_io  # noqa: E402
from hack_and_slash.core.level import (  # noqa: E402
    FLOOR,
    WALL,
    Level,
    Prop,
    PropKind,
    RoomKind,
)

WIDTH = 26
HEIGHT = 14

#: West side, on the middle row. Where the arena's exit puts you.
ENTRANCE = (3, 7)

#: Dead centre, so it is the first thing on the screen and on the line to every
#: door. A reward you can miss by walking past it is a reward that gets missed.
REWARD_TILE = (13, 7)

#: East wall, spread over the full height so three doors are three places rather
#: than one cluster. Inside the wall ring, never on it -- a door tile has to be
#: walkable or the hero stops a pixel short of the thing that ends the room.
#:
#: Order is content: top, middle, bottom is the order `rooms.offer` fills and the
#: order the reference bot reads, and door 0 is the one it always takes.
#:
#: **The middle door is in line with the fixture, and door 0 is not.** That is
#: load-bearing rather than incidental: the reference bot walks straight at the
#: door it takes and must not use what is in the middle on the way, or it starts
#: measuring its own perturbation -- see `Autoplay._in_a_room`. The top and
#: bottom doors clear the centre by 32px against a 14.5px reach.
#: `test_the_reference_bot_walks_past_every_fixture` fails if this moves.
DOOR_TILES = ((23, 3), (23, 7), (23, 11))

#: What the template carries before `rooms.chamber` stamps it. Any valid
#: combination will do -- the point is that the file on disk is a level that
#: loads, validates and could be played, rather than a fragment with holes in
#: it that only means something once code has filled them in.
TEMPLATE_KIND = RoomKind.TREASURE
TEMPLATE_DOORS = (RoomKind.FOUNTAIN, RoomKind.SHOP, RoomKind.SHRINE)


def build() -> Level:
    grid = [[FLOOR] * WIDTH for _ in range(HEIGHT)]
    for x in range(WIDTH):
        grid[0][x] = WALL
        grid[HEIGHT - 1][x] = WALL
    for y in range(HEIGHT):
        grid[y][0] = WALL
        grid[y][WIDTH - 1] = WALL

    props = [Prop(PropKind.CHEST, REWARD_TILE)]
    props += [
        Prop(PropKind.DOOR, tile, leads_to=kind)
        for tile, kind in zip(DOOR_TILES, TEMPLATE_DOORS)
    ]

    return Level(
        name="Chamber",
        rows=tuple("".join(row) for row in grid),
        hero_spawn=ENTRANCE,
        enemy_spawns=(),
        tile=config.TILE,
        kind=TEMPLATE_KIND,
        props=tuple(props),
    )


def main() -> int:
    level = build()
    problems = level.problems()
    if problems:
        # Refused rather than written. A broken chamber is a run that strands
        # the player with no enemies to kill and no door to reach, which is the
        # one failure in this game with no way out of it.
        for problem in problems:
            print(f"  ! {problem}")
        return 1

    path = config.LEVELS_DIR / "rooms" / "chamber.json"
    level_io.save(level, path)
    print(f"wrote {path.relative_to(ROOT)}  ({WIDTH}x{HEIGHT}, {len(level.props)} props)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
