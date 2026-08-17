# Balance

```sh
python tools/balance.py                          # the reference class
python tools/balance.py --class all --seeds 8    # every starting class
python tools/balance.py --class advanced         # every class they promote into
python tools/balance.py --class sage --stage 33  # one class, one arena
```

Runs reference bots over many seeds and prints where the game sits. The point of
this document is that **numbers here are either measured or explicitly flagged as
guesses**, and the flag lives in the data file next to the number.

---

## The brackets

Two, because they fail independently — a run can be unwinnable while every stage
is fine alone (the heal is too small), and every stage can be fine while the run
never gets tense (the heal is too large). Plus a ceiling.

| | must | currently |
| --- | --- | --- |
| **every stage**, entered at full health | clear on every seed | 6/6 each, 4–39s |
| **whole run**, health carrying | clear on every seed | 6/6, ~17min, worst finish 53/115 |
| **face-tank** — walks in swinging, never disengages | **lose every run** | 0/6, dying on stage 2–3 |

The run figures are the Knight promoting into the Dark Knight, which is what a
run *is* now — the fork is compulsory, so there is no such thing as a forty-stage
run by a base class, and `tools/balance.py` will not measure one. Ask it for
`--class knight` or `--class dark_knight` and you get the same run either way.

Only the floor and the game is unfair; only the ceiling and there is no game.
`tests/test_playthrough.py` pins all three, plus **two** class×stage grids.

### Two grids, because there are two heroes

A stage is not hard in the abstract. It is hard *for the hero that fights it*,
and which hero that is changes exactly once, at `jobs.PROMOTION_STAGE`.

| Grid | Classes | Stages | Seeds |
| --- | --- | --- | --- |
| base | the 4 starting classes that are not the reference | 1–20 | 3 |
| advanced | all 10 promoted classes | 21–40 | 2 |

Sweeping a base class over stage 30 measures a matchup the game cannot produce
— the fork is compulsory and twenty stages behind by then — so every failure it
reported would be a fiction. `tools/balance.py` refuses it for the same reason.

Two seeds on the advanced grid rather than three: a promotion doubles the roster,
so ten classes over twenty stages is already two and a half times the base grid.
What that costs is on record — see the note on `ADVANCED_SEEDS`.

**None of these numbers include loot.** The bot never buys anything and never
detours for a pickup, so every figure above measures the same game it measured
before the shop existed — which is the point: the [loot layer](loot.md) was added
on top of a tuned game without moving a cell of it. The cost is that the shop's
own numbers have no instrument behind them. Teaching `autoplay` to spend gold
would give you one, and would stop the grid being a fixed reference the same day.

---

## Findings

Four things the measurement overturned. That is what it is for.

### Reaction time is not what decides these fights

Across slow and moderate reactions the outcome barely moves — rolling costs uptime
and lengthens a fight, so reacting sooner does not obviously pay. What separates
winning from losing is **disengaging when hurt**, which is why the ceiling bracket
is a hero that refuses to.

Forty stages sharpened this rather than changing it. The ladder over a whole run:

| reaction | runs won | median finish hp |
| --- | --- | --- |
| perfect (0 ticks) | 0/6 | — |
| sharp (12) — *the reference* | 6/6 | 62 |
| sloppy (24) | 5/6 | 81 |
| asleep (40) | 6/6 | 99 |

A hero that reacts to nothing at all finishes as often as the reference and ends
with more health, because it spends none of the fight rolling. A hero that reacts
to everything finishes none. The reflexes are not the axis; the disengaging is.

### The between-stage heal is per class, and it is per *half* as well

The recorded finding that these numbers cannot be scaled from one value has held
up twice now. Extending the campaign broke the run bracket while every stage
still cleared on its own — the exact signature of a heal too small to sustain a
run — and the fix was not a global multiplier:

| line | heal, acts I–IV | acts V–VIII | why |
| --- | --- | --- | --- |
| Knight | 56 | **84** | 1/6 runs at 56, 6/6 at 84 |
| Rogue | 38 | **60** | 1/6 → 4/6; the two seeds still lost die in the first half |
| Archer | 30 | 30 | 6/6 unchanged — fights at range and arrives healthy |
| Magician | 46 | 46 | every loss is in acts I–IV; +50% moves none of them |
| Priest | 62 | 62 | both losses are on stage 20, same reason |

