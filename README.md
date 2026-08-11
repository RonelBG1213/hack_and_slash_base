# Hack and Slash

A top-down twin-stick arena brawler. Move with WASD, aim with the mouse, click
to swing, roll to survive. Clear the arena or die in it.

Python 3.14 + pygame-ce. No engine, no build step.

## Why Python

This genre ships on Unity and C#. Python is not a shipping language for it, and
this is not pretending otherwise — it is here to get the *combat design* right
cheaply, where changing a number and feeling the result takes seconds.

That only pays off if the design survives the move to a real engine, so the game
logic is kept engine-agnostic: `core/` and `game/` are plain arithmetic on plain
data and never import pygame. `tests/test_architecture.py` fails the build if
that stops being true. Porting means rewriting `render/` and `scenes/`, not the
game.

## The fight

You are faster than everything you fight. That is the deal the whole arena rests
on — in open ground you can always break away, so taking a hit is a decision you
made rather than something the arena did to you. Boxed in by five things at once,
you cannot, and that is the arena working as intended.

Every attack in the game runs the same three phases:

```
WINDUP  ->  ACTIVE  ->  RECOVERY
 tell      hitbox      punishable
```

Only `ACTIVE` can hit anything. **Windup** is the tell — it is what makes an
attack readable, and it is the first number to change when something feels
unfair. **Recovery** is the price of missing: whiffing into empty air is a
mistake, not a free action.

| Enemy | What it asks you |
| --- | --- |
| **Grunt** | Can you make space? Walks in and swings. |
| **Charger** | Are you standing in a line with it? Long telegraph, committed dash — sidestep it or eat it. |
| **Archer** | Are you standing still in the open? Keeps its distance and needs line of sight, so pillars are the answer. |

Your dodge roll is invulnerable from its very first frame, and the
invulnerability ends *before* the roll does — so rolling at the right moment
works and rolling constantly does not.

## Setup

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt     # macOS / Linux
```

The art and the arena are both generated, not committed. Build them once:

```sh
.venv/Scripts/python tools/gen_art.py       # assets/sprites.png
.venv/Scripts/python tools/make_level.py    # levels/arena.json
```

> **Use `pygame-ce`, not `pygame`.** On Python 3.14 the classic `pygame` package
> has no wheel and falls back to a source build that fails on Windows.
> `pygame-ce` is the maintained community fork and is API-compatible — the code
> still says `import pygame`. Never install both into one environment; they
> collide on the same import name.

## Run

| Command | What it does |
| --- | --- |
| `python main.py` | Play |
| `python main.py --seed 7` | Play a specific run — the same seed replays the same fight |
| `python main.py --smoke` | Pixel-fidelity check: every sprite must upscale with hard edges |
| `python -m pytest` | Full suite, headless, no window |

## Controls

| Input | Action |
| --- | --- |
| WASD / arrows | Move |
| Mouse | Aim |
| Left click (or `J`) | Swing — hold to keep swinging |
| Space / Shift / right click | Dodge roll |
| `R` | Restart the run |
| Esc | Back to the menu |

You keep a fraction of your speed mid-swing, not none of it — committing to an
attack should cost position, not responsiveness.

## Layout

```
src/hack_and_slash/
  core/     vectors, level, collision, spatial index    <- no pygame
  game/     entities, actions, combat, AI, the tick     <- no pygame
  render/   atlas, camera, renderer, HUD, effects
  scenes/   menu, play, smoke
