# Hack and Slash

A top-down twin-stick arena brawler. Move with WASD, aim with the mouse, click to
swing, roll to survive. Four attacks per class — light, neutral, heavy, ultimate —
on ascending cooldowns. Pick one of five classes, then twenty stages in four acts,
each ending on a boss. Your wounds come with you from one stage to the next, so
how well you clear stage one is still with you at the end of the act — and so does
your gold, which a shop between stages will take off you. Survive nineteen and
your class forks in two for the last fight.

Python 3.14 + pygame-ce. No engine, no build step.

---

## Quick start

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
| `1` `2` `3` | Buy, in the shop between stages |
| `1` `2` | Choose a path, on the promotion screen before the last stage |
| Enter / Space / Esc | Dismiss the shop or the promotion screen and start the stage |

The light attack repeats while held. The three skills do not — each is one press,
because deciding *when* to spend one is most of what makes it a skill, and a
leant-on key would spend every cooldown the instant it expired.

---

## Documentation

| | |
| --- | --- |
| [**Design**](docs/design.md) | What the game asks of the player — the fight, the enemies, the bosses, the five classes and the ten they promote into, the four attack slots, the shape of a run |
| [**Loot and gold**](docs/loot.md) | Drop rates, the gold formula, rarity, the between-stage shop, and which of those numbers are measured |
| [**Architecture**](docs/architecture.md) | The two structural rules, the nine-phase tick, the `Intent` seam, determinism and the two RNG streams |
| [**Balance**](docs/balance.md) | The brackets the game is held to, the four findings that overturned an assumption, and what to reach for when a bracket breaks |
| [**Content and tuning**](docs/content.md) | Editing the JSON: adding an enemy, a class, a boss, a brain. The tools |
| [**Testing**](docs/testing.md) | Running the suite, the three load-bearing tests, and the strict-xfail policy |
| [**Known limits**](docs/limits.md) | What this does not do, and which of those were decisions |

### The two rules worth knowing before you touch anything

**`core/` and `game/` never import pygame.** All the interesting logic — swing
resolution, collision, AI, loot arithmetic — is plain Python on plain data, so the
whole suite runs headless. `tests/test_architecture.py` fails the build if that
stops being true.

**The simulation runs on a fixed timestep, never on frame time.** Every speed is
pixels per tick and every duration is ticks, so a fight resolves identically at
30fps and at 240, and a seeded run replays exactly.

Both are explained in [Architecture](docs/architecture.md).
