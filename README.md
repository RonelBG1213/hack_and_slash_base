# Hack and Slash

A top-down twin-stick arena brawler. Move with WASD, aim with the mouse, click
to swing, roll to survive. Four attacks per class — light, neutral, heavy,
ultimate — on ascending cooldowns. Pick one of five classes, then twenty stages
in four acts, each ending on a boss. Your wounds come with you from one stage to
the next, so how well you clear stage one is still with you at the end of the act.

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
| **Bowman** | Are you standing still in the open? Keeps its distance and needs line of sight, so pillars are the answer. |
| **Mage** | The same question from further out, and it hurts more. The hex is slow enough to walk out of, so it costs you position rather than health. |

Two more arrive later. The **rat** is almost as fast as you are, so unlike a
grunt it cannot be walked away from and left -- it dies to one hit of anything
and never turns up alone. The **brute** is the opposite: slow enough to ignore
and tough enough that killing it costs you the attention everything else in the
room wants.

Each act ends on a boss, and all four ask the same three questions from the same
three distances -- sweep up close, a committed charge at mid range, a fan of shots
from far -- so every position has a known answer and the fight is about moving
between them. Below half health each one stops pausing between attacks. None of
them learns a new move, so nothing you worked out stops being true.

| Boss | Act | What is different about it |
| --- | --- | --- |
| **The Warden** | I | The one that teaches the pattern. Slowest thing in the game, longest gaps between attacks. |
| **The Houndmaster** | II | The same three questions in a hurry -- faster body, shorter tells, a tight three-shot spray. |
| **The Effigy** | III | The opposite reading. Enormous reach, the longest telegraph in the game, embers everywhere. |
| **The Sovereign** | IV | Nothing new, and no room. Nine shots across a half-circle, and the reach to punish standing anywhere. |

### The classes

You pick one before the run and it is the whole of character building.

| Class | What it asks of you |
| --- | --- |
| **Knight** | Can you afford to commit? Most health, most damage, worst mobility. The reference class -- the campaign is measured against it. |
| **Rogue** | Can you stay in? Fragile and very fast, with a swing so short that whiffing costs nothing. |
| **Archer** | Can you keep the room between you? Ranged, and a shot spends itself on the first thing it meets -- so the pillars that protect you eat your damage too. |
| **Magician** | Can you find the gap? The hardest single hit in the game, behind the longest commitment. |
| **Priest** | Can you last? Unremarkable in any one fight, and recovers two thirds of its health between stages. |

### The four slots

Every class has four attacks, on ascending commitment and ascending cooldown.

| Slot | Key | What it is |
| --- | --- | --- |
| **Light** | click / `J` | No cooldown. The attack in the table above — the one the class *is*. |
| **Neutral** | `Q` | ~3s. Answers the situation the light attack is worst in, and always hits for less. The Archer's kick, the Magician's ward, the Rogue's thrown knife. |
| **Heavy** | `E` | ~5s. Roughly double the light attack in damage and in commitment. |
| **Ultimate** | `F` | ~25-30s. The largest payoff the class has. Once or twice a stage. |

A neutral buys position rather than kills things — that is the point of it, and
it is why every one of them does less damage than the attack it sits beside. The
Knight's Shield Bash shoves a crowd nearly twice as far as a greatsword swing for
five damage, because a 30-tick greatsword cycle with three grunts on you is the
Knight's actual problem and more damage was never the answer to it.

**These fifteen attacks are the one part of this game that has not been
measured.** Everything else in the balance section below came from running the
campaign and reading the result. The reference bot plays light-only by design —
which is what keeps every recorded number still meaning what it meant — so it
cannot see the other three slots. What the suite pins is the *relationships*
between slots, not the values. Treat the numbers as a first pass.

Only the light attack has to obey the rule that a hero starts a swing faster than
any enemy does. A heavy telegraphing for half a second is a commitment you chose
to spend with a cooldown behind it, which is not the same thing as an enemy
striking before you can answer.

### The run

Twenty stages in four acts. An act introduces one enemy, spends three stages
combining it with everything that came before, and ends on a boss. Enemy counts
rise inside an act and reset at the start of the next one, because a new idea
deserves room.

Health carries between stages and you recover a fixed amount on clearing one.
How much is the class's own number, and for the Priest it is most of the class.
So a run is a single arc rather than twenty separate fights, and a bad stage
costs you rather than ending you. `R` starts a new run as the same class, never a
new stage: replaying a boss at full health is exactly the tension the carry-over
exists to create.

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
.venv/Scripts/python tools/make_level.py    # levels/stage1..20.json + campaign.json
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
| `python main.py --stage 10` | Jump straight to a stage. For tuning: you arrive at full health, so it is not the fight a run gives you |
| `python main.py --class rogue` | Skip the character select and play a class straight away |
| `python main.py --smoke` | Pixel-fidelity check: every sprite must upscale with hard edges |
| `python -m pytest` | Full suite, headless, no window |

## Controls

