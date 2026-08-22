# Roadmap

What this game does not have that the market it sits in expects, what each
absence costs, and the order to buy them back in.

> [!IMPORTANT]
> **Nothing in this document is measured, and it is the only document here of
> which that is true.** [Balance](balance.md) reports numbers a bot produced.
> [Limits](limits.md) records decisions and the reasoning that was available
> when they were taken. This is a third thing: a judgement about an audience,
> made by reading the code against the games it would sit beside on a store
> page. Treat every ranking below as an opinion with its evidence attached
> rather than as a result, and note that the evidence is all *internal* — what
> the repo contains — while the standard it is held to is external and asserted.
>
> Where a gap here is already recorded in [Limits](limits.md) as deliberate,
> **this document is not overturning that decision.** It is putting a price on
> it. A decision that was correct against the codebase can still be expensive
> against a market, and both facts can be held at once.

---

## Where this sits

A top-down twin-stick brawler with permadeath, a gold economy, reward rooms
between fights, a compulsory class fork and seeded runs. Everything in that
sentence names the roguelite shelf — Hades, Dead Cells, Enter the Gungeon,
Brotato, Halls of Torment — and that is the shelf a player will judge it from.

What is behind the framing is a **fixed fifty-stage campaign**. That gap between
the frame and the thing is the largest single item in this document, and it is
[its own section](#a-seed-does-not-move-a-fight).

What is genuinely strong, stated first because the rest of this document is a
list of absences: the systems depth is already past what most projects on that
shelf ship with. Five classes forking into ten, thirty-five distinct attacks,
ten bosses, six enemy archetypes with nine variants, an eight-attribute layer,
a twelve-piece gear pool, hazards, four seeded RNG streams and a headless suite
of ~1,402 tests holding a measured balance grid. **The gaps below are product
gaps, not engineering ones**, and that is a much better problem to have than the
reverse.

---

## The four things that stop it being a product

These are ordered by perceived-quality gained per hour spent, which is not the
same order as difficulty.

### ~~No sound~~

**Shipped.** The layer was written first and wired second: it arrived complete
in `09bc62c` — cue table, mixer, generator and twenty-one tests — and nothing
imported it, so the game stayed silent through that commit and the one after it
while every document went on saying the tree had no audio in it. Both halves are
in now.

`audio/cues.py` maps twelve of the thirteen `EventKind`s to a named cue and splits
four of them on payload — a blow you land and a blow you take are different
sounds, and so are a coin and a relic. `audio/bank.py` owns the mixer and
sixteen channels. `tools/gen_sfx.py` writes fifteen WAVs from a fixed seed, the
way `gen_art.py` writes the sprites, and they are gitignored for the same two
reasons. `main.py` opens the mixer at the rate, width and channel count the
generator writes, so nothing is resampled between the file and the speaker.

`scenes/play.py` feeds cues from the same drained event list the feel pass
reads — **once, shared**, because `drain_events` empties the queue and a second
call would come back empty — and plays them once per *frame* beside
`effects.tick()`, where `Cues.drain` collapses a stalled frame's fifteen ticks
down to one play per cue. Settings → Sound volume is a 0–10 dial that mutes on
Enter and applies mid-run through the pause overlay.

What it is not, and [Limits](limits.md#no-music-and-no-sound-that-is-not-a-cue)
now carries the same list from the other side: there is **no music**, no boss or
victory stinger, no UI sound on a menu row, and no positional audio —
`bank.play` takes one global level and a cue sounds the same wherever it
happened. Those are the next things here, and none of them is on the critical
path the way silence was.

The reason it was worth doing first is unchanged, and worth keeping written
down. The whole combat feel layer — hitstop, knockback, screenshake, damage
numbers, i-frames on the roll — is a language for telling the player that a hit
connected. Delivered silently, that language reads as a bug rather than as
minimalism: the screen jerks for no reason a player can name.

### Placeholder art

`tools/gen_art.py` paints hard-edged shapes into `assets/sprites.png`, which is
not committed. [Limits](limits.md#placeholder-art) records the swap path: drop
in a PNG with the same cell layout and the game does not care what is in the
cells.

The cost is the one thing a systems-first project is structurally worst placed
to feel. On the storefronts this genre sells through, art is the first and
usually the only thing that decides whether anyone reaches the systems at all.
No amount of tuning is visible in a screenshot.

It is fourth in [the order](#the-order) rather than first, for one reason: it is
the largest cost on this page and the only one that is better spent *after* the
game has proved worth dressing.

### No way to run it without a Python toolchain

No packaging, no icon, no installer, and — by decision — no build step. The
[README](../README.md#quick-start) start path is a virtualenv, a `pip install`
and four generator scripts before `python main.py` — it was three until
`gen_sfx.py` joined `gen_art.py`, `make_level.py` and `make_rooms.py`, which is
the same growth [item 3 of the order](#the-order) prices from the packaging
side.

That is a correct and deliberate development setup. It is not a distribution.
The audience for this genre does not have Python 3.14, and the pygame-ce caveat
in the README is exactly the kind of thing that ends an install attempt.

The absence of a build step is a real asset for the edit loop and should be
kept. What is needed is a *second* path — a one-file executable produced by a
tool that runs over the existing tree — not a change to how the project is
developed. Note that the generated artefacts are the wrinkle — though a smaller
one than this paragraph used to claim. **`levels/` is committed**: all 52 files,
the fifty stages, the campaign manifest and the room template, are in the repo
and `git check-ignore` says nothing about them. Only `assets/` is generated and
ignored, so the packaging step has to run `gen_art.py` and `gen_sfx.py` before
it freezes, and `make_level.py` / `make_rooms.py` are a *developer's* commands
rather than a build's.

### No controller

Verified: no `joystick`, `gamepad` or `controller` reference exists anywhere in
`src/`, `tools/` or `main.py`.

Twin-stick is the control scheme most associated with a gamepad in the whole
action space, and a keyboard-and-mouse-only build is excluded from handhelds
outright. This is a smaller job than it sounds: the `Intent` seam described in
[Architecture](architecture.md) already separates *what the player asked for*
from *what device asked it*, which is precisely the seam a second input device
plugs into. Aim comes off a stick instead of a cursor and nothing under the seam
learns about it.

It pairs naturally with [rebinding](#what-players-will-file-as-bugs), which is
the same refactor seen from the other side — **and that half has now shipped**,
which makes this smaller again than the paragraph above already claimed. The
named actions a pad would bind to exist (`bindings.Action`), the resolution of a
binding to a device event is already isolated in one module
(`scenes/keymap.py`), and `scenes/play.py` reads actions rather than keys. What
is left is a second table of bindings and a stick where the cursor was.

---

## The roguelite it is framed as, and the campaign it is

### A seed does not move a fight

This is the largest design gap in the project and it deserves its own statement,
in the same units the rest of the documentation uses.

Every stage is a hand-written literal in `tools/make_level.py`. Stage 25 is a
`herald` at (32,13), grunts at (20,6) and (20,20), and a `revenant` at (24,13) —
on every run, on every seed, for every player, forever. Across all fifty stages
the enemy counts ramp sensibly (3 to 20, mean 12.2, boss floors at 4), and the
authoring is good. It is also completely fixed.

What the seed *does* move, from `game/world.py` and
[Loot](loot.md): damage rolls, what a kill drops, crit and evasion dice, where
the hazards stand, and what the stall and the shrine put on their shelves. What
it does not move: which enemies, how many, where, in what arena, in what order.

> [!NOTE]
> **This is the direct consequence of a decision the project has taken
> deliberately and repeatedly, and it is a good decision.** The recorded balance
> grid in [Balance](balance.md) is a fixed reference. It is a fixed reference
> *because* the stages are fixed — 280 comparable cells across every change
> since. [Limits](limits.md) documents three separate occasions where a change
> was refused for threatening exactly that property.
>
> So the second run being the first run is not an oversight. It is the price
> already paid for every measured number in this repository. The point of
> putting it here is that the price is paid in the currency the market cares
> most about, and nobody has written that down.

The player-facing version: hour one is a well-tuned campaign, and hour two is
the same campaign. Every game named at the top of this document sells on
run-to-run *difference*, and a player who reaches stage 12 twice has already
seen everything stage 12 will ever be.

**The recommendation is not to make the campaign procedural.** That invalidates
the grid on the day it lands and throws away the project's best property to buy
a different one. See [the order](#the-order) for the alternative.

### ~~Nothing survives a run~~

**Shipped.** `game/unlocks.py` is the first thing that reads the four counters,
and it is built so that reading them still cannot move the grid: an unlock
grants **access** and never numbers, and that is structural rather than a rule
somebody has to remember — there is no `attributes` key in the schema and no
import of `attributes.py` in the module, so a stat grant is not a thing the
loader refuses but a thing the file cannot say.

**Nothing is stored.** What is unlocked is derived from the profile every time
it is asked for, which is `promotes_from`, `variant_of` and `rooms._wall_of` a
fourth time. No schema bump, nothing to migrate, and no unlock state that can
disagree with the scoreboard beside it. `"unlocks": []` in
`data/unlocks.json` is the game exactly as it shipped before — nothing is locked
unless an entry says it is — and that is why the loader deliberately has *no*
two-way "every modifier must be reachable" check in `shop.stock`'s image: it
would make the rollback illegal. A content test makes that claim about the
shipped file instead, which is where it belongs.

Three entries to start: Hard at stage 10, Nightmare at stage 25, and
**Champion's Wake** — the [elite layer](#no-elite-layer) as an opt-in run
modifier — for a run won. The Unlockables screen lists them with what each one
wants, the character select greys a tier it cannot offer and says why, and the
run-end summary names whatever the run just earned. Easy and Normal are never
gated and a test pins it: the cursor opens on the default tier, so a lock in
front of it would strand the screen on a row that cannot start a run.

The paragraph below is the argument that was made *before* it shipped, kept
because it is the reasoning the shape came from.

`game/profile.py` keeps four lifetime counters and its docstring states plainly
that nothing in the sim, in `Run`, or in anything deciding a fight ever reads
one.

That is a coherent position and the docstring argues it well — the day an unlock
hands a run a head start is the day the grid moves. The cost is that **a player
who loses on stage 31 has been given no reason to press New Game.** The
meta-progression loop is the genre's entire retention model: the Mirror, the
cells, the blueprints. Here the reward for a lost run is the counter going up by
one on a screen that describes itself as a stub.

Note the asymmetry that makes this cheaper than it looks. An unlock that grants
a *stat* moves the grid. An unlock that grants **access** — a class, a starting
weapon, a cosmetic, a difficulty tier, a run modifier the player opts into —
does not, because the grid measures a specified class over a specified stage and
is indifferent to how the player got the right to pick it. The first unlocks
should be drawn entirely from the second set, and that is a design constraint
worth writing into the data file when it lands.

### A build is twelve flat numbers

The stall rolls three pieces from the twelve in `data/equipment.json` over five
consumables, each writing into one of the eight attributes in
`data/progression.json`. Rarity scales the magnitude.

Every one of them is a scalar. There are no synergies, no conditional effects,
no piece that changes what an attack *does* — nothing with the shape of a Hades
duo boon or a Vampire Survivors evolution. A run's build is therefore a vector
of eight numbers, and two runs of the same class differ by their magnitudes.

That is why the gear does not generate a story. "I got +12 damage" is not a run
a player describes to somebody else, and the descriptions are most of how this
genre spreads.

### One damage type and no status effects

The fields in `data/weapons.json` are damage, variance, arc, reach, the three
frame windows, knockback, hitstop, cooldown, and the projectile block. `buff`,
`buff_ticks` and `buff_haste` exist, and they are all **self**-buffs on the
neutral slot.

~~Nothing in the game applies a state to an enemy.~~ **The substrate shipped;
the content has not.** `Weapon.inflict` / `inflict_ticks` mirror the buff pair
pointing the other way — that one is granted to the user when the window opens,
this one is applied to the target when a blow is *confirmed*, past the i-frame
and evasion gate, so an avoided blow leaves nothing behind. It lands on
`Entity.status` / `status_ticks`, a fourth `Attributes` addend beside the buff
and deliberately not sharing its slot: `apply_buff` replaces rather than stacks
and `render/hud.py` lights the Q pip off `buff_ticks`, so one slot would mean an
enemy's fire putting out the Priest's Benediction and lighting their skill pip
while it burned.

**Three of the four effects needed no arithmetic at all.** A vulnerability is a
negative `defense`, which `combat.resolve_damage` has always subtracted; a slow
is a negative `move_speed`, which `sim._walk_speed` has always multiplied by —
it needed one clamp, because past -1000 the product turns negative and that does
not stop a body, it *reverses* it. A burn is a negative `regen`, and it is the
one that needed a branch: `_regen` refused negatives, short-circuited at full
health, had no floor at zero and announced no death. It has a sibling now, and
the healing branch is byte-identical so `tests/test_sim.py`'s four regen tests
are the receipt.

There is still no stun — `Entity.stagger` is a plain int rather than an
attribute, so it cannot ride a block, and `movement_scale` returns zero while it
is set, which makes it a total lockout rather than a status — and no damage type
for anything to resist or be weak to.

**Three attacks carry a block**, and where they are is why they could ship
without a sweep: Deathmark, Runeshot and Cataclysm are all a promoted class's
heavy or ultimate, and the reference bot presses the light attack and nothing
else. No enemy attack inflicts anything — that is the change that moves all 280
cells, and `test_no_enemy_attack_inflicts_anything` is the guard. Removing the
three blocks makes the layer inert again, which is the rollback.

This is the substrate the previous gap is missing. Status effects are what turn
flat stats into interactions — a slow that makes the charger's commitment
punishable, a burn that rewards the Magician's reach — and they are the cheapest
route to gear that is worth describing.

### No elite layer

Six archetypes, nine variants, ten bosses. `test_a_variant_is_stat_identical_to_what_it_varies`
already holds a variant to the whole attribute block by iterating
`dataclasses.fields`, which means **`EntityType.attributes` is the affix slot
and it is already built** — [Limits](limits.md#the-attribute-layer) names it as
where an enemy's armour would live.

An elite/champion layer — a modifier rolled onto an ordinary spawn from the
run's seed — is the single largest variety multiplier per hour of work available
here, and it is the one change in this document that adds run-to-run difference
*without* touching the stage literals the grid depends on.

**Shipped, and off unless a run asks for it.** `game/elites.py` and
`data/elites.json`: six stat affixes, weighted, rolled per ordinary spawn from a
**fifth** seeded stream (`world.elite_rng`, `seed ^ ELITE_STREAM`) and added to
`Entity.bonus` beside the difficulty tier's block. No new arithmetic in
`combat`, `sim` or `ai` — the affix slot was already built, and this is the
third feature `attributes.py` has absorbed that looked like it needed
mechanics.

Two independent guards, and the second is the one that matters:

* `data/elites.json` has an `enabled` flag, which is the content rollback.
* **`World(...)` takes `elites=OFF` by default**, so `tools/balance.py`,
  `game/autoplay.py`, `tests/test_playthrough.py` and every other caller in the
  project fight the monsters they always fought *however the file is tuned*. A
  run meets champions only by opting in, and it can only opt in once the
  profile has earned the unlock.

So "the grid is unmoved" is a test rather than a sweep, in the shape
[Testing](testing.md) already records four times:
`test_an_off_elite_layer_draws_no_dice_at_all` compares the generator's state
either side of construction, and
`test_no_enemy_in_any_shipped_stage_is_a_champion` walks all fifty arenas
asserting `bonus is NEUTRAL` by identity.

The warning below was heeded rather than argued with: every affix carries an
`Attributes` block and nothing else, and because `Attributes.from_dict` refuses
an unknown key, a behavioural affix is not something the loader rejects — it is
something the schema cannot express. Health is per-mille of the creature rather
than a flat `max_hp`, for the reason `difficulty.Enemies` already gives: one
flat number means something quite different to a rat and to a brute. **No boss
ever rolls one**, and none of the numbers has been swept — nothing can sweep
them while the layer is opt-in, and `data/elites.json` says so at the top.

> [!WARNING]
> **It is not free, and the constraint is recorded elsewhere.**
> [Limits](limits.md#nothing-paths-around-walls) explains that enemies walk
> straight at the hero and a pillar will hold one up, which already constrains
> level design. An affix that changes speed or reach interacts with that, and an
> affix that spawns adds interacts with it badly. Whatever ships first should be
> a stat affix, not a behavioural one.

### Bosses have one phase and one moveset

Recorded at [Limits](limits.md#the-bosses-have-one-phase-change-and-no-second-moveset)
with its reasoning: below half health each stops pausing between attacks, and
nothing new is introduced at the moment the player can least afford to learn
it. All ten share the shape.

The reasoning is sound and the market expectation is still two or three phases
with a genuine mechanical turn. This is listed low because ten bosses already
exist and re-authoring them is expensive relative to what it returns next to the
items above it.

---

## What players will file as bugs

None of these is a design decision that has been argued anywhere; they are
simply absent.

| | Where it stands | Why it matters |
| --- | --- | --- |
| ~~**Key rebinding**~~ | **Shipped.** Settings → Controls rebinds the eleven gameplay keys; menu keys, the panel digits and the mouse buttons are fixed by decision and [Limits](limits.md#only-the-gameplay-keys-rebind) records why | Was an accessibility baseline. It also built `bindings.Action`, which is the list [controller support](#no-controller) now binds to rather than inventing |
| ~~**In-fight pause**~~ | **Shipped.** `Esc` opens Resume / Settings / Quit to menu; the Quit row names the stage the autosave keeps. It writes nothing — **this did not buy [suspend-and-quit](#what-players-will-file-as-bugs), which is still the row below** | It also made the options screen reachable mid-run, which is where a wrong key binding is actually discovered. [Limits](limits.md#pause-writes-nothing) records what it deliberately is not |
| ~~**Accessibility options**~~ | **Shipped, in part.** Settings → Accessibility is five rows: colourblind palette, reduce flashing, reduce motion, and the two effect toggles that moved there from Settings. `palette.py` holds the two colour sets and `limits.md` records the two refusals | The row predicted the ninth row would cost a layout. It did — but a *smaller* one than priced, because two of the eight rows were accessibility settings on the wrong screen: moving them out took Settings to seven rows and put `ROW_H` back **up**, 16 → 18, the first time that number has moved in that direction. **Text scale and assist mode were refused rather than deferred**, each for a reason that is now written down ([no text scale](limits.md#no-text-scale), [no assist mode](limits.md#no-assist-mode)). What is left of this row is the honest remainder: the difficulty tiers are the assist mechanism and three of the four are still [untuned](limits.md#three-of-the-four-difficulty-tiers-are-unmeasured) |
| **Localisation** | Strings are hardcoded in `scenes/` and `render/` | Cheap now as a string table, expensive later as a refactor across **ten** render modules and ten scenes. It was nine when this row was written; the pause overlay added `render/pause_panel.py`. The price of this one goes up with every screen that ships |
| **Suspend mid-fight** | One autosave slot, written on the tick a stage begins. `game/save.py` [argues the refusal](../README.md#the-main-menu) | The argument is about *save scumming* and holds. Handheld play needs suspend-and-quit, which is a different feature and is compatible with it. **The pause overlay above did not deliver it** and was deliberately built not to: quitting from pause keeps the room you started, not the fight you were in |
| ~~**Run-end summary**~~ | **Shipped.** `render/result_panel.py`: the verdict, the class and its promotion, the depth and the clock, gold left, kills, damage dealt and taken, the build that was assembled and everything bought | The four numbers that did not exist are now derived from the event stream by `render/tally.py`, a third consumer beside the feel pass and the audio pass — no file under `game/` changed and the sweep never drains events, so the grid could not move. **The unlocks half of [order item 4](#the-order) is still open.** [Limits](limits.md#the-result-screen-is-a-full-stop-now) records the wash decision it overturned and the two things the screen cannot honestly say |
| **Daily seeded run and leaderboard** | Absent | **The expensive half is already built.** Exact seeded determinism is the property this project has defended hardest; a daily seed is a date-derived integer through the same door `--seed` uses |
| **Tutorial** | **Written, not wired.** `render/tutorial.py` is complete — six lessons, two kinds of satisfier, a `Lesson` table keyed on `bindings.Action` so a prompt names the key the player actually bound — and `tests/test_tutorial.py` holds it to the feel pass's rule that a fight resolves identically with it running. **Nothing in `src/` imports either.** | The same shape the audio layer had in `09bc62c`: the layer arrived complete and the call sites did not, so every document went on saying the thing was absent while the code sat in the tree. What is missing is a `Tutorial` on `PlayScene`, a `feed` beside `effects.tick()` on the drained list the feel and audio passes already share, and somewhere to draw a prompt |

---

## The numbers nobody has checked

Carried here from [Limits](limits.md#unmeasured) because they read differently
against a market than against a codebase. All three are recorded honestly
already; what follows is only the consequence.

- **The whole between-stage economy is unmeasured.** `autoplay` never buys,
  never spends a shrine's point and never detours to a fixture, which is exactly
  what keeps the grid a fixed reference. The consequence is that the systems a
  player spends the most *deliberate* attention on — which door, which piece,
  which attribute — have never been evaluated by anything.
- **Every tier except Normal ships flagged untuned** — `_measured: false` in
  `data/difficulty.json` — and the flag is honest and visible on the select
  screen. It was two tiers of three when [Limits](limits.md#three-of-the-four-difficulty-tiers-are-unmeasured)
  was written; the `nightmare` tier and the per-tier enemy multipliers have
  since landed, so it is three of four, and each tier now carries seven dials
  rather than one. The ratio is the point, not the count: the only swept tier is
  the one the grid is pinned to, and widening a tier from one dial to seven
  widened the unmeasured surface with it.
- **The classes are not balanced against each other.** The Rogue and the Archer
  take about 17% of their health on a median stage where the Knight takes 28%,
  and no attempt has been made to close it. Five classes that are not peers is a
  review comment waiting to be written.

The honest first instrument for all three is hands on a keyboard, not
`tools/balance.py` — which is the same conclusion
[Limits](limits.md#nothing-measures-the-shop) reaches from the other direction.

---

## The order

> [!IMPORTANT]
> **The positioning decision comes before any of it, and it is one question:
> does the campaign stay fixed?**
>
> It should. The fixed campaign is what the grid, the brackets, the two
> class×stage grids and every recorded number in [Balance](balance.md) rest on,
> and this project has correctly refused three changes that would have cost it.
>
> **So the variance is bought somewhere else: a second mode.** A seeded arena
> that assembles stages through the existing generator, rolls elite affixes, and
> ranks on a daily seed — sitting *beside* the fifty-stage campaign rather than
> replacing it. The campaign stays the tuned, measured, authored spine. The
> arena is where a second hour goes. Nothing in `levels/stage*.json` moves, and
> `test_playthrough.py` does not learn that the mode exists.
>
> That is the whole argument for the sequencing below.

1. ~~**Sound.**~~ **Shipped** — the cue layer, the generator and the four call
   sites that were missing from it. See
   [the section above](#no-sound). Music, stingers and UI sound are
   the remainder and are not what silence was.
2. **Controller.** ~~And rebinding with it~~ — rebinding shipped first and on
   its own, which was the cheaper order than it looked: it did the refactor at
   the `Intent` seam, so the controller is now the second binding table rather
   than the second half of one job.
3. **Packaging to a single executable**, with the generators run as part of the
   build. Nothing above this line reaches anyone without it — and note the
   build now has a fourth generator to run, since `assets/sfx/` is gitignored
   exactly as `assets/sprites.png` is.
4. ~~**Run-end summary**, **then the first unlocks**~~ — **both shipped.**
   Access only, never stats, per
   [Nothing survives a run](#nothing-survives-a-run). Four dead counters are now
   two locked tiers and an opt-in modifier, and the summary names what a run
   earned on its way down.
5. ~~**Elite affixes, then status effects.**~~ **Shipped.** Stat affixes only,
   as the warning above asked, and three status-bearing attacks on promoted
   slots the grid cannot see. What is left is measurement rather than build:
   nothing has swept the champion rates, and nothing can while the layer is
   opt-in.
6. **The seeded arena mode and a daily leaderboard.** Replay value; grid
   untouched.
7. **Art.** Largest cost, best spent once the six items above have proved the
   game is worth dressing.

Items 1–3 are the product line: below it there is nothing to sell, above it
there is. **One of the three is done**, which is the first time that sentence
has been able to say so. Items 4–6 are the retention line, and **two of those
three are done** — what is left of it is item 6, the seeded arena and the daily
leaderboard, which is also where the champion layer stops being opt-in and
becomes what a mode is *about*. Item 7 is what decides whether anyone arrives.

> [!NOTE]
> **The suite is not a green gate right now, and the baseline is now written
> down.** Four run-bracket failures stand on `main`, with no xfails outstanding
> anywhere in the project; they are
> [named in Testing](testing.md#none-currently-recorded) so a red run can be
> attributed in seconds rather than re-derived. **Re-confirmed at `af09d65`** by
> running those four ids again: the same four, failing the same way — the priest
> still finishing 2 of 3 — so neither the audio wiring nor the difficulty work
> since `929b32e` moved the bracket. Testing still records the earlier
> confirmation at `929b32e`, which is the older of the two readings. The per-stage grid is clean and
> is the thing that must stay clean. Note that
> [`test_playthrough.py` takes tens of minutes](testing.md), so the fast gate is
> the edit loop and the full suite is the commit.

---

## What this does not propose

Stated so that each stays a decision rather than an oversight.

- **Procedural generation of the campaign.** Covered above: it buys variance
  with the grid, which is the wrong trade. The arena mode is the answer.
- **Damage or maximum health scaling beyond what the gear layer already does.**
  [Limits](limits.md#almost-no-progression-that-makes-you-hit-harder) documents
  the open question the gear pool already left behind — a well-bought run may
  meet the late bosses with roughly double the damage they were tuned against.
  That question wants answering before anything else is added on top of it.
- **A level editor.** [Limits](limits.md#no-level-editor) prices it at roughly
  half a project, and the arena mode changes the calculus rather than the
  answer — a generator that assembles stages needs authored *chunks*, which is a
  smaller thing than an editor.
- **Teaching the reference bot to spend.** It measures the shop and stops the
  grid being a fixed reference on the same day. Refused three times already, and
  this document does not reopen it.
- **CI.** [Limits](limits.md#no-ci) records its absence, and a suite that takes
  tens of minutes is the reason it is not free. Worth having before item 5,
  which is the first item that touches the sim.
