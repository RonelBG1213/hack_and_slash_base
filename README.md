# Hack and Slash

A top-down twin-stick arena brawler. Move with WASD, aim with the mouse, click to
swing, roll to survive. Four skills per class — a light attack, a self-buff, a
heavy and an ultimate — on ascending cooldowns. Pick one of five classes, then fifty stages in ten acts,
each ending on a boss. Your wounds come with you from one stage to the next, so
how well you clear stage one is still with you at the end of the act — and so does
your gold. Between two stages is a room — a fountain, a shop, a shrine or a
chest — and three doors deciding what the next one will be.

Clear stage twenty and your class forks in two. There is no declining it, and
there are thirty more stages on the other side.

Python 3.14 + pygame-ce. No engine, no build step.

---

## Quick start

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt     # macOS / Linux
```

The art and the stages are both generated. The art is not committed, so build it
once; the stages are, so you only need to rebuild them after editing one:

```sh
.venv/Scripts/python tools/gen_art.py       # assets/sprites.png
.venv/Scripts/python tools/make_level.py    # levels/stage1..40.json + campaign.json
.venv/Scripts/python tools/make_rooms.py    # levels/rooms/chamber.json
```

Then:

```sh
.venv/Scripts/python main.py
```

> [!IMPORTANT]
> **Use `pygame-ce`, not `pygame`.** On Python 3.14 the classic `pygame` package
> has no wheel and falls back to a source build that fails on Windows.
> `pygame-ce` is the maintained community fork and is API-compatible — the code
> still says `import pygame`. Never install both into one environment; they
> collide on the same import name.

## Run

| Command | What it does |
| --- | --- |
| `python main.py` | Play |
| `python main.py --seed 7` | Play a specific run — the same seed replays the same run. Overrides the seed set on the Settings screen |
| `python main.py --stage 10` | Jump straight to a stage. For tuning: you arrive at full health, so it is not the fight a run gives you |
| `python main.py --class rogue` | Skip the character select and play a class straight away. Advanced classes are named here too, which is the only way to reach one without playing twenty stages to it |
| `python main.py --smoke` | Pixel-fidelity check: every sprite must upscale with hard edges |
| `python -m pytest` | Full suite, headless, no window |

## The main menu

Six rows: New Game, Load Game, Settings, Achievements, Unlockables, Quit Game.
Up/down to choose, Enter to take one, Esc to quit. That is the whole screen — the
key bindings used to be printed down the right of it and are now on Settings,
which is where you go to look something up rather than to start.

**Load Game** is a single autosave slot, written on the tick a stage begins and
deleted when the run ends. A save records the campaign index, the seed, the
class, the health carried in and what the run has banked; the arena itself is
*rebuilt* from those rather than stored, which is what makes a loaded stage the
stage that was saved rather than one that resembles it. There is deliberately no
mid-fight save — see `src/hack_and_slash/game/save.py` for why.

**Settings** covers window scale and fullscreen, screenshake, damage numbers, the
seed for the next run, and erasing the save and profile, with the controls listed
beside them for reference. They are printed, not rebindable. Nothing on that screen
can change how a fight resolves, which is the line it is drawn on: difficulty is
a balance decision and balance decisions live in `data/` where they get swept.

**Difficulty** is chosen on the character select, beside the class — **Easy,
Normal, Hard, Nightmare**, up and down to move between them. A tier says how
much damage *the hero* takes and what the monsters are: their health, damage,
walking speed, aggro radius, attack cadence, and how often they slip a blow
entirely — the harder tiers defend. The default tier is structurally pinned to
the arithmetic every recorded balance number was measured against, monsters
included: at Normal every dial sits at its own identity, every enemy is the
creature `data/entities.json` declares, and `data/difficulty.json` refuses to
load if that is not true of the default. The other three ship marked untuned
until `tools/balance.py --difficulty` has swept them.

**Achievements** and **Unlockables** are stubs and say so. Achievements draws
four lifetime counters from `state/profile.json`; nothing is defined. Unlockables
is empty because unlocks were chosen to be gameplay-affecting, and the first one
that ships moves the recorded class×stage grid — so it is a design decision to be
taken deliberately rather than a screen to be filled in.

`state/` holds the save, the settings and the profile. It is generated and
gitignored, like `levels/` and `assets/`.

## Controls

Also on the Settings screen, in short form — this table is the long one.

| Input | Action |
| --- | --- |
| WASD / arrows | Move |
| Mouse | Aim |
| Left click (or `J`) | Light attack — hold to keep swinging |
| `Q` | Class buff — no hitbox; grants your class's own stat block for a few seconds |
| `E` | Heavy skill |
| `F` | Ultimate |
| Space / Shift / right click | Dodge roll |
| `I` / Tab | Character sheet — what the class brings, what the run earned, and the total |
| `R` | Restart the run |
| Esc | Back to the menu |
| Up / down, Enter | Choose, on the menu and the Settings screen |
| Left / right | Change a value, on the Settings screen |
| `1`–`8` | Buy, at a stall — three rolled pieces of gear over the consumables |
| `1`–`3` | Spend a point, at a shrine — three of the eight attributes |
| `1` `2` | Choose a path, on the promotion screen after stage twenty |
| Enter / Space / Esc | Dismiss the stall, the shrine or the character sheet |

Between two stages is a **reward room** you walk through: a fountain, a shop
stall, a shrine or a chest, and three doors naming what the room after the
*next* stage will hold. Walk onto the fixture to use it and through a door to
leave. There is no key for any of that — a room is somewhere you are, not a menu.

**The doors stand on the three walls you did not come in through**, and the one
you take is the wall the next room puts you at — so the rooms lie end to end and
a run is a path rather than a series of identical boxes. **The stall is on every
third floor and on every floor that follows a boss, and on no other**, so you
always know how far the next chance to spend is — and clearing an act always
leads to one.

**The stall and the shrine roll.** A stall shows three pieces of gear drawn from
a pool of twelve, each at its own rarity, priced against the floor and gone when
you leave — over the five consumables that are always there. A shrine shows
three of the eight attributes to spend its point on. Both rolls come from the
run's seed and the room's index, so quitting and coming back finds the same
shelf.

**The stall only shows what you can still buy.** A piece of gear leaves the
shelf the moment you buy it, and a consumable leaves when it hits its cap; the
uncapped one stays for the whole run. The rows under a purchase move up, so the
digits are what is on the shelf now rather than what was on it when you walked
in.

The promotion screen is the one panel with no exit key. Twenty stages are
tuned for the class you become, so there is nothing sensible for a refusal to
mean — and Enter, which dismisses every other panel in the game, would otherwise
throw the run away by habit.

The light attack repeats while held. The three skills do not — each is one press,
because deciding *when* to spend one is most of what makes it a skill, and a
leant-on key would spend every cooldown the instant it expired.

A dodge or a skill pressed between two simulation ticks waits for the next one
rather than being dropped — including during the freeze after a hit lands, which
is where most of them used to go. The dodge goes further and stays live for a
few ticks, so a roll pressed a moment early still comes out when you are free to
take it. It never grants a roll the game would otherwise refuse.

---

## Documentation

| | |
| --- | --- |
| [**Design**](docs/design.md) | What the game asks of the player — the fight, the enemies, the bosses, the five classes and the ten they promote into, the four attack slots, the shape of a run, the traps the floor puts under you, and the fork in the middle of it |
| [**Loot and gold**](docs/loot.md) | Drop rates, the gold formula, rarity, the shop and the room you reach it through, and which of those numbers are measured |
| [**Architecture**](docs/architecture.md) | The two structural rules, the nine-phase tick, the `Intent` seam, determinism and the four RNG streams |
| [**Balance**](docs/balance.md) | The brackets the game is held to, the four findings that overturned an assumption, and what to reach for when a bracket breaks |
| [**Content and tuning**](docs/content.md) | Editing the JSON: adding an enemy, a variant, a class, a boss, a brain, a room, a trap. The tools |
| [**Testing**](docs/testing.md) | Running the suite, the three load-bearing tests, and the strict-xfail policy |
| [**Known limits**](docs/limits.md) | What this does not do, and which of those were decisions |
| [**Roadmap**](docs/roadmap.md) | What is missing against the genre this sits in, what each absence costs, and the order to buy them back — the one document here that is judgement rather than measurement |

### The two rules worth knowing before you touch anything

**`core/` and `game/` never import pygame.** All the interesting logic — swing
resolution, collision, AI, loot arithmetic — is plain Python on plain data, so the
whole suite runs headless. `tests/test_architecture.py` fails the build if that
stops being true.

**The simulation runs on a fixed timestep, never on frame time.** Every speed is
pixels per tick and every duration is ticks, so a fight resolves identically at
30fps and at 240, and a seeded run replays exactly.

Both are explained in [Architecture](docs/architecture.md).
