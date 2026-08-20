# Testing

```sh
python -m pytest              # 803 tests, headless, no window
python -m pytest tests/test_loot.py
python main.py --smoke        # pixel fidelity: every sprite upscales with hard edges
```

> [!NOTE]
> **The suite is slow now, and it is `test_playthrough.py` that is slow.** Two
> class×stage grids over a forty-stage campaign is a few hundred simulated
> fights, and the whole-run brackets play forty stages end to end several times
> over. Everything else in the suite finishes in seconds.
>
> ```sh
> python -m pytest --ignore=tests/test_playthrough.py   # the fast gate
> python -m pytest -k "not stage" tests/test_playthrough.py
> ```
>
> The gate before a commit is still the whole thing. These are for the edit
> loop, not for the merge.

`pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]`, so
pytest needs no `PYTHONPATH` and no editable install. `tests/conftest.py` forces
`SDL_VIDEODRIVER=dummy` before anything imports pygame — on CI there is no
display, and locally a window stealing focus mid-run is its own kind of flakiness.
That only matters for the handful of render tests; everything under `core/` and
`game/` is pygame-free by design and does not care.

---

> [!WARNING]
> ## Never read the exit code through a pipe
>
> `pytest -q | tail` reports **tail's** exit code. `tail` succeeds at printing a
> failure summary, so the command exits 0 and the gate goes green. Two real
> failures once sat unnoticed on `main` this way.
>
> ```sh
> python -m pytest -q > out.txt 2>&1; echo "PYTEST_EXIT=$?"
> tail -20 out.txt
> ```
>
> `set -o pipefail` also works in bash. PowerShell has no equivalent — use
> `$LASTEXITCODE`, and note that `$?` is `$true` for a native exe whose stderr you
> redirected, which is a second way to be lied to on Windows.

---

## What the suite is made of

| File | Tests | What it guards |
| --- | --- | --- |
| `test_playthrough.py` | 313 | the [balance brackets](balance.md) and both class×stage grids |
| `test_run.py` | 34 | carry-over: health, gold, banking across stages, and that a promotion survives one |
| `test_render.py` | 50 | drawing, the HUD, the panels, and the input path — headless |
| `test_loot.py` | 28 | the gold formula, rarity weights, the sweep, the RNG split |
| `test_progression.py` | 14 | experience, the curve, spending, and **that the layer ships off** |
| `test_attributes.py` | 12 | the attribute block, and **that it moved nothing** |
| `test_entities.py` | 27 | content validity: levels, boss weapon order, sprite scale |
| `test_collision.py` | 20 | movement against walls, separation, swept paths |
| `test_actions.py` | 19 | the WINDUP → ACTIVE → RECOVERY state machine |
| `test_ai.py`, `test_boss.py`, `test_sim.py` | 17 each | brains, the boss positional brain, one tick |
| `test_combat.py` | 16 | hit resolution and damage rolls |
| `test_campaign.py` | 15 | act structure, stage ordering, playability |
| `test_shop.py` | 23 | prices, caps, the late shelf, the Boots, refusal when short |
| `test_level.py` | 13 | tiles, solidity, spawns |
| `test_effects.py` | 14 | that the feel pass changes nothing, whichever way its toggles are set |
| `test_menu.py` | 38 | the six menu rows, the autosave, the options screen, and both column layouts |
| `test_save.py` | 16 | **that a loaded stage is the stage that was saved** |
| `test_settings.py` | 13 | preferences and the profile, and that neither can stop the game starting |
| `test_skills.py` | 11 | slot indices and the cooldown contract |
| `test_atlas.py` | 9 | data and art agree about which sprites exist |
| others | | vectors, camera, spatial hash, level IO |
| `test_architecture.py` | 1 | **the rule the project rests on** |

## The seven tests that are load-bearing

Each of these guards something that would otherwise fail **silently** — no
assertion anywhere else would notice.

### `test_architecture.py` — the pygame rule

Imports every module in `core/` and `game/` in a subprocess with
`sys.modules['pygame'] = None`, so `import pygame` raises `ImportError`. A
subprocess because any other test may have imported pygame already and would mask
the dependency. Failure message names the offending module and says to move it
into `render/`.

### `test_effects.py` — the feel pass changes nothing

Runs the same seeded fight with effects on and off and demands the two come out
identical. Screenshake and damage numbers are fed by events the sim emits and
never reads back; this is what keeps that true.

### `test_loot.py::test_loot_rolls_do_not_disturb_the_damage_stream`

