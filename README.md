# Hack and Slash

A top-down twin-stick arena brawler. Move with WASD, aim with the mouse, click
to swing, roll to survive. Four stages, then The Warden. Your wounds come with
you from one stage to the next, so how well you clear stage one is still with
you at the boss.

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
| **The Warden** | All three at once. It picks its attack from range alone -- sweep up close, a committed charge at mid range, a five-shot fan from far -- so every position has an answer and the fight is about moving between them. Below half health it stops pausing between attacks; it never learns a new move, so nothing you worked out stops being true. |

### The run

Four stages, rising from four grunts in an open yard to the boss. Health carries
between them and you recover 22 on clearing one, so a run is a single arc rather
than four separate fights -- but a bad stage costs you rather than ending you.
`R` starts a new run, never a new stage: replaying the boss at full health is
exactly the tension the carry-over exists to create.

Your dodge roll is invulnerable from its very first frame, and the
invulnerability ends *before* the roll does — so rolling at the right moment
works and rolling constantly does not.

## Setup

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt     # macOS / Linux
```

The art and the stages are both generated, not committed. Build them once:

```sh
.venv/Scripts/python tools/gen_art.py       # assets/sprites.png
.venv/Scripts/python tools/make_level.py    # levels/stage1..4.json + campaign.json
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
| `python main.py --seed 7` | Play a specific run — the same seed replays the same run |
| `python main.py --stage 4` | Jump straight to a stage. For tuning: you arrive at full health, so it is not the fight a run gives you |
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
  core/     vectors, level, campaign, collision, spatial index   <- no pygame
  game/     entities, actions, combat, AI, run, the tick          <- no pygame
  render/   atlas, camera, renderer, HUD, effects
  scenes/   menu, play, smoke
data/       entities.json, weapons.json   -- content, not code
levels/     stage1..4.json, campaign.json
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

Runs reference heroes over many seeds and prints where the game sits. Two
brackets, because they fail independently — a run can be unwinnable while every
stage is fine alone (the heal is too small), and every stage can be fine while
the run never gets tense (the heal is too large).

| | must | currently |
| --- | --- | --- |
| **every stage**, entered at full health | clear on every seed | 8/8 each, 4–18s |
| **whole run**, health carrying | clear on every seed | 8/8, ~52s, worst finish 58/100 |
| **face-tank** — walks in swinging, never disengages | lose every run | 0/8 |

Only the floor and the game is unfair; only the ceiling and there is no game.
`tests/test_playthrough.py` pins all three.

**Two findings worth knowing before you tune anything.**

*Reaction time is not what decides these fights.* Across slow and moderate
reactions the outcome barely moves — rolling costs uptime and lengthens a fight,
so reacting sooner does not obviously pay. What separates winning from losing is
*disengaging when hurt*, which is why the ceiling is a hero that refuses to.

*A zero-tick reaction is not skill, it is an artifact.* A hero answering every
telegraph on the tick it opens rolls perpetually against something winding up or
swinging half the time — the boss — and never swings back. It loses 7 of 8 runs
where the twelve-tick policy wins all 8. So the reference hero is the twelve-tick
one. That was invisible until there was a boss to expose it, and it is the reason
to distrust any single bot as a stand-in for a player.

Treat both as cautions rather than verdicts on the dodge: these bots have perfect
information and only the crudest sense that pillars exist. Measured, not settled.

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
python tools/make_level.py                       # rebuild the four stages
python tools/balance.py                          # where the fight sits
python tools/screenshot.py play out.png          # render a scene headlessly
python tools/screenshot.py play out.png --stage 4 --ticks 240   # ...mid-fight
```

## Known limits

- **No progression beyond health.** No upgrades, no loot, no build. A run is four
  fights and what you have left; picking an upgrade between stages is the obvious
  next thing and is deliberately not started.
- **No level editor.** `tools/make_level.py` describes each stage as a border
  plus a list of pillar rectangles and writes the JSON. An editor is roughly half
  a project on its own; a short script is the honest trade for four stages.
- **Placeholder art.** Generated shapes, not drawn sprites. Replace
  `assets/sprites.png` with a PNG of the same cell layout to swap in real art.
- **Nothing paths around walls.** Enemies walk straight at you, so a pillar will
  hold a grunt up. This constrains level design rather than being invisible: a
  pillar that seals a lane strands whatever is behind it, and the player has to
  go and fetch a grunt that spent the fight pushing into a wall. An early draft
  of stage 1 did exactly that. Real pathing means A* over the tile grid, in
  `core/`.
- **Enemies do not dodge.** Expressed as data: they have no `dodge_ticks`. The
  roll is the player's verb alone.
- **No sound.** Nothing here would have to change to add it; hits already emit
  events with everything a sound cue needs.
- **Projectiles are swept along their centre line only.** `path_is_clear` ignores
  the arrow's radius, so a shot can clip a wall corner by a pixel or two before
  it stops. Cosmetic at this scale; making it exact means sweeping a circle
  rather than a segment.
- **The dodge's worth is measured, not settled.** The reference bots gain little
  from it, and the twitchiest one is actively crippled by it (see Balance). They
  have perfect information and only the crudest sense of pillars, so that says
  more about them than about the roll — but it is the claim in this README most
  likely to be overturned by hands on a keyboard.
- **The boss has one phase change and no second moveset.** Below half health it
  stops pausing between attacks. Deliberate — nothing new to learn at the moment
  you can least afford to — but it does mean the fight has no surprise in it once
  you have read the three attacks.
- **The charger commits absolutely.** Once it dashes it cannot stop, including
  into a wall. That is the point, but it does mean a clever player can farm it
  against pillars.
