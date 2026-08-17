# Architecture

## Why Python at all

This genre ships on Unity and C#. Python is not a shipping language for it, and
this is not pretending otherwise — it is here to get the *combat design* right
cheaply, where changing a number and feeling the result takes seconds.

That only pays off if the design survives the move to a real engine. So the game
logic is kept engine-agnostic, and porting means rewriting `render/` and
`scenes/` rather than the game.

---

## Layout

```
src/hack_and_slash/
  core/     vectors, level, campaign, collision, spatial index   <- no pygame
  game/     entities, actions, combat, AI, run, the tick          <- no pygame
  render/   atlas, camera, renderer, HUD, effects, shop and job panels
  scenes/   menu, select, play, options, achievements, unlockables, smoke
  settings.py  the player's preferences                            <- no pygame
data/       entities.json, weapons.json, loot.json   -- content, not code
levels/     stage1..40.json, campaign.json           -- generated
assets/     sprites.png                              -- generated
state/      save.json, settings.json, profile.json   -- written while playing
tools/      art generator, level builder, balance sweep, screenshots
tests/      803 tests, all headless
```

| Module | What it is |
| --- | --- |
| `game/sim.py` | The heart of it: one function that advances the world by one fixed tick |
| `game/intent.py` | The seam — the sim takes an `Intent` and nothing else |
| `game/world.py` | All state for one stage. Owns the two RNG streams |
| `game/run.py` | The layer above a stage: what carries between them |
| `game/skills.py` | Names the four attack-slot indices, so they are not bare integers in three places |
| `core/spatial.py` | Broadphase hash. `World` builds it with cell 48 — a little wider than the longest reach in the game, so a swing query sweeps four buckets at worst |
| `game/save.py` | Snapshot and restore a `Run`. Pure functions over a `dict`; the disk is touched from `scenes/` only, so the balance sweep cannot grow a file dependency |
| `game/profile.py` | Four lifetime counters, and the only thing in the project that outlives a run |
| `settings.py` | Window, effect toggles, seed. Beside `config.py` rather than in `render/` because the window size is read *before* there is a display to ask |

