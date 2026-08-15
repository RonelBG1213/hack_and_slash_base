# Testing

```sh
python -m pytest              # 429 tests, headless, no window
python -m pytest tests/test_loot.py
python main.py --smoke        # pixel fidelity: every sprite upscales with hard edges
```

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
| `test_playthrough.py` | 111 | the [balance brackets](balance.md) and the 5×20 class×stage grid |
| `test_run.py` | 30 | carry-over: health, gold, banking across stages |
| `test_render.py` | 29 | drawing, the HUD, the shop panel — headless |
| `test_loot.py` | 28 | the gold formula, rarity weights, the sweep, the RNG split |
| `test_entities.py` | 21 | content validity: levels, boss weapon order, sprite scale |
| `test_collision.py` | 20 | movement against walls, separation, swept paths |
| `test_actions.py` | 19 | the WINDUP → ACTIVE → RECOVERY state machine |
| `test_ai.py`, `test_boss.py`, `test_sim.py` | 17 each | brains, the boss positional brain, one tick |
| `test_combat.py` | 16 | hit resolution and damage rolls |
| `test_campaign.py` | 15 | act structure, stage ordering, playability |
| `test_shop.py` | 14 | prices, caps, refusal when short |
| `test_level.py` | 13 | tiles, solidity, spawns |
| `test_effects.py` | 11 | that the feel pass changes nothing |
| `test_skills.py` | 11 | slot indices and the cooldown contract |
| `test_atlas.py` | 9 | data and art agree about which sprites exist |
| others | | vectors, camera, spatial hash, level IO |
| `test_architecture.py` | 1 | **the rule the project rests on** |

## The three tests that are load-bearing

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
guards. See [Architecture](architecture.md#two-random-streams-not-one) for why a
single shared generator would have invalidated every recorded number without
anything failing.

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

Three properties make this work:

- **`strict=True` is the whole point.** A non-strict xfail that starts passing
  reports XPASS and nobody notices. Strict means the day it starts passing, the
  suite goes red and somebody has to decide: was it fixed, or did the test rot?
- **The reason string is the documentation**, and it appears in every run's short
  summary. It says what has been *ruled out*, not just that something is wrong.
- **The count is the gate.** "Exactly three xfails, the same three" is the
  acceptance criterion for any change to this repo. A new one appearing is as much
  a failure as a regression, and it catches the class of change that breaks
  something without breaking an assertion.

One test per grid cell rather than a loop over all of them: a loop stops at the
first failure and hides everything after it, so one class failing three stages
would surface as an intermittent run-level flake instead of three named cells.

### The three currently recorded

| Test | Why |
| --- | --- |
| `test_every_stage_is_clearable_by_every_class[magician-stage12]` | clears The Terraces on 2/3 seeds — open balance work |
| `test_every_class_can_finish_the_campaign[magician]` | completes 1/3 runs, dying on stage 12 both times |
| `test_twitchiness_is_not_skill` | the artifact it pinned has stopped holding — both policies now finish 6/6, so the strict `>` fails. The assertion message asks the right question (*reconsider which policy is the reference*), so it is a live question rather than a broken test |

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
