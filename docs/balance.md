# Balance

```sh
python tools/balance.py                          # the reference class
python tools/balance.py --class all --seeds 8    # every starting class
python tools/balance.py --class advanced         # every class they promote into
python tools/balance.py --class sage --stage 33  # one class, one arena
python tools/balance.py --allocate spread        # ...with a hero that spends its levels
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
| **whole run**, health carrying | clear on every seed | 6/6 with `hazards.enabled: false`; **see the trap finding below** |
| **face-tank** — walks in swinging, never disengages | **lose every run** | 0/6, dying on stage 2–3 |

The run figures are the Knight promoting into the Dark Knight, which is what a
run *is* now — the fork is compulsory, so there is no such thing as a forty-stage
run by a base class, and `tools/balance.py` will not measure one. Ask it for
`--class knight` or `--class dark_knight` and you get the same run either way.

Only the floor and the game is unfair; only the ceiling and there is no game.
`tests/test_playthrough.py` pins all three, plus **two** class×stage grids.

> [!IMPORTANT]
> **The three brackets are not equally exposed to the rooms between the stages,
> and the difference is structural rather than lucky.**
>
> The class×stage grid **cannot see a room at all.** `_stage_world` builds a
> `World` straight out of `campaign()[index]` at full health, and a reward room
> is not in `campaign.stages` — so no cell of either grid can reach one. That is
> a fact about the code, not a result that was checked. (It was written when two
> per-stage xfails were recorded; there are none now, and the argument is the
> same one for every cell.)
>
> The **run-level** bracket and the **face-tank ceiling** do not see one either,
> and that took a second attempt to arrange. `autoplay` walks from a room's
> entrance to a door and touches nothing on the way — so no number in
> `data/rooms.json` reaches any bracket, and the run-level figures are
> byte-identical to the ones recorded before rooms existed: 24900 / 24664 for the
> Knight line, cell for cell.
>
> **That survived the rooms learning to turn**, which is the strongest evidence
> the arrangement is structural. The doors moved from a column on the far wall
> onto the three walls the hero did not enter through, and door 0 went from the
> top door to the left one. Gold, win counts, median health and worst health are
> identical on every row and every cell.
>
> **One column moved, and it is worth knowing which.** The whole-run *duration*
> dropped by exactly 73 game-seconds — 1171 → 1098 skilled, and the same −73 on
> every reaction-ladder row including the one that wins a different number of
> runs. A constant rather than a spread, which is what tells you it is not a
> difficulty change: door 0 is now 10.8 tiles from the entrance where it was
> 20.4, so the bot's walk through each of the thirty-nine rooms roughly halved.
> A sweep compared against an older one will show it, and it means nothing.
>
> **The first draft had the bot use the fixture, and it cost a whole run.** Three
> of the four rewards were inert to it anyway — it never buys, never allocates a
> point, never spends gold — so the fountain was the only one that did anything.
> Over twelve seeds it flipped one run from won to lost, and the trace is what
> settled it: **the losing run arrived at the stage it died on with more health
> than the surviving one** (108 against 99). Not a difficulty change. Extra
> health put the hero somewhere slightly different on stage 15 and thirty-nine
> stages of a deterministic fight amplified it.
>
> The general form, which is the third time this project has hit it: **a
> measurement that perturbs the thing it measures reports its own perturbation in
> the same units it reports difficulty.** The demon's flanker brain was the first
> and `xp_base` is the second. The answer each time has been to make the
> instrument not touch the feature, and to say plainly what that leaves
> unmeasured — see [Limits](limits.md#nothing-measures-which-door-is-worth-taking).

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

### The difficulty tiers, and what the first sweep of them found

Knight, forty stages, four seeds, `tools/balance.py --class knight --seeds 4
--difficulty <tier>`. One dial: a per-mille multiplier on damage the hero takes.

| tier | `incoming` | every stage alone | whole run | face-tank | worst hp |
| --- | --- | --- | --- | --- | --- |
| Forgiving | 700 | 40/40 at 4/4 | **4/4** | 0/4 | 77 |
| Normal | 1000 | 40/40 at 4/4 | **2/4** | 0/4 | 61 |
| Relentless | 1300 | 40/40 at 4/4 | **0/4** | 0/4 | — |

Three things, and the middle one is the important one.

**The ceiling holds on every tier, the gentlest included.** A hero that walks in
swinging finishes no runs at 700 either. *Only the floor and the game is unfair;
only the ceiling and there is no game* — a tier that made walking in swinging
work would be the absence of a game rather than an easier one, and it is the one
bracket a difficulty setting can quietly destroy. Pinned by
`test_the_ceiling_holds_on_the_easiest_tier_too`, against whichever shipped tier
is gentlest rather than against a name, so adding a softer one below cannot
slide out from under it.

> [!warning] The run-level floor was **already red before any of this landed**
> Two tests, both failing on `main` with all of this work stashed, both verified
> that way round deliberately — a new feature is the obvious suspect and was the
> wrong one:
>
> | test | reads |
> | --- | --- |
> | `test_the_floor_a_skilled_hero_finishes_the_whole_run` | 2/6 |
> | `test_every_class_can_finish_the_campaign[priest]` | 2/3 |
>
> The Knight sweep agrees: 2/4 whole runs at Normal, worst run ending on stage
> 20. **These are the only two reds in the suite**, and neither is an xfail —
> `UNTUNED_STAGES` and `UNTUNED_CAMPAIGNS` are both still empty, so the
> acceptance criterion is unchanged at zero.
>
> Every one of the forty stages clears 4/4 entered at full health, on all three
> tiers. So this is not a wall in the campaign; it is attrition — the heal
> between stages no longer sustaining a run — which is precisely what the tool's
> own verdict line says and what the two brackets were separated to
> distinguish. It is open, and it is not a difficulty problem.

**Which is also why Relentless cannot be read yet.** 0/4 at the run level is a
tier stacked on top of a bracket that was already failing, so the number says
nothing about whether 1300 is the right dial — it says the run-level floor is
broken and 1300 does not repair it. Forgiving at 700 *does* repair it, which is
a fact about the size of the attrition gap rather than a recommendation.

Both outer tiers stay marked unmeasured in `data/difficulty.json` and on the
select screen. What this sweep settles is the per-stage bracket and the ceiling;
what it cannot settle is anything run-level, until the floor is green again.

### A lateral disengage moves the run bracket and not one per-stage cell

Knight, four seeds, `--policy reference` against `--policy evasive`. The only
difference between the two instruments is which way the hero walks when it gives
ground: straight back, or leaned forty degrees off the line.

| | per-stage, stages 1-20 | whole run | worst run ended | median hp | worst hp |
| --- | --- | --- | --- | --- | --- |
| reference | 20/20 cells at 4/4 | 2/4 | **stage 20** | 62 | 61 |
| evasive | 20/20 cells at 4/4 | 3/4 | **stage 38** | 59 | 56 |

**Not one of the twenty per-stage cells moved** -- same win rate and the same
worst-hp figure in every one. And the run-level bracket moved a long way: the
worst run of the set now ends eighteen stages later than it did.

The two readings are not in tension, they are the two brackets doing the job they
were separated to do. A stage entered at full health rarely takes the hero below
`CAUTIOUS_BELOW`, so the retreat branch is hardly reached and the two policies
decide the fight identically -- which
`test_a_healthy_fight_is_decided_identically_by_both_policies` pins directly. A
*run* is where health carries, where the hero spends whole stages under that
threshold, and where the shape of the retreat compounds.

Note the direction of the health columns: the sidestepping bot finishes with
slightly *less* health, not more. It is not taking fewer hits per fight. It is
ending up somewhere survivable at the end of a run, which is a different thing
and is the thing the run bracket measures.

> [!important] What this costs to promote is now known, and it is less than feared
> The recorded worry was that teaching the bot a lateral disengage "moves the
> grid on the day it lands". Measured: it moves **no** cell of the per-stage
> grid and it moves the run-level bracket. So promoting it into the reference is
> a re-baseline of the run rows and nothing else -- much cheaper than a 280-cell
> re-tune, and a decision that can now be taken on evidence.
>
> It is still not taken. `Evasive` ships as a second instrument, the reference is
> untouched, and both those facts are structural rather than careful --
> `test_the_evasive_policy_leaves_the_reference_untouched` fails if the override
> ever spreads to a second method.

### The demon was not an instrument artifact after all

The recorded position was that the `flanker` demon's failures measured *"the
reference bot has no answer"* rather than *"the fight is too hard"* -- the brain
closes on an arc precisely to defeat a straight-line retreat, and the reference
bot has no other kind. The stated unblocker was to teach the bot to sidestep.

That is now built (`autoplay.Evasive`, `--policy evasive`), so the excuse is
testable. Assassin, stage 39, eight seeds, one demon standing where a revenant
stood -- the sharpest cell of the original attempt:

| | no demon | one demon |
| --- | --- | --- |
| reference | 8/8, worst 23 | 5/8, worst **4** |
| evasive | 8/8, worst 23 | 4/8, worst **13** |

**The sidestep does not recover the cell.** It buys real survivability -- the
worst case more than triples and the median goes 23 to 34 -- so the instrument
genuinely *was* partly blind. The blindness was simply never the size of the
failure. The creature is too strong there on its own merits.

Stage 36 says the harness is driving the same thing the original sweep drove: at
`flank_degrees` 35 it reads 8/8 worst 28, reproducing the recorded row exactly,
against 8/8 worst 44 with no demon. Evasive reads 8/8 worst 26 -- no rescue
there either.

So the demon still spawns nowhere, and the dead-end entry that said *"re-propose
it after `autoplay` can sidestep, and not before"* has been satisfied and
answered: the bot can sidestep, and the answer is still no.

> [!warning] Two things this does **not** settle
> `EVASIVE_DEGREES` is 40 and unswept. The flanker's measured 35-to-55 cliff is
> the *enemy's* approach and says nothing about the hero's disengage, so a
> different lean could read differently -- sweeping it is the first thing the
> next attempt should do.
>
> And the run-level floor was red on `main` when this was measured, so nothing
> run-level in this section is readable. Every figure above is per-stage,
> entered at full health, which is the bracket that was green.

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
| Magician | 46 | 46 | every loss was in acts I–IV; +50% moved none of them, which is what ruled the heal out as the Magician's lever |
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

### A charge speed is a class-specific dial, and health is not

The acts IX–X pass produced the sharpest instance of the finding above it. **The
Unmade** — stage 50 — cleared 6/6 for nine of the ten advanced classes and **1/6
for the Dark Knight**, which died every time with the boss around fifty health
from dead. Close enough to read as a health problem, and it was not one:

| change | Dark Knight | the other nine |
| --- | --- | --- |
| as drafted — hp 220, charge 18 at speed 4.0 | 1/6 | 6/6 each |
| hp 220 → 205 | 1/4 | unmoved |
| hp 220 → 195 | 2/4 | unmoved |
| hp 220 → 195 *and* the fan 12 → 10 | 2/4 | unmoved |
| charge damage 18 → 14 | 6/6 | unmoved |
| **charge_speed 4.0 → 3.5**, health and damage untouched | **6/6** | unmoved |

Two of the six rows fix it and both of them are the charge, which is what makes
this a finding rather than a lucky number: the fight was never the health bar.

The reason is the class rather than the boss. The Dark Knight is the fastest body
in the game on the least health of the two Knight branches, so it fights this one
from *inside* the sweep — and a charge that crosses that distance faster than it
can leave is not a telegraph, it is a tax. Every slower class was already
answering the same charge comfortably.

What generalises: **a dial that interacts with hero speed will show up as one
class failing and nine passing, and health never will.** A statline that is wrong
for one class looks exactly like a stage that is slightly too hard for everyone,
and the grid is the only thing that tells them apart. The damage stayed at 18 —
a charge that hits for less is a smaller mistake, a charge that arrives slower is
a mistake you are allowed to see coming, and only one of those is the fight.

### Acts IX and X: what the extension to fifty cost

Ten new stages measured on the ten advanced classes. The first pass was **17
failed cells**, all of them in four stages and one boss, and every fix was
placement or durability. None was a hero number:

| stage | what failed | what it was | what fixed it |
| --- | --- | --- | --- |
| 43 The Long Gallery | Hunter, Magic Archer, Sage, Wizard at 0/2 — every ranged class, no melee one | 48×20 with a pillar row down the middle | 48×24, six pillars instead of eight |
| 44 The Press | both Priest branches at 1/2 | 17 bodies in 42×24 | 16 in 44×26 |
| 47 The Long Vigil | both Knight branches, both Priest branches | a third revenant and a second stalker | revenant out, stalker → grunt |
| 49 The Threshold | Dark Knight, Sage, Wizard, both Priests | 22 bodies | 20, taking out a beastman and the hellhound rather than two grunts |
| 50 The Unmaking | Dark Knight at 1/6 | charge speed, above | 4.0 → 3.5 |

Stage 43 is the one worth keeping. Four classes failed it and they were **exactly
the four ranged ones**, which is not a difficulty reading at all — a shallow room
with pillars down its centre has no lane long enough to shoot along. A win rate
split that cleanly along a class *property* is a shape problem, and no amount of
thinning the roster would have found it.

After the pass: **400/400** across ten classes × ten stages × four seeds.

### The run bracket got longer, not harder, and that is worth telling apart

Every one of the fifty stages clears from full health. The **run** bracket does
not, and the numbers say why. Six reference runs per class, promoting on the
first branch, recording the stage each loss happened on:

| class | branch | where the losses fell |
| --- | --- | --- |
| Knight | Dark Knight | 20, 20, 37, 38, **50** |
| Rogue | Assassin | 14, 22 |
| Archer | Hunter | **42** |
| Magician | Sage | none — 6/6 |
| Priest | Battle Priest | 20, 20, 34 |

**Six of the eight losses are on stages the extension did not touch**, and three
of them are stage 20 — the Sovereign, fought by a base class on the last stage
before the fork. That is the shape of a run bracket that was already thin, not
of ten stages that are too hard: a longer campaign is more chances to lose a run
you were always at some risk of losing, which is the same mechanism the twitchy
policy demonstrated when the artifact faded at twenty stages and came back at
forty. The suite reflects that — the run-level tests were failing before this
work as well, and the extension added two more.

Two things this does *not* license concluding. It is not evidence that acts IX
and X are correctly tuned in a run — nothing here measures that. And it is not
evidence that they are gentle: the two losses that are in the new range are at
42 and 50, which is where a run is at its thinnest.

### Traps at depth are the unmeasured half of the last two acts

The per-stage grid builds a `World` without a floor number, so **it measures
every stage with floor-one hazards** — the limitation already on record below,
now with ten deeper floors under it:

| floor | trap damage | count |
| --- | --- | --- |
| 20 | 11 | 3 |
| 40 | 17 | 4 |
| 50 | 20 | 4 |

Count is capped at 4 and stays there, so what actually changed between the old
last floor and the new one is a trap hit costing 20 instead of 17 — a quarter of
the Rogue's health rather than a fifth. Nothing in the curve was touched: moving
`damage.floor_step` would move all forty floors that are already on record, and
that is the one thing the extension was not allowed to do.

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

### The Magician was missing

The hero-side twin of the finding above, and it closed the last two xfails in
the project. The Magician failed stage 12 at 6/12 seeds and finished 1/6 runs
where the other four classes cleared everything; four dials had been tried on it
and recorded as dead ends.

**All four were downstream of a shot that connects.** Damage per hit, health and
recovery all assume the bolt arrives. Instrumenting a stage-12 fight is what
showed it does not:

| | Magician | Archer |
| --- | --- | --- |
| light attack | 15 damage | 9 damage |
| shots per fight | 37–42 | 37–41 |
| **damage landed per shot** | **6.1–8.1** | **5.5–6.9** |
| implied hit rate | ~half | ~two thirds |
| damage taken | 105+ on a loss | 44–64 |
| fight length | 1355–1619 ticks | 1152–1438 |

A bolt worth 15 landing 7 is a bolt that misses half the time. At
`projectile_speed: 3.4` one crossing the 120px `RANGED_PREFERRED` holds is **35
ticks in the air**; a grunt walks 1.05px per tick and has moved 37px — four body
widths — by the time it arrives, and nothing in this game leads a target. The
class was paying the game's longest commitment for a coin flip.

The fix is two numbers in `data/weapons.json`, `projectile_speed` 3.4 → **4.0**
and `projectile_radius` 3.5 → **4.5**, and deliberately nothing else. Damage and
commitment *are* the class — *"the hardest single hit in the game, behind the
longest commitment"* — and neither moves.

| | base grid, 20 stages × 12 seeds | runs |
| --- | --- | --- |
| before | 228/240 — st12 6/12, st14 10/12, st16 9/12, st17 11/12 | 1/6 |
| after | **240/240** | **6/6** |

Sage and Wizard inherit `arcane_bolt` and were swept across all twenty late
stages: unmoved. The other four classes cannot move — neither number is theirs —
which is structural rather than a result that was checked.

**Both numbers, and it is a plateau rather than a spike.** Speed alone leaves
stage 12 at 10/12; radius alone leaves the run bracket at 2/3. Every combination
from 4.5/4.0 upwards scores the same 72/72 on the six tight stages, and the step
below it, 4.0/3.8, falls back to 70/72 — so there is room to tune, in one
direction. 4.0 is the largest value that keeps the Archer's shortbow (4.2) the
faster projectile, which is the Archer's half of the difference between the two
ranged classes.

Two cautions worth carrying:

- **A four-stage screen lied.** The first candidate to score 48/48 on the tight
  stages was `recovery 16 → 12, damage 15 → 13`; swept over all twenty it broke
  stage 3 — the recorded arena — to 7/12 and took runs to 0/6. Lowering damage
  raises commitment whenever it crosses an enemy's hit points: at 13 a bolt can
  no longer one-shot a 14hp bowman or two-shot a 30hp charger.
- **Fixes do not add.** `speed 1.80` and `proj 4.2` each fixed half the problem
  and scored *worse* combined than either alone. The sim is deterministic and
  chaotic; two changes are a third change, not a sum.

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

## Traps, and the limit of the run-level bracket

**This is the most important finding in this file, and it is about the
instrument rather than the game.**

The per-stage brackets hold with the hazard layer at full strength. All 280
class x stage cells pass, `test_every_stage_can_be_cleared` passes on every
seed, the ceiling still refuses the face-tank, and the two strict xfails are the
same two. **No arena in the campaign becomes unclearable because of a trap.**

The two *run-level* brackets do not hold, and they cannot be made to:

| `test_the_floor_a_skilled_hero_finishes_the_whole_run` | 6 fixed seeds, health carrying |
| `test_every_class_can_finish_the_campaign[priest]` | 3 fixed seeds, one class |

Thirteen configurations were swept looking for a setting that keeps them green.
A representative slice, all against the same six seeds:

| bot | damage curve | knockback | runs won |
| --- | --- | --- | --- |
| blind | layer off | — | **6/6** |
| blind | 1 flat | none | **6/6** |
| blind | 1 flat | 2.2 | 5/6 |
| blind | 3 @ 0.03/floor | none | 5/6 |
| blind | 5 @ 0.06/floor | 2.2 | 3/6 |
| steps off traps | 5 @ 0.06/floor | 2.2 | 4/6 |
| steps off, fair placement | 5 @ 0.06/floor | 2.2 | 2/6 |
| steps off, fair placement | 3 @ 0.03/floor | 2.2 | 2/6 |
| steps off, fair placement | fewer traps, cap 2 | 2.2 | 4/6 |

**Read the last four rows.** Halving the damage moved the score *down*. Halving
the number of traps moved it *up* by less than making the placement fairer moved
it down. The score does not track difficulty in any direction — and the only
configuration that scores 6/6 is the one where a trap does one point of damage
and does not move the hero at all, which is a trap layer that is not there.

### Why, and what it means

A run is one deterministic trajectory through forty fights. The run-level
bracket asks whether *that trajectory* survives, on six particular seeds. Any
perturbation — a point of damage, a shove, a sidestep — sends the hero somewhere
slightly different, and thirty-odd stages of deterministic combat amplify it
until a seed that used to win loses, or the reverse.

**This is not a new discovery; it is the fountain finding again, at full size.**
`data/rooms.json` records it: a heal of 15% flipped a whole run from won to lost,
and the *losing* run reached the stage it died on with more health than the
surviving one. The project's answer then was to keep the reference bot from
touching fixtures at all, which is why `autoplay._in_a_room` walks to a door and
touches nothing.

That answer is not available here. A trap is on the floor of the arena, and
there is no version of "walk past it" that leaves the trajectory untouched. So:

> **A fixed-seed, full-run pass/fail is the wrong instrument for anything that
> changes where the hero stands.** It measures a trajectory, and it reports a
> moved trajectory in the same units it reports a harder game.

Two seeds dying at floor 20 — the act IV boss, a stage that carries **no traps
at all** — is the cleanest evidence. Nothing about that fight changed. The hero
arrived at it standing somewhere else.

### What would actually settle it

Not a tuning pass. Either the bracket becomes a *distribution* (win rate over
thirty seeds, with a threshold) rather than six coin flips, or it keeps a fixed
budget and accepts that any new mechanic re-baselines it. Both are real changes
to the acceptance criterion and neither should be made to get a feature merged.

Until then the honest summary of the hazard layer is:

- every individual arena clears, with traps, at full strength — **measured**;
- whether a forty-stage run with traps is *tuned* — **not measured, and not
  measurable by this instrument**.

### What the bot can and cannot see

`autoplay` was taught to step off a trap (`_trap_underfoot`), and that change is
inert when the layer is off — `world.traps` is empty, the branch returns on its
first line, and `test_the_policy_is_untouched_when_the_layer_is_off` pins the
hero's whole path to prove it. So the recorded campaign is measured by exactly
the policy that recorded it.

It is still a poor trap player: it looks half a second ahead, steps out by the
shortest open route, and has no idea whether it is stepping into a second trap
or into a brute. That is deliberate -- it is a floor under the measurement, not
a ceiling. It cannot tell you whether a tell is long enough to read, whether a
blade's track is legible at 1x, or whether being caught feels like a mistake you
made. Those need hands on a keyboard.

One thing it did earn: the bot walked into a blade laid along the row inside the
top wall on stage 28 and spent 198,000 ticks pinned there instead of the 2,500
the stage takes. That trap had open floor on one side and stone on the other, so
being shoved the wrong way held it in place while the blade kept coming back.
`hazards._can_step_off` now refuses that placement outright, and
`test_nothing_is_placed_where_a_body_could_not_step_off_it` sweeps all forty
arenas for it. **The bot is how it was found; it was unfair to a person first.**

## What is not measured

Three holes, all deliberate and all stated where somebody will trip over them.

**The thirty-five attacks.** The reference bot plays light-only, which is what
keeps every recorded number meaning what it meant when it was recorded. It cannot
see the neutral, heavy or ultimate slots — and the neutral is doubly invisible now
that it is a buff, because the skill-using bot skips the slot explicitly rather
than measuring its own attack ordering — and because an advanced class inherits
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
It can now *spend levels* (`--allocate`, below) but still not gold, and the two
are not the same argument: a frugal player is a player, while a player who never
spends a level is nobody.

**Every number in `data/rooms.json`.** The bot walks past all four fixtures, so
nothing measures whether a fountain is worth 15% or 40%, whether a chest pays
enough to matter, whether the shrine's point is the best thing on any wall, or
whether a stall every third floor — plus one after every boss — is the right
spacing.
That is the price of the run-level bracket still being a fixed reference, and it
is the same trade as the shop: an instrument that spends is an instrument that
has stopped being one. See
[Limits](limits.md#nothing-measures-which-door-is-worth-taking).

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

### The instrument can spend now. The dial is still at zero.

The first of those three is done. `play_run_out` takes an `allocate` policy and
`tools/balance.py` takes `--allocate`, so a sweep can be run against a hero that
spends what it earns.

| `--allocate` | what it plays |
| --- | --- |
| *omitted* | spends nothing. **The reference**, and what every number on this page was measured with |
| `spread` | one point into each attribute in turn, round and round |
| an attribute name | every point of a run's budget into that one |

Neither of the two is a player, and that is on purpose in both directions.
`spread` picks no favourite, so what it measures is the **floor** — what
levelling is worth to somebody who spends without thinking about it. `--allocate
max_hp` and its seven siblings measure the **ceiling of one dial**, which is the
question `data/progression.json` needs answered eight times before any of its
prices stops being a guess. A real player is somewhere between, and nothing here
claims to be them.

Three things about the default are worth being explicit about, because they are
what keep this page true:

- **Omitting the flag runs the old code path**, not a policy that behaves like
  it. `allocate=None` is a branch that is never taken, so a sweep without the
  flag is byte-identical to one run before the argument existed.
- **The flag is inert on the shipped table anyway.** `xp_base` is 0, so the
  most spendthrift policy in the module has nothing to spend —
  `test_allocating_is_inert_while_the_table_is_off` pins that. Adding the
  instrument could not have moved a cell, which is exactly why it is a separate
  commit from turning the dial up.
- **Spending is timed to the transition**, where `scenes/play.py` opens the
  panel — not to the level-up. A level earned mid-fight is banked and spent on
  the way out, and after the promotion, because a point in health raises a
  ceiling the class change is about to move. An instrument that spent earlier
  than the game does would measure a hero the game cannot produce, which is the
  same mistake `run_identity` exists to prevent one class-shaped version of.

**What is still not done is the second and third.** Nothing here has been
re-baselined against a levelling hero, so every figure on this page remains a
figure about `xp_base: 0`. Turning the dial up is the commit that invalidates
them, and it should be taken with `--allocate spread` output in hand and the
expectation of retuning. There are no recorded xfails left to be invalidated by
it — the Magician's two came off — which removes a hazard rather than the work.
See [Testing](testing.md#known-bad-cells).

## Known-bad cells are recorded, not deleted

`UNTUNED_STAGES` and `UNTUNED_CAMPAIGNS` in `tests/test_playthrough.py` map a cell
to a reason and produce a strict xfail. See [Testing](testing.md#known-bad-cells)
for the policy and why the *count* is the gate.