Both are **generated**, and they are treated differently on the way into git:
`assets/*.png` is gitignored, `levels/*.json` is committed. A fresh clone must
run `tools/gen_art.py` before anything works; `tools/make_level.py` only has to
be rerun after editing a stage. See [Content](content.md#tools).

> [!NOTE]
> This is an inconsistency rather than a decision anybody wrote down, and the
> forty-stage extension made it visible: twenty new `levels/stage*.json` files
> show up untracked in `git status` beside twenty tracked ones. Either they all
> belong in the repo or none of them do. Committing them means a clone can be
> played without running a tool and diffs show what a stage edit did to the
> arena; ignoring them means one less generated artifact to keep in step. It has
> not been settled.

`state/` is the third generated directory and the only one written *while the
game runs* — the save file, the settings and the profile. Gitignored, and not
because it is awkward to track: one player's progress is not a fact about the
project. Nothing under `core/` or `game/` reads it except through an explicit
path argument, and **nothing that decides a fight reads it at all.** The save
describes a run and the profile counts them; neither is an input to either. That
is what keeps `tools/balance.py` and the class×stage grid free of any dependency
on what happens to be on disk.

---

## The two rules worth keeping

### `core/` and `game/` never import pygame

All the interesting logic — swing resolution, collision, pathing, AI, loot
arithmetic — is plain Python on plain data, so the whole suite runs headless with
no window and no display driver.

`tests/test_architecture.py` imports every module in those two packages **in a
subprocess** with `sys.modules['pygame'] = None`, so `import pygame` raises. A
subprocess because any other test may already have imported pygame and would mask
the dependency. If you reach for pygame in `core/`, that is the signal the code
belongs in `render/`.

Two things ride on it: the headless suite, and the eventual port staying
affordable.

### The simulation runs on a fixed timestep, never on frame time

Every speed is pixels per tick and every duration is ticks, so a fight resolves
identically at 30fps and at 240. Variable-dt physics would make every combat test
a coin toss. `sim.Accumulator` is the piece that banks real seconds and pays out
whole ticks.

**A corollary: the feel pass cannot change a fight.** Screenshake, damage numbers
and hitstop live in `render/effects.py`, fed by events the sim emits and never
reads back. `tests/test_effects.py` runs the same seeded fight with effects on and
off and demands the two come out identical.

**And a trap, which cost the dodge for a long time.** A rendered frame and a
simulation tick are not the same thing, and a frame can produce zero ticks or —
during hitstop — several that never step. Anything edge-triggered therefore has
to be spent by the *tick that consumes it*, never by the frame that read it:
`PlayScene` cleared its dodge and skill flags once per frame, so a press landing
in either window was discarded before `sim.step` ever saw it. `_read_intent`
reads, `_consume_edges` spends, and `_drop_edges` throws away — three different
events that used to be one line.

**That fix alone measured as worth nothing, which is the more interesting
half.** Reaching the sim is not the same as being accepted. Being hit sets both
`freeze` and `stagger`, and `freeze` drains *without stepping* — so the stagger
has not counted down at all when stepping resumes, and a press delivered on the
first stepped tick is delivered into an `actions.can_dodge` that refuses it. A
press made during hitstop landed 0 out of 33 times before the fix and 0 out of
16 after it. It needed to survive `DODGE_BUFFER_TICKS` — one more than the
stagger — at which point it lands every time.

The buffer grants nothing the sim would refuse; it re-asks, and the sim gets the
last word. It is bounded for the same reason it exists: an unbounded one is a
roll the player has stopped wanting. What stops one press becoming two rolls is
`dodge_ticks + dodge_cooldown` — 28 ticks on the shortest class against a
six-tick buffer — which is a **content** number rather than anything in the
scene, so `test_one_press_is_one_roll` and
`test_the_dodge_buffer_is_shorter_than_every_roll_in_the_game` pin it where it
can actually drift.

Two rules generalise past this codebase:

1. **Wherever a fixed-timestep sim sits behind a variable-rate input loop,
   one-shot inputs belong on the sim's clock.**
2. **Delivering an input is not the same as it being accepted.** Measure the
   thing the player sees, not the thing you fixed — the first patch here was
   correct, complete against its own description, and moved nothing.

---

## The Intent seam

`sim.step(world, intent)` takes a world and an `Intent` and nothing else.

The player and the AI produce the same structure, so they go through exactly the
same code path, and a test can script a whole fight with no input device, no
window and no clock. `game/autoplay.py` is a bot that produces `Intent`s; so is
`scenes/play.py` reading the keyboard. Neither is privileged.

## The tick

`sim.step` runs nine phases in an order that is not arbitrary. Each reads the
results of the last, and moving any of them changes the game.

| # | Phase | What it does |
| --- | --- | --- |
| 1 | timers | i-frames, cooldowns and stagger expire before anything consults them, and health regeneration accrues |
| 2 | decide | the hero's intent arrives from outside; enemies produce theirs |
| 3 | begin | new swings and dodges start, committing facing |
| 4 | move | walking, dashes and knockback, resolved against walls |
| 5 | separate | bodies pushed out of each other |
| 6 | index | the broadphase is rebuilt **after** everything has moved, so a hit test never consults last tick's positions |
| 7 | strike | open hitboxes and arrows resolve against where things are *now* |
| 8 | advance | state machines move on, opening hitboxes and loosing arrows for the tick to come |
| 9 | settle | the run is judged, the dead drop what they were carrying, and *then* they are removed |

Phase 9's internal order matters too: the hero has to still be in the list to be
found dead, and a body that has already been culled cannot be asked what it was
worth. It is also what makes loot bookkeeping unnecessary — a body is dead and
still in the list for exactly one settle, so every kill pays out exactly once.

---

## Determinism

A run replays exactly from its seed. That is what makes every recorded number in
[Balance](balance.md) mean something.

**Nothing anywhere may call the module-level `random` functions.** One call and a
seeded run stops replaying, and every damage assertion in the suite becomes a coin
toss.

Each stage in a run is seeded `seed + index * 1013`. Without the offset every
stage would draw the same rolls in the same order, which is both duller and a
worse test — a bug that only shows up on a particular sequence would never appear
twice.

### Three random streams, not one

`World` holds **three** seeded generators, all derived from the one seed:

| Stream | Seeded | Draws for |
| --- | --- | --- |
| `world.rng` | `seed` | the fight — damage rolls, and nothing else |
| `world.loot_rng` | `seed ^ 0x10071` | what a kill leaves behind |
| `world.attr_rng` | `seed ^ 0x2A771` | crit and dodge |

> [!IMPORTANT]
> This split is the load-bearing guarantee of the whole loot layer.
>
> `combat.roll_damage` draws from `world.rng` on every hit. One interleaved loot
> draw shifts every subsequent damage roll for the rest of the run — which would
> move all 280 cells of the recorded class×stage grids **without a single balance
> number changing, and nothing would report it.**
>
> `test_loot_rolls_do_not_disturb_the_damage_stream` runs the same seeded fight
> with a deliberately generous loot table and a silent one, and asserts the damage
> lists come out identical. It was written before the code it guards.

Any future subsystem that rolls dice gets its own offset, for the same reason. Two
generators seeded identically are one generator — the offset *is* the mechanism.

> [!NOTE]
> **The attribute layer is the rule being followed rather than restated.** Crit
> and dodge are dice; both draw from `attr_rng`, and
> `test_attributes.py::test_attribute_rolls_do_not_disturb_the_damage_stream`
> is the loot test's sibling — the same seeded fight run twice, once neutral and
> once with a crit that fires on every hit and multiplies by exactly one, so the
> two are arithmetically identical while only one of them rolls.
>
> Two details worth copying next time. **Zero takes an early return and draws
> nothing**, mirroring `roll_damage` at zero variance, so a switched-off
> attribute costs the stream nothing at all. And the guard uses *crit* rather
> than dodge: an evaded hit changes the fight rather than the arithmetic, so the
> two runs would legitimately diverge and prove nothing.
>
> Experience needed **no** stream. It is `xp_base * monster_level` and rolls
> nothing, which is why the progression layer cannot disturb a damage roll
> however it is tuned.

One related trap: the weighted rarity draw is written long-hand as a single
`random()` against a cumulative sum rather than with `random.choices`, because
`choices` may consume a different number of values between Python versions.

---

## Scenes

Scenes swap by **replacement** — a scene returns a new one from `update` or
`handle_event`, and `scenes/base.App` runs whatever it is handed.

That is why the between-stage shop is a **modal state inside `PlayScene`** rather
than a scene of its own. A shop scene would have to hand a live `Run` back to a
`PlayScene` whose constructor builds a fresh one.

While the shop is open the world is not stepped **and the accumulator is not
fed**. Banking real seconds behind a panel would fast-forward the first moments of
the next stage the instant it closed.