Two lines needed half again as much and three needed nothing, which is the same
shape the base heals have: what a class needs back depends on how much damage it
takes to clear a stage, not on the size of its health bar.

The constraint that survived from when promotion was a capstone: **the two
branches of a class always share this number.** A tier may heal more than the
tier below it; a branch may never heal more than its twin, or the fork becomes
partly a decision about healing and "the healing one" eats half the roster.

### A zero-tick reaction is an artifact, not skill

A hero answering every telegraph on the tick it opens rolls perpetually against
something winding up or swinging half the time — the boss — and never swings back.
It loses 7 of 8 runs where the twelve-tick policy wins all 8. So the reference
hero is the twelve-tick one.

That was invisible until there was a boss to expose it, and it is the reason to
distrust any single bot as a stand-in for a player.

**It faded and then came back, which is worth more than either reading alone.**
At twenty stages the gap closed — both policies finished 6/6 — and the test that
pinned it was recorded as a strict xfail with the question *reconsider which
policy is the reference* attached. At forty stages the twitchy policy finishes
**0/6**, and five of its six runs end on stage 25, the first boss past the fork.
Four more bosses is four more chances to prove the point, so the artifact scales
with exactly the thing that causes it. The xfail came off.

> Treat both findings as cautions rather than verdicts on the dodge: these bots
> have perfect information and only the crudest sense that pillars exist.
> Measured, not settled.

### The enrage threshold is a fraction, so boss health barely affects difficulty

Halving a boss's HP does not halve the damage it deals you: it spends the same
*proportion* of a shorter fight enraged. Both later bosses were tuned by damage in
the end, after health changes moved the win rate by nothing at all.

### Ranged escorts do not work on a boss stage

A bowman never becomes the nearest thing in the room, so it is never what you are
fighting, so it never dies — a damage tax for the length of the fight with no
answer available. The act III boss stage was drafted with two of them and was
unwinnable on every seed. Every boss stage is escorted by melee now, which is a
standing constraint on level design rather than a bug that got fixed.

### An enemy outside its own aggro radius is a stage that cannot end

Not a balance finding — a level-design one, and the most expensive hour of the
acts V–VIII pass.

Several late stages failed for several classes with the hero at 60–100 health and
the tick limit reached. Every table read it as a difficulty problem, and three
rounds of enemy tuning moved it around without fixing it. The cause was a grunt
that had **never moved from its spawn tile**: parked on the top row of a
thirty-tall arena, more than its 220px aggro from anywhere the hero's route
went. It never engaged, so it never died, so the stage never ended.

The same shape twice over, in two disguises:

- **A ranged enemy in a corner pocket** behind the last pillar. An `archer` brain
  with no line of sight does not shoot, so it never becomes the nearest thing in
  the room, so nothing goes to it.
- **Anything on an extreme row.** In a thirty-tall arena, row 3 is twelve tiles
  from the middle band the hero actually walks — 192px against a grunt's 220px
  aggro. It engages only if the player happens to pass near its column.

Both are the no-pathing limit wearing a costume, and both read as balance
failures in every instrument the project has. The tell that distinguishes them:
**the hero is healthy and something is still at full health.** If a stage fails
that way, count what is alive before touching a single number.

Placement fix, not a tuning one: keep spawns inside the band the hero traverses,
and keep ranged enemies out of pockets.

### A ranged enemy at the far end of a big room is a damage tax, not a fight

The sibling of the finding above, and the one that survives after it is fixed.
This one is a real balance effect rather than a broken stage, and it looks
almost identical in a table.

Every late stage that still failed after the placement pass failed the same way:
the hero **died** with one **untouched mage** left standing. A mage at the far
end of a twenty-enemy arena is never the nearest thing in the room, so it is
killed last by construction — which means it shoots for the entire fight while
the hero works through everything between them. It is the same mechanism as the
ranged-escort finding on boss stages, arriving on ordinary stages once the rooms
got big enough and the rosters long enough.