Runs the same seeded fight with a deliberately generous loot table and a silent
one, and asserts the damage lists are identical. Written before the code it
guards. See [Architecture](architecture.md#five-random-streams-not-one) for why
a single shared generator would have invalidated every recorded number without
anything failing.

### `test_attributes.py::test_attribute_rolls_do_not_disturb_the_damage_stream`

The same test a second time, for the same reason, against `attr_rng` — crit and
dodge are dice and the third stream is what keeps them out of the fight's.

The shape is worth copying rather than the code. The fight runs twice: once
neutral, once with a crit that fires on **every** hit and multiplies by
**exactly one**. Both are arithmetically the same fight; only one of them rolls.
Using dodge here instead would prove nothing, because an evaded hit changes the
fight rather than the arithmetic and the two runs would legitimately diverge.

Its quieter sibling, `test_neutral_attributes_reproduce_todays_arithmetic`, is
what makes "the attribute layer moved none of the 280 cells" a structural fact
rather than the result of a sweep somebody remembered to run — and
`test_progression.py::test_the_shipped_table_ships_switched_off` is what keeps
it true.

### `test_rooms.py::test_the_map_stream_does_not_disturb_the_damage_stream`

The same test a third time, against the fourth stream. Runs one seeded fight with
the room layer rolling continuously alongside it and one with it silent, and
demands the damage lists come out identical.

Worth having even though the map stream is a `Random` the fight never sees,
because the failure it guards against is not "the wrong generator was passed in"
— it is a `random.shuffle` or a `random.choice` reached for out of habit in
`game/rooms.py`, which draws from the module-level generator and would shift
nothing visible and everything measured.

Its sibling `test_an_arena_carries_no_props_at_all` is the other half of the
claim: `sim._touch_props` opens on `if not world.props: return`, so the phase is
free on every tick the grid has ever measured — and that is only true while no
stage file grows a prop, which is asserted rather than assumed.

### `test_hazards.py::test_traps_do_not_disturb_the_damage_stream`

The same test a fourth time, and the one with the most to guard, because the
hazard layer is the first that lands on a **measured** tick. Loot pays out on a
kill and a room happens between stages; a trap is in the arena, on the floor the
reference bot walks across.

So it could not be kept off the measured path, and was instead built to need
almost no dice: `hazard_rng` is drawn from once, at world construction, to decide
where the traps stand, and after that a trap is arithmetic on `world.tick` with a
flat damage number and **no crit or evasion roll**. This runs one seeded fight
with a trap chewing on the hero the whole time and one with none, and demands the
damage the hero *dealt* comes out identical.

Read the assertion carefully, because it claims less than it looks like it does.
Traps absolutely change how a fight goes — the hero is poorer in health and gets
shoved around, and that is the feature. What is pinned is the *sequence of dice*,
which is what makes `"enabled": false` in `data/hazards.json` a bit-for-bit
rollback rather than an approximate one.

### `test_rooms.py::test_the_door_the_bot_takes_clears_the_fixture_by_a_margin`

`test_the_reference_bot_walks_past_every_fixture` walks the bot through a room and
asserts it touched nothing, which is the thing that actually matters — the fountain
that a first draft let it use flipped a whole run from won to lost, and the losing
run reached the stage it died on with *more* health than the surviving one.

But that test passes identically at one pixel of margin and at fifty. So its
companion measures the margin: the perpendicular distance from the fixture to the
straight line the bot walks, in pixels, against the reach it would use one at. Over
all four walls a room can be entered through, because the room turns with the run
now — a layout that clears the fixture from the west and shaves it from the north
would go on being measured for as long as nobody walked out of a south door.

Worst case is the east approach at 45.5px against a reach under 15. **When a
behavioural test and a numeric one disagree about how close something came, the
numeric one is the one that catches the change before it breaks anything.**

### `test_save.py::test_a_restored_stage_is_the_stage_that_was_saved`

A save records a campaign index, a seed and a health; the arena is **rebuilt**
from those rather than serialised. So the whole feature rests on the rebuild
being identical, and if it is not, loading a run hands the player a different
fight wearing the same stage number. There is no symptom: the room is simply not
where they left it, and every number on the HUD is still plausible.

Asserted twice over, because the two halves fail differently. The entity list
catches a world built from the wrong level, seed or class. Its companion,
`test_a_restored_run_draws_the_same_dice`, catches the half a body comparison
cannot see — two worlds can hold identical entities and diverge from the first
swing if their generators are not in the same place, and **all three streams**
have to match or the split that protects the damage rolls is not being restored.

The same shape as the two RNG tests above: run it twice and demand equality,
rather than checking a handful of fields somebody thought of.

---

## Known-bad cells

A test that fails for a reason nobody is fixing today is recorded, never deleted
and never commented out.

```python
#: Cells known to fail, and why. Deleting an entry re-arms the check.
UNTUNED_STAGES = {
    ("magician", 11): (
        "the Magician clears stage 12 (The Terraces) on 2/3 seeds. Open balance "
        "work -- see UNTUNED_STAGES for what has been ruled out"
    ),
}
```

**Both dictionaries are empty today**, and the entry above is what one looked
like — the Magician, whose two cells stood for long enough to accumulate four
recorded dead ends before the fifth attempt closed them. The comment block above
them in `test_playthrough.py` is kept as the record of that, which is the shape
this section is really arguing for: the value was never the marker, it was the
reason string growing a paragraph every time somebody tried something.

Three properties make this work:

- **`strict=True` is the whole point.** A non-strict xfail that starts passing
  reports XPASS and nobody notices. Strict means the day it starts passing, the
  suite goes red and somebody has to decide: was it fixed, or did the test rot?
- **The reason string is the documentation**, and it appears in every run's short
  summary. It says what has been *ruled out*, not just that something is wrong.
- **The count is the gate.** "Exactly *N* xfails, the same N" is the acceptance
  criterion for any change to this repo, and **N is zero today**. A new one
  appearing is as much a failure as a regression, and it catches the class of
  change that breaks something without breaking an assertion. Zero is the
  strongest version of the gate rather than the end of it: with nothing on the
  list, any xfail at all is a new one.

> [!NOTE]
> **It was three until the campaign doubled, and the third one was removed by
> being fixed.** `test_twitchiness_is_not_skill` was xfailed because the
> artifact it pinned had faded — at twenty stages both policies finished 6/6 and
> the strict `>` failed. At forty stages the twitchy policy finishes **0/6**,
> five of the six runs ending on stage 25, so the assertion holds again and the
> marker came off.
>
> That is the strict xfail working exactly as designed. It went red the day the
> claim became true, forced the question *was it fixed or did the test rot*, and
> the answer was "fixed". Two hundred new grid cells were added in the same
> change and every one of them was tuned rather than recorded — a fourth entry
> would have been the first crack in the only rule keeping this suite honest.

One test per grid cell rather than a loop over all of them: a loop stops at the
first failure and hides everything after it, so one class failing three stages
would surface as an intermittent run-level flake instead of three named cells.

### A failing cell tells you which kind of failure it is

The grid assertions call `why_not()` in their message, which replays the failing
seeds and reports whether the hero **died** or **ran out of ticks while healthy
with something still untouched**. Those look identical in a win count and are
nothing alike: the first is a balance question, the second is an enemy parked
where nothing reaches it, which no amount of tuning will fix. Three late stages
shipped with the second fault and cost an afternoon of tuning the wrong dial.

It is inside the assertion message, so Python only evaluates it when the
assertion has already failed — the hundreds of passing cells pay nothing.

### None currently recorded

| Test | Why |
| --- | --- |
| — | — |

The list was these two until the Magician was fixed:

| Test | Why it was there |
| --- | --- |
| `test_every_stage_is_clearable_by_every_class[magician-stage12]` | cleared The Terraces on 2/3 seeds |
| `test_every_class_can_finish_the_campaign[magician]` | completed 1/3 runs, dying on stage 12 |

Both were the Magician and both were in acts I–IV. Neither moved when the
campaign doubled — the second half cannot help a class that dies on stage 12 —
and neither moved for any of the four dials tried on damage, health and
commitment. What closed them was two numbers nobody had looked at: the bolt's
`projectile_speed` and `projectile_radius`. **The bolt was missing**, at a hit
rate near half against the Archer's two thirds, and every dial tried before it
was downstream of a shot that connects. See
[Balance](balance.md#the-magician-was-missing).

> [!NOTE]
> **This used to carry a warning that both entries would `XPASS` the day
> levelling was switched on**, and that whoever raised `xp_base` would have to
> re-decide them. That particular hazard is gone with the entries — but the
> general one is not, and it is worth restating in the form that outlives them:
> a cell recorded as unclearable that starts clearing is a *failure* under this
> policy, not a quiet win, because the fix arriving by way of a global power
> increase is exactly the thing worth being told about rather than absorbing.
> Whoever raises `xp_base` still re-baselines all 280 cells. See
> [Balance](balance.md#the-instrument-can-spend-now-the-dial-is-still-at-zero).
Extending the run made the diagnosis sharper, though: across six seeds the
Magician's losses landed on stages 12, 12, 17 and 18 and **raising its
between-stage heal by half changed none of them**, which ruled the run layer out.
That was read at the time as pointing back at commitment. It pointed one step
further than that — past commitment to whether the bolt arrived at all — and the
heal finding is still correct and still the reason `heal_between_stages` is not
the Magician's lever.

## Adding a test

Anything in `core/` or `game/` is plain arithmetic — build a `World`, step it a
known number of ticks, assert on what you find. No window, no clock, no input
device. `tests/helpers.py` builds the arena: a known level, a hero at a known
spot, enemies exactly where the test put them, and a seed.

**It loads the real bestiary, never invented stats.** `data/entities.json` and
`data/weapons.json` are what the tests fight with, so a test failing after a
tuning change is telling the truth about the game rather than about a fixture.

Render tests draw to an offscreen surface and read pixels back. They are the only
ones that touch pygame, and the only ones that care that conftest set the dummy
driver.
