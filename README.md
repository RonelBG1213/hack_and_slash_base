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

The art, the sound and the stages are all generated. The art and the sound are
not committed, so build them once; the stages are, so you only need to rebuild
them after editing one:

```sh
.venv/Scripts/python tools/gen_art.py       # assets/sprites.png
.venv/Scripts/python tools/gen_sfx.py       # assets/sfx/*.wav
.venv/Scripts/python tools/make_level.py    # levels/stage1..50.json + campaign.json
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

**Settings** covers window scale and fullscreen, **sound volume**, the seed for
the next run, erasing the save and profile, and two rows that open a screen of
their own — **Accessibility** and **Controls**. Volume is a 0-10 dial: left and
right move it, Enter mutes and a second Enter puts it back where it was, and the
row reads `off` at zero. It is reachable from the pause overlay as well as from
here; the erase row is the one thing it does not offer mid-run. Nothing on that screen can change how a fight resolves,
which is the line it is drawn on: difficulty is a balance decision and balance
decisions live in `data/` where they get swept. Which key swings is not how hard
the swing lands, so the bindings sit on the right side of that line.

**Accessibility** is five toggles. **Colourblind** swaps the colours that carry
meaning — the health ladder, the enemy pips, the damage numbers and the rarity
tiers — for a set that stays readable without red-green vision; nothing else on
screen changes. **Reduce flashing** holds the low-health bar steady instead of
pulsing it, and stops the character select's prompt blinking. **Reduce motion**
skips the freeze a landed blow puts on the frame, which costs no ticks: the
freeze never advanced the world, so the fight plays out identically either way.
**Screenshake** and **Damage numbers** moved here from Settings, which is where
they should have been. Every row is safe to change with a fight paused behind it.

There is no text scale and no assist mode, and both are decisions rather than
gaps — `docs/limits.md` gives the reasoning for each. The short version: the game
draws into a 384x216 surface with no room for larger glyphs, and the window scale
row already upscales every one of them; and difficulty is the assist mechanism,
chosen on the character select where a balance decision belongs.

**Controls** rebinds the eleven gameplay keys — the four directions, the four
attacks, the roll, the character sheet and restart. Up and down to choose, Enter
to arm a row, then press the key you want; Escape cancels an armed row instead of
leaving, and a Reset row puts everything back. Rebinding an action **replaces**
every key it had, so binding Move up to the up arrow drops `W` from it.

Escape, Enter and the digits that buy at a stall, spend at a shrine and choose at
the fork are **not** rebindable, and the screen refuses them: they are how you
reach that screen and leave it. The mouse buttons are not rebindable either.

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

**Achievements** is a stub and says so: four lifetime counters from
`state/profile.json`, and nothing defined against them.

**Unlockables** is not one any more. It lists what `data/unlocks.json` offers,
what each one still wants, and which of them are switched on. Three to start —
Hard at stage 10, Nightmare at stage 25, and **Champion's Wake**, which turns on
the elite layer for a run won. Escape leaves; Enter turns a modifier on.

The rule the screen is built under, because it is the one that used to keep it
empty: **an unlock grants access and never numbers.** A run that begins with
numbers the reference bot did not have is measuring a different game and the
recorded class×stage grid stops describing it; a run that begins with a *choice*
costs nothing, because the grid measures a specified class over a specified
stage and does not care how the player got the right to pick it. There is no
`attributes` key in the schema, so that is enforced rather than remembered.

`state/` holds the save, the settings and the profile. It is generated and
gitignored, like `levels/` and `assets/`.

## Controls

What the game ships with. Everything in the first table is **rebindable** on
Settings → Controls; nothing in the second is.

| Input | Action |
| --- | --- |
| WASD / arrows | Move |
| Left click (or `J`) | Light attack — hold to keep swinging |
| `Q` | Class buff — no hitbox; grants your class's own stat block for a few seconds |
| `E` | Heavy skill |
| `F` | Ultimate |
| Space / Shift | Dodge roll |
| `I` / Tab | Character sheet — what the class brings, what the run earned, and the total |
| `R` | Restart the run |

Aiming is the mouse and the two mouse buttons are fixed: left click swings and
right click rolls, alongside whatever keys those actions are bound to.

| Input | Action |
| --- | --- |
| Mouse | Aim |
| Left click / right click | Swing / dodge roll |
| Esc | Pause — resume, Settings, or quit to the menu |
| Up / down, Enter | Choose, on the menu and the Settings screen |
| Left / right | Change a value, on the Settings screen |
| `1`–`8` | Buy, at a stall — three rolled pieces of gear over the consumables |
| `1`–`3` | Spend a point, at a shrine — three of the eight attributes |
| `1` `2` | Choose a path, on the promotion screen after stage twenty |
| Enter / Space / Esc | Dismiss the stall, the shrine or the character sheet |

**When a run ends** — however it ends — the arena stops and a summary takes the
screen: the verdict, the class and the branch it took, how deep you got and how
long the fighting took, gold left, kills, damage dealt and taken, the attributes
the run built, and everything it bought. Gear is counted rather than named, and
a run you loaded from a save counts only the session you played — both for
reasons in [Limits](docs/limits.md#what-the-run-summary-cannot-say).

**Esc pauses the fight** rather than ending it. The world stops where it is —
nothing is banked, so resuming picks up on the tick it stopped — and the overlay
offers Resume, Settings and Quit to menu. Quitting keeps whatever the autosave
holds, which is the start of the room you were in, and the Quit row says which
stage that is. Nothing is written when you pause or quit: a save is still only
ever taken on the tick a room begins.

Settings from the pause menu is the real one, not a copy — including Controls and
Accessibility, so a binding that is wrong, or a palette that is unreadable, can be
fixed in the fight that revealed it. The only row missing there is **Erase saved
run**, which does not mean anything while you are playing the run it would erase.

The second table is fixed because every row in it is how you reach a screen or
leave one. A swing bound to Escape is a player who cannot get out of the arena;
a roll bound to `1` is a player who buys a Tonic every time they dodge at a
stall. `state/settings.json` records only the actions you actually moved, so a
key that never gets rebound follows the game if the shipped default ever changes.

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
| [**Design**](docs/design.md) | What the game asks of the player — the fight, the enemies, the bosses, the champions among them, the five classes and the ten they promote into, the four attack slots, the shape of a run, the traps the floor puts under you, and the fork in the middle of it |
| [**Loot and gold**](docs/loot.md) | Drop rates, the gold formula, rarity, the shop and the room you reach it through, and which of those numbers are measured |
| [**Architecture**](docs/architecture.md) | The two structural rules, the nine-phase tick, the `Intent` seam, determinism and the six RNG streams |
| [**Balance**](docs/balance.md) | The brackets the game is held to, the four findings that overturned an assumption, and what to reach for when a bracket breaks |
| [**Content and tuning**](docs/content.md) | Editing the JSON: adding an enemy, a variant, a class, a boss, a brain, a room, a trap, an elite affix, an unlock, a status. The tools |
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