data/       entities.json, weapons.json   -- content, not code
levels/     arena.json
tools/      art generator, level builder, headless screenshots
```

`game/sim.py` is the heart of it: one function that advances the world by one
fixed tick. `game/intent.py` is the seam — the sim takes an `Intent` and nothing
else, so the player and the AI go through exactly the same code and a test can
script a whole fight without an input device.

### The two rules worth keeping

**`core/` and `game/` never import pygame.** All the interesting logic — swing
resolution, collision, pathing, AI — is plain Python, so the whole suite runs
headless with no window and no display driver. `tests/test_architecture.py`
imports every logic module with pygame blocked and fails if any of them needs
it. If you reach for pygame in `core/`, that is the signal the code belongs in
`render/`.

**The simulation runs on a fixed timestep, never on frame time.** Every speed is
pixels per tick and every duration is ticks, so a fight resolves identically at
30fps and at 240. Variable-dt physics would make every combat test a coin toss.
`sim.Accumulator` is the piece that banks real seconds and pays out whole ticks.

A corollary: **the feel pass cannot change a fight.** Screenshake, damage
numbers and hitstop live in `render/effects.py`, fed by events the sim emits and
never reads back. `tests/test_effects.py` runs the same seeded fight with
effects on and off and demands the two come out identical.

## Balance

```sh
python tools/balance.py
```

Runs reference heroes over many seeds and prints where the fight sits. The part
that decides anything is the bracket, and both ends have to hold:

| | must | currently |
| --- | --- | --- |
| **skilled** — closes in, swings, backs off when hurt | win every seed | 8/8, ~17s, worst finish 47/100 |
| **face-tank** — walks in swinging, never disengages | lose every seed | 0/8 |

Only the floor and the fight is unfair; only the ceiling and there is no fight.
`tests/test_playthrough.py` pins both.

**A finding worth knowing before you tune anything.** The obvious way to model a
bad player is a slow reaction time, and it measures almost nothing here — a hero
that never dodges finishes about as healthy as one with perfect reflexes, because
rolling costs uptime and lengthens the fight. What actually separates winning
from losing is *disengaging when hurt*, which is why the ceiling is built on
refusing to do that. A test pins the finding, so if dodging ever becomes decisive
the bracket gets revisited rather than quietly drifting.

Treat that as a caution rather than a verdict on the dodge: these bots have
perfect information and no idea pillars exist, and a human's dodge is doing work
theirs never needs to. It is measured, not settled.

**If the bracket breaks, reach for durability first.** An enemy that dies before
its attack cadence lets it swing again applies no pressure however hard it hits,
and that is arithmetic rather than taste — at the numbers here a grunt lives
about 46 ticks of contact against a 65-tick gap between its swings, so it gets
one attack off and no more. Then count and placement (`tools/make_level.py`),
then cadence (`PAUSE_AFTER_ATTACK` in `game/ai.py`). Enemy damage and hero HP
last: raising damage makes one mistake lethal, which is a harsher game rather
than a tighter one.

## Tuning

The numbers are data. To make the charger fairer, raise its windup:

```json
"gore": { "windup": 32, "active": 26, "recovery": 26, "damage": 13 }
```

To add an enemy, append to `data/entities.json`:

```json
"brute": {
  "name": "Brute", "faction": "enemy", "sprite": "brute",
  "hp": 40, "speed": 0.7, "radius": 7.0, "weapon": "gore",
  "brain": "chaser", "aggro": 200
}
```

then add `"brute"` to `SPRITE_ORDER` in `config.py` and a painter for it in
`tools/gen_art.py`, and regenerate. `tests/test_atlas.py` fails if the data and
the art disagree about which sprites exist.

Brains are code, not data — `game/ai.py` has three, each about twenty lines. A
new one is a new `case` in `decide` plus a name in the JSON.

## Tools

```sh
python tools/gen_art.py                          # rebuild assets/sprites.png
python tools/make_level.py                       # rebuild levels/arena.json
python tools/balance.py                          # where the fight sits
python tools/screenshot.py play out.png          # render a scene headlessly
python tools/screenshot.py play out.png --ticks 240   # ...mid-fight
```

## Known limits

- **One arena.** The slice is a single fight. Floors, loot and progression are
  the obvious next thing and are deliberately not started.
- **No level editor.** `tools/make_level.py` describes the arena as a border plus
  a list of pillar rectangles and writes the JSON. An editor is roughly half a
  project on its own; a twenty-line script is the honest trade for one level.
- **Placeholder art.** Generated shapes, not drawn sprites. Replace
  `assets/sprites.png` with a PNG of the same cell layout to swap in real art.
- **Enemies do not path around walls.** They walk straight at you, so a pillar
  will hold a grunt up. Fine in an open arena, wrong the moment there is a
  corridor — that needs A* over the tile grid, which would live in `core/`.
- **Enemies do not dodge.** Expressed as data: they have no `dodge_ticks`. The
  roll is the player's verb alone.
- **No sound.** Nothing here would have to change to add it; hits already emit
  events with everything a sound cue needs.
- **Projectiles are swept along their centre line only.** `path_is_clear` ignores
  the arrow's radius, so a shot can clip a wall corner by a pixel or two before
  it stops. Cosmetic at this scale; making it exact means sweeping a circle
  rather than a segment.
- **The dodge's worth is measured, not settled.** The reference bots gain nothing
  from it (see Balance). They also have perfect information and no positioning
  sense, so that says more about them than about the roll — but it is the one
  claim in this README that hands on a keyboard could still overturn.
- **The charger commits absolutely.** Once it dashes it cannot stop, including
  into a wall. That is the point, but it does mean a clever player can farm it
  against pillars.