The dial is **where it stands, not what it does.** Moving a single mage from the
far wall into the middle third of the room does not change one number about it,
and it changes how much of the fight it is present for — which is the whole of
its damage output. Fifteen mages moved inward across acts V–VIII.

The general form, worth carrying: *in a game with no pathing, kill order is
decided by geometry, and a ranged enemy's real damage is its damage times how
late it dies.*

---

## If the bracket breaks, reach for durability first

An enemy that dies before its attack cadence lets it swing again applies no
pressure however hard it hits, and that is arithmetic rather than taste — at the
numbers here a grunt lives about 46 ticks of contact against a 65-tick gap between
its swings, so it gets one attack off and no more.

In order:

1. **Durability** — how long it survives contact.
2. **Count and placement** — `tools/make_level.py`.
3. **Cadence** — `PAUSE_AFTER_ATTACK` in `game/ai.py`.
4. **Enemy damage and hero HP, last.** Raising damage makes one mistake lethal,
   which is a harsher game rather than a tighter one.

---

## What is not measured

Three holes, all deliberate and all stated where somebody will trip over them.

**The thirty-five attacks.** The reference bot plays light-only, which is what
keeps every recorded number meaning what it meant when it was recorded. It cannot
see the neutral, heavy or ultimate slots — and because an advanced class inherits
its light, promoting does not widen what the bot can see. So the ten advanced
classes are measured (their health and their bodies, against acts V–VIII) and
their twenty attacks are not.

That has a consequence worth stating plainly: **acts V–VIII are tuned to be
clearable with the inherited light attack alone.** A player using the new heavy
and ultimate has an easier time than the grid says. That is the intended
direction — the new kit should feel like a reward rather than a requirement — but
nobody has measured how much easier. `autoplay.skilful` presses all four slots
and exists to answer exactly that question.

**The shop.** `autoplay` never buys. See [Loot](loot.md#what-is-measured-and-what-is-not).

That hole got one shelf deeper with the **Boots**, and the depth is worth being
precise about, because the Boots are the first good that touches what a class
*is* rather than a `Run` integer. The grid is still provably unmoved — the bot
buys nothing, so `move_speed` is zero on every body in every sweep, and
`sim._walk_speed` returns the type's own number at zero rather than multiplying
it by one. What is unmeasured is not whether the Boots moved the recorded
numbers (they cannot) but **whether +20% walking speed is a sensible thing to be
able to buy**, in a game with no enemy pathing where outrunning a crowd is the
hero's main answer to one. The cap is set on that reasoning rather than on a
sweep.

Both are the same trade, taken twice: the instrument stays fixed so the grid stays
comparable, and the price is that new systems ship unmeasured and say so.

**The attribute layer and levelling, taken a third time — and this one is
different in a way that matters.** Eight attributes and a level-up system now
exist ([Limits](limits.md#the-attribute-layer)), and they ship with `xp_base: 0`
so that every number on this page still measures the game it measured. The
structural proof is `test_neutral_attributes_reproduce_todays_arithmetic`, which
settles in milliseconds what a sweep would take minutes to suggest.

The difference from the shop is worth stating, because it changes what has to
happen next rather than only what is unknown. Gold is optional — a player might
genuinely not spend it, so a bot that never buys is *a* player, just a frugal
one. **Points are not optional.** Nobody reaches a boss holding nine unspent
levels. So the moment `xp_base` goes above zero, a sweep run by the current
`autoplay` stops measuring an under-equipped hero and starts measuring a hero
nobody would ever play, and it reports the gap in the same units as difficulty.

That is precisely the [flanker demon](#findings) finding, arriving from the
other direction: there, the instrument lacked a behaviour the *enemy* targeted;
here it lacks a behaviour every *player* has. Same lesson, and the same order of
operations — **teach `autoplay` to allocate first, re-baseline the grid second,
tune the curve third.** Turning the dial up before that produces a wall of
plausible-looking numbers that mean nothing.

## Known-bad cells are recorded, not deleted

`UNTUNED_STAGES` and `UNTUNED_CAMPAIGNS` in `tests/test_playthrough.py` map a cell
to a reason and produce a strict xfail. See [Testing](testing.md#known-bad-cells)
for the policy and why the *count* is the gate.