| Input | Action |
| --- | --- |
| WASD / arrows | Move |
| Mouse | Aim |
| Left click (or `J`) | Light attack — hold to keep swinging |
| `Q` | Neutral skill |
| `E` | Heavy skill |
| `F` | Ultimate |
| Space / Shift / right click | Dodge roll |
| `R` | Restart the run |
| Esc | Back to the menu |

The light attack repeats while held. The three skills do not — each is one press,
because deciding *when* to spend one is most of what makes it a skill, and a
leant-on key would spend every cooldown the instant it expired.

You keep a fraction of your speed mid-swing, not none of it — committing to an
attack should cost position, not responsiveness.

## Layout

```
src/hack_and_slash/
  core/     vectors, level, campaign, collision, spatial index   <- no pygame
  game/     entities, actions, combat, AI, run, the tick          <- no pygame
  render/   atlas, camera, renderer, HUD, effects
  scenes/   menu, select, play, smoke
data/       entities.json, weapons.json   -- content, not code
levels/     stage1..20.json, campaign.json
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

Brains are code, not data -- `game/ai.py` has four, each about twenty lines. A
new one is a new `case` in `decide` plus a name in the JSON. Several creatures
sharing one is normal: the bowman and the mage are both `"archer"`, which names a
behaviour rather than a creature.

Adding a **class** is the same move with `"faction": "hero"`, `"brain":
"player"`, dodge fields and a `heal_between_stages`. There is no second place to
register it -- the character select reads `bestiary.hero_classes`, which is
whatever the faction says, in file order.

Adding a **boss** has one trap worth knowing. The boss brain is positional:
`weapons[0]` is the sweep it uses up close, `weapons[1]` is the charge it uses at
mid range, `weapons[2]` is what it shoots. Declare them in any other order and it
will telegraph one attack and land another. `tests/test_entities.py` pins that,
along with the `sprite_scale: 2` that `render/hud.py` uses to decide what gets a
boss health bar.

## Tools

```sh
python tools/gen_art.py                          # rebuild assets/sprites.png
python tools/make_level.py                       # rebuild the twenty stages
python tools/balance.py                          # where the fight sits, reference class
python tools/balance.py --class all --seeds 8    # ...every class
python tools/screenshot.py select out.png        # render a scene headlessly
python tools/screenshot.py play out.png --stage 20 --class priest --ticks 240
```

## Known limits

- **No progression beyond health.** No upgrades, no loot, no build. You pick a
  class and that is the whole of character building; a run is twenty fights and
  what you have left. This one is load-bearing rather than incidental: because the
  hero never gets stronger, health on a later boss buys fight *length* and nothing
  else, so the act bosses are not much tougher than the first and take their
  difficulty from reach, cadence and arena instead. Both later bosses were drafted
  far tankier and were unwinnable on every seed.
- **No level editor.** `tools/make_level.py` describes each stage as a border plus
  a list of pillar rectangles and writes the JSON. An editor is roughly half a
  project on its own; a short script is still the honest trade at twenty stages,
  though it is nearer the line than it was at four.
- **Ranged escorts do not work on a boss stage.** A bowman never becomes the
  nearest thing in the room, so it is never what you are fighting, so it never
  dies -- a damage tax for the length of the fight with no answer available. The
  act III boss stage was drafted with two of them and was unwinnable on every
  seed. Every boss stage is escorted by melee now, which is a standing constraint
  on level design rather than a bug that got fixed.
- **Placeholder art.** Generated shapes, not drawn sprites. Replace
  `assets/sprites.png` with a PNG of the same cell layout to swap in real art.
- **Nothing paths around walls.** Enemies walk straight at you, so a pillar will
  hold a grunt up. This constrains level design rather than being invisible: a
  pillar that seals a lane strands whatever is behind it, and the player has to
  go and fetch a grunt that spent the fight pushing into a wall. An early draft
  of stage 1 did exactly that. Real pathing means A* over the tile grid, in
  `core/`.

  It also quietly contaminates measurement. Running the skill-using bot over the
  twenty stages, two of the eight cells that moved were not losses at all --
  both hit the tick limit with the hero healthy and every surviving enemy at
  full health, behind a wall and outside its own aggro radius. Nothing had gone
  wrong with the balance; the fight had simply ended up somewhere neither side
  could route out of.
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
- **The bosses have one phase change and no second moveset.** Below half health
  each stops pausing between attacks. Deliberate -- nothing new to learn at the
  moment you can least afford to -- but it does mean a fight holds no surprise once
  you have read the three attacks, and all four bosses share the shape.
- **The enrage threshold is a fraction, so boss health barely affects
  difficulty.** Halving a boss's HP does not halve the damage it deals you: it
  spends the same *proportion* of a shorter fight enraged. Both later bosses were
  tuned by damage in the end, after health changes moved the win rate by nothing
  at all.
- **Five classes, one campaign.** Every stage is tuned against the Knight and only
  checked against the other four. They are not balanced against *each other* --
  the Rogue and the Archer take about 17% of their health on a median stage where
  the Knight takes 28%, and no attempt has been made to close that.
- **The charger commits absolutely.** Once it dashes it cannot stop, including
  into a wall. That is the point, but it does mean a clever player can farm it
  against pillars.
