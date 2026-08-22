# Known limits

Everything here is known, and most of it is deliberate. Where a limit was a
decision, the reasoning is given — so that reversing it is a decision too, taken
with the same information.

> [!NOTE]
> **This document argues each limit against the codebase. [Roadmap](roadmap.md)
> prices several of them against the genre the game sits in**, which is a
> different question and sometimes reaches a different answer. Nothing there
> overturns a decision here; it records what one costs. Where the two disagree,
> this document holds the reasoning and that one holds the judgement.

---

## Deliberate

### Almost no progression that makes you hit harder

> [!NOTE]
> **This section was written when it was true of the whole game, and it is now
> true only in the narrow sense below.** An eight-attribute layer and a level-up
> system landed underneath it — crit rate, crit damage, health, damage, defense,
> dodge, health regen and move speed — and they ship **switched off**
> (`xp_base: 0` in [`data/progression.json`](../data/progression.json)).
>
> **All eight are now reachable, and this section's central claim no longer
> holds unqualified.** The Boots were the first crack — `move_speed`, which the
> sentence below survived because movement is not output. **The gear a stall
> rolls broke it properly**: the pool in
> [`data/equipment.json`](../data/equipment.json) carries `damage` and `max_hp`
> among the eight, so the hero's output *can* now grow across a run. See
> [The attribute layer](#the-attribute-layer) at the end of this section and
> [Loot and gold](loot.md#the-gear-a-stall-rolls).

The shop's five consumables sell health now, health per stage, gold find and
walking speed; nothing among *them* touches damage or maximum health, on any of
the forty stages. **The three rolled gear rows above them do.**

That claim was load-bearing rather than squeamish, and it is worth stating
exactly what buying it back costs. Because the hero's **output** did not grow
across a run, health on a later boss bought fight *length* and nothing else — so
the act bosses are not much tougher than the first and take their difficulty from
reach, cadence and arena instead. Both act III and act IV bosses were drafted far
tankier and were unwinnable on every seed; the four late bosses were built inside
that finding rather than rediscovering it, and the heaviest of them is twenty
health above the Sovereign.

> [!WARNING]
> **This is the open question the gear layer leaves behind, and it is stated
> rather than hidden.** A run that buys every damage piece it is offered could
> roughly double its damage per swing over forty stages — a `whetstone` at
> legendary is +12 flat, against a Knight's greatsword at 12. Nothing measures
> whether that happens or what it does, because `autoplay` never enters a panel
> and never spends: `run.earned` is neutral in every recorded sweep, which is
> what keeps the grid provably unmoved and is *also* exactly why the grid has
> nothing to say about this.
>
> So the late bosses are still tuned against a hero whose output does not grow,
> and a well-bought run now meets them with one whose output did. That is a
> difficulty question, not a correctness one, and the honest first check is hands
> on a keyboard rather than `tools/balance.py`. The dials, in the order to reach
> for them: the `damage` amounts in `data/equipment.json`, then `rarity_scale`,
> then `stall.offers` in `data/rooms.json` — and `stall.offers: 0` puts this
> paragraph back to the way it was.

**The one exception is [promotion](design.md#promotion), and it is the seam the
campaign is built around rather than a hole in this rule.** An advanced class
changes maximum health and replaces two attacks. This document used to argue
that it was survivable *only* because there was no stage after it. That argument
was true of the trigger it described and it is no longer the trigger: the fork
sits after stage 20, and twenty stages follow it.

What makes it survivable now is narrower and more useful. **An advanced class
inherits its light attack**, and the light is most of what a fight is made of —
so the hero's damage per swing does not jump at the fork. What changes is a
health number and two attacks on long cooldowns. Acts V–VIII are tuned against
the inherited light alone, which means the new heavy and ultimate are upside
rather than something a stage assumes; that is what keeps the second half from
needing a scaling multiplier under it.

Moving the trigger again is still one condition in `jobs.PROMOTION_STAGE` and a
re-tune of everything after it.

~~What still has no answer is equipment.~~ Selling a damage upgrade would need a
per-`Entity` stat layer that every lookup in the game went through, and would
invalidate the whole recorded balance grid on the day it shipped. Promotion sits
in `EntityType`, which is frozen content — it swaps which type a body points at
rather than adding a layer under it.

**The layer arrived, and the Boots are the first thing sold through it.** What
that changed is smaller than it sounds, and the reason is the same one that made
the layer affordable in the first place: the reference bot never spends, so
`move_speed` is zero in every sweep, and `sim._walk_speed` returns the type's
own number at zero rather than multiplying it by one. The grid is untouched as
arithmetic, not as an argument.

What remains refused is **damage and maximum health in the shop**, and the
reason is now a design one rather than a structural one — see
[Nothing measures the shop](#nothing-measures-the-shop).

### The attribute layer

The refusal above was correct about the cost and wrong about the conclusion, and
the half that survives is worth keeping: **the layer is what invalidates the
grid, so the layer had to be able to prove it hadn't.**

Eight attributes — crit rate, crit damage, health, damage, defense, dodge,
health regen and move speed — in two halves. `EntityType.attributes` is content, frozen and
shared, and is where an enemy's armour would live. `Entity.bonus` is what one
run earned, and it dies with the run. `Entity.attrs` is the sum and the only
thing the sim reads. Every field defaults to the identity of its own operation,
so a neutral block makes `combat.resolve_damage` reduce to `combat.roll_damage`
and the arithmetic is exactly the arithmetic that was measured.

Three things made it affordable, and all three are the project's own recorded
patterns pointed at a new problem:

- **A third RNG stream.** Crit and dodge are dice, and a die drawn from
  `world.rng` shifts every damage roll after the first hit — all 280 cells,
  silently. `world.attr_rng` is seeded `seed ^ ATTR_STREAM`, and
  `test_attribute_rolls_do_not_disturb_the_damage_stream` was written before the
  code it guards, exactly as the loot one was.
- **One field on `EntityType`, not one per attribute.** `test_a_variant_is_stat_identical_to_what_it_varies`
  iterates `dataclasses.fields`, so all nine variants were held to the whole
  block with no test edit — and an eighth attribute is covered the day it lands.
  It has since landed (`move_speed`) and that is exactly what happened: no test
  edit, and `progression.Table.load` refused to start until the new attribute
  had a price, which is the same trick working from the other end.
- **The claim is settled structurally, not by a sweep.**
  `test_neutral_attributes_reproduce_todays_arithmetic` checks every weapon in
  the content files in milliseconds. `tools/balance.py` takes minutes and proves
  less.

**What is not answered is whether any of it is any good.** The values in
`data/progression.json` are a first pass and the file says so.

~~Worse than that, and stated plainly because it is the trap: `autoplay` does not
spend points.~~ **It can now.** `play_run_out` takes an `allocate` policy and
`tools/balance.py` takes `--allocate` — `spread` for one point into each
attribute in turn, an attribute name for a whole budget in one dial. The reason
it had to come first is the part that has not changed: unlike gold, which a
player might reasonably not spend, levels are always spent, so a sweep run
against an unlevelled hero measures a game nobody plays and reports it in the
same units as difficulty. That is the [flanker demon](balance.md#findings) again.

**The bot has the behaviour. The dial is still at zero, and that is the whole of
what is left.** `allocate=None` is still the default and is still a branch that
is never taken, so no recorded number moved when the instrument gained the
ability — and on the shipped table the flag is inert anyway, because there is
nothing to spend. What remains is the expensive half: turn `xp_base` up,
re-baseline all 280 cells against `--allocate spread`, and expect to retune.
There are no strict xfails left for it to invalidate. See
[Balance](balance.md#the-instrument-can-spend-now-the-dial-is-still-at-zero).

Setting `xp_base` back to 0 is the rollback, and it is the state it ships in.

**Two things reach these eight without experience being on, and they are now the
only things that do.** A [shrine](design.md#the-rooms-between) hands out a point
and offers three of the eight to spend it on; a [stall](loot.md#the-gear-a-stall-rolls)
sells rolled gear that writes a block directly. Both go through
`progression.grant`, which is the one place `run.earned` and the live
`Entity.bonus` are written together — three callers, one write, because two of
them used to hold their own copy of it and a third copy is the point at which one
gets fixed and the others do not.

Note what that split buys and what it costs. **Buys:** the attributes become
reachable without turning on the half that would move the recorded grid, because
a room is invisible to `Run.index` and the bot walks past every fixture.
**Costs:** the same blindness, pointed the other way — the bot never spends a
point and never buys a piece, so the sweep measures a hero with a neutral block
whatever the shelves are selling.

`--allocate` only half-answers that, and the half it does not answer is the
important one. It teaches the bot what to do with a point *once it is holding
one* — but the bot still walks past the shrine that would hand it one and past
the stall that would sell it a block, so on the shipped table it still arrives at
every fight neutral. Measuring the shrine means an instrument that detours to a
fixture, and that is the change this project has refused three times because it
stops the grid being a fixed reference. See
[Nothing measures which door is worth taking](#nothing-measures-which-door-is-worth-taking).

### The bosses have one phase change and no second moveset

Below half health each stops pausing between attacks. Deliberate — nothing new to
learn at the moment you can least afford to — but it does mean a fight holds no
surprise once you have read the three attacks, and all four bosses share the
shape.

### Champions are stats, and only on ordinary monsters

`data/elites.json` rolls an affix onto an ordinary spawn from the run's own
seed. Four things it deliberately is not.

**No behavioural affixes**, and the refusal is structural rather than a rule:
an affix carries an `Attributes` block, `Attributes.from_dict` raises on a key
it does not know, so nothing that summons, paces or paths can be written down.
That follows from [nothing paths around walls](#nothing-paths-around-walls) —
the one limit every arena is laid out against — and from the recorded finding
that a brain aimed at a player behaviour can only be measured by an instrument
that has it.

**No boss ever rolls one.** A boss is already the act's statement, and it is the
one body with a health bar of its own for the mark to compete with. It is a dial
(`bosses`) rather than a hard rule, because a seeded arena mode has no acts to
make a statement about.

**Off unless a run asks.** Two independent switches: `enabled` in the data file,
and `World(elites=OFF)` at every seam in the project. The second is the one that
protects the grid, and it protects it *however the file is tuned* — so this
layer could ship enabled tomorrow without a single recorded number moving.

**And therefore entirely unmeasured.** `autoplay` never opts in, so nothing has
an opinion about whether a 12% champion rate is a spice or a wall. This is the
[shop's hole](#nothing-measures-the-shop) in a new place and it was chosen the
same way: an instrument that opted in would stop the grid being a fixed
reference on the day it gained the ability to measure this.

### A status has no stun, and only three attacks inflict one

`Weapon.inflict` / `inflict_ticks` and `Entity.status` / `status_ticks` are the
substrate: a burn is a negative `regen`, a slow a negative `move_speed`, a
vulnerability a negative `defense`. Three things it is not.

**There is no stun.** `Entity.stagger` is a plain integer rather than one of the
eight attributes, so it cannot ride a block — and `actions.movement_scale`
returns zero while it is set, which makes it a total lockout rather than a
status. Adding one means a separate scalar on the weapon and a decision about
how long a player may be denied their hands, which is a design question and not
a field.

**A slow does not slow a roll or a charge.** `sim._self_propulsion` branches on
`DODGING` and on a charging `ACTIVE` before it reads the walking speed. So the
obvious use — making a charger's commitment punishable — is not what a slow
does; it is a repositioning tax. The dodge exclusion is the recorded one from
the attribute layer (a roll is a fixed-distance defensive tool and stretching it
buys invulnerability rather than mobility); the charge falls out of the same
ordering.

**Three attacks carry a block, and where they are is the whole of why they
could ship unswept.** The Assassin's Deathmark (a vulnerability), the Magic
Archer's Runeshot (a slow) and the Wizard's Cataclysm (a burn) — every one an
advanced class's heavy or ultimate. The reference bot presses the light attack
and nothing else, so the recorded grid cannot see any of the three, which is the
same reason `docs/balance.md` has never had an opinion about the twenty
promoted attacks. `--policy skilful` *does* press those slots, so its numbers
moved; nothing gates on them.

**Which means all three magnitudes are guesses**, in the same position every
number in `data/rooms.json` is in. They are written into the weapons' own
`_comment` blocks rather than here, beside the numbers they describe.

**A status on an *enemy* weapon is the change that cannot be made this way.**
Every enemy attack is pressed on measured ticks, so a burn on a grunt moves all
280 cells on the day it lands. `test_no_enemy_attack_inflicts_anything` is the
guard, and the rollback for the whole layer is still one edit: remove the three
`inflict` blocks and the code is inert.

### Enemies do not dodge

Expressed as data: they have no `dodge_ticks`. The roll is the player's verb
alone.

### The charger commits absolutely

Once it dashes it cannot stop, including into a wall. That is the point, but it
does mean a clever player can farm it against pillars.

### Placeholder art

Generated shapes, not drawn sprites. Replace `assets/sprites.png` with a PNG of
the same cell layout to swap in real art — see [Content](content.md#tools).

### No music, and no sound that is not a cue

The sound effects shipped: `audio/cues.py` turns events into named cues,
`audio/bank.py` owns the mixer, `tools/gen_sfx.py` generates the WAVs, and
`scenes/play.py` feeds and drains them. `tests/test_audio.py` pins that a fight
resolves identically with cues running, which is what makes the audio pass
tunable without re-checking the balance under it.

What is still absent is everything that is not a combat cue: **no music**, no
stinger on a boss or a victory, no sound on a menu row, and no positional
audio -- `SoundBank.play` takes one global level, so a trap across the arena is
as loud as the one underfoot. The first two are content and the third is a
panning argument in `bank.py`; none of them is the hole silence was.

### The result screen is a full stop now

The four lines that ended a run are a summary: the verdict, the class and the
branch it took, the depth and the clock, gold left, kills, damage dealt and
taken, the attributes the run built and everything it bought.

**It took the panels' wash with it, and that overturns a recorded decision.**
The old comment read: *"a dim wash rather than a solid panel, so the arena stays
visible behind the result -- seeing what killed you is part of the message."*
Two things answer it. There is **nothing left to see** -- `sim._settle` culls the
corpse on the death tick, so the lighter wash was showing an empty arena. And
there are now nine lines of numbers on that screen, which need the contrast.
Recorded here rather than deleted, because the old reasoning was good and the
next person to reach for a lighter wash should meet the argument, not a blank.

**The world stops when the run ends.** It did not before: the end block sits
inside the tick loop, so later frames went on stepping the world -- enemies kept
moving, and on a *won* run the hero was alive and could still walk and swing
behind the wash. Invisible until a kill count was on screen climbing while the
player read it. The freeze is a guard around the tick loop and deliberately not
an early `return`: `effects.tick()` is what decays the screenshake, and stopping
it would leave the viewport jittering under the summary for as long as it was up.

### What the run summary cannot say

Three things, each an honest ceiling rather than a shortcut.

**Gear is counted, never named.** `run.purchases` keys equipment as
`eq:{index}:{slot}`, and the `Offer` carrying the name is derived per room and
thrown away. Re-deriving it means rewinding `run.index` and re-running every
stall's stream, which yields names that are wrong-but-plausible the moment the
gear pool is edited. What a piece *did* is not lost -- it is in `run.earned`,
which the line above prints. Naming them is a separate change: record the name
at purchase time.

**"Gold collected" was never true and the row no longer claims it.**
`Run.gold_total` is `gold + world.gold`, and both `shop.buy` and `equipment.buy`
subtract from `gold` -- so on any run that spent anything, that number is what is
**left**. The old screen said "collected". Gold collected is not derivable at
all: chest gold goes straight into `run.gold` and its `PROP` event carries
`amount=0`. So the row says **Gold left**, and no figure was invented to replace
it. (`profile.record_end`'s docstring makes the same wrong claim about
`best_gold`; it is noted, not chased.)

**A resumed run has only counted this session.** The tally is not in the save
file and deliberately not: persisting it would need `SAVE_VERSION` 4 -> 5, and
`check_version` refuses anything else outright, so every save in existence would
stop loading for a number that is thrown away moments later. Instead
`Tally.partial` makes the clock read `12:04 this session`, which is the honest
version of the same gap.

### Pause writes nothing

`Esc` stops the world and offers Resume, Settings and Quit to menu. **Quitting
does exactly what `Esc` did before the overlay existed**: it returns to the menu
having written and deleted nothing, so what survives is the autosave taken on the
tick the current room began.

That is a decision, not an omission. Writing a save at the moment a player
happens to press pause is **Suspend mid-fight**, which is a separate feature and
one `game/save.py` argues about at length: a snapshot is only a complete
description of a run *before* `sim.step` has run once on that world, and a
mid-fight one would mean serialising every entity position, every cooldown, every
projectile and the state of three `Random`s — welding the save format to the
sim's internals so that every change to a fight becomes a change to the format.

So the overlay's Quit row states what it keeps, in place, rather than implying it
keeps everything. The number it prints is asserted against a real `save.read()`
rather than written down, because a promise about a file is worth what the file
says.

> [!NOTE]
> **The pause overlay is unreachable from the promotion panel, and that is the
> point.** `Esc` is read only from the arena branch; the fork swallows it, as it
> swallows every key but `1` and `2`. A pause menu reachable from there would be
> a way to walk out of a choice that half the campaign is tuned around — see the
> no-exit-key note in `scenes/play.py`. The same holds for the shop, the shrine
> and the sheet, each of which already answers `Esc` its own way.

### The options screen is now reachable mid-run

A consequence of pause, and worth recording because it tightens a rule rather
than relaxing one. `scenes/options.py` says none of its rows may change how a
fight resolves, and calls that "the line this screen is drawn on". Until now that
line only had to hold *between* runs. It is now load-bearing **during** one.

Two things follow. **The seed row is safe by where the seed is read**, not by
anything the pause path does — `Run` takes its seed at construction and
`_stage_seed` derives from `run.seed` — so a refactor reading `settings.seed` at
stage entry would let a player re-roll act VIII from a pause menu. There is a
test pinning it for that reason. And **the erase row is hidden mid-run**: it
deletes a save the next stage boundary immediately rewrites, and resets a profile
that the end of the run then reports into.

Anything added to that screen from now on has to be safe to change with a fight
paused behind it.

> [!NOTE]
> **The first thing added since has cleared that bar, and one of its rows needed
> a new argument to do it.** Settings → Accessibility is five toggles. Three are
> safe by the argument this project has used four times now — they are fed by
> events the sim emits and never reads back — and `colourblind` is safe because a
> palette is a table of colours.
>
> `reduce_motion` is the exception and is worth recording as one: it gates a line
> in `PlayScene.update` rather than a flag on `Effects`, so the events argument
> does not reach it. What makes it safe is narrower and is a property of
> `freeze` — it **drains without stepping**, which is the whole reason `sim.step`
> clears `world.hitstop` at the top of a tick instead of counting it down. So
> skipping a freeze removes frames in which the world did not advance.
>
> That claim is proved rather than cited:
> `test_reducing_motion_skips_the_freeze_without_skipping_a_tick` runs the same
> fight both ways and asserts the two reach the same tick in identical states —
> in different numbers of *frames*, which is the feature.

### Only the gameplay keys rebind

The eleven actions in `bindings.py` can be moved on Settings → Controls. Four
things around them cannot, and each is a decision rather than a next step.

**Escape, Enter and the digits are refused**, by name, in `keymap.RESERVED`.
Escape leaves every screen in the game and closes the shop, the sheet and the
level panel; Enter dismisses all three and takes a row on the menu; `1`-`8` buy
at a stall, spend at a shrine and choose a path at the fork, and none of those
three panels has anywhere else to put a digit. They are how a player reaches the
rebinding screen and leaves it, so a screen that handed them out could strand
somebody in the arena they were standing in. The refusal is what makes the
feature safe rather than a hazard, and it is not a limitation of the
implementation.

> [!NOTE]
> **Space is deliberately not reserved, and the reason is worth keeping.** It
> confirms on every menu *and* it is the shipped dodge key. That works because
> the arena and the panels are never taking keys in the same moment -- so
> reserving it would have meant the screen refusing the game's own default,
> which is the reductio that decided where the line went.

**Menu navigation is not rebindable.** Up, down, left, right and confirm are
open-coded in `scenes/menu.py`, `options.py`, `select.py` and the four panel
handlers in `play.py`, and routing them through actions would mean re-expressing
every panel's exit rule -- including the promotion panel's deliberate refusal to
have one. The accessibility argument that carried the gameplay keys is much
weaker here: a menu is navigated a few times a session, an attack is pressed
hundreds of times a stage.

**The mouse buttons are not rebindable.** Left click swings and right click
rolls. A button is not a key, `bindings.py` models only keys, and the button
pair is small enough that a player who cannot use it is not helped by swapping
which of the two does what.

**Rebinding an action replaces every key it had**, rather than adding to a list.
So binding Move up to the up arrow drops `W` from it, and the roll's three
shipped keys become one the moment it is touched. The alternative -- a screen
that adds -- needs a way to *remove* a binding, which is a second interaction on
a screen whose whole job is "press the key you want". Reset puts the alternates
back.

### No text scale

Settings → Accessibility has five rows and none of them resizes the text. That is
a limit of the resolution rather than a gap in the screen.

The game draws into a 384x216 internal surface, and every layout in it is
measured in pixels against that surface: 41 `pygame.font.Font` constructions
across fifteen modules, `test_menu.py` and `test_render.py` asserting that each
label clears the value beside it and each row clears the hint under it. The
Settings screen itself is the illustration — its `ROW_H` has been 20, 18, 16 and
is now 18 again, and each of those moves was forced by one more row of 13px text.
There is no slack anywhere for a larger glyph, and a text-scale row would not be
a setting so much as a second set of layouts for every screen in the game.

**What the game does have is the window scale row**, and it is not a consolation
prize. `config.integer_scale` upscales the whole surface by a whole number, so a
player on 6x is reading glyphs six times the size of the ones in the source —
which is more magnification than a text-scale slider in a 1080p game would
offer. What it cannot do is make the text bigger *relative to the arena*, and
that is the thing 384x216 forbids.

The honest version of this feature is a larger internal resolution, which moves
every layout in the project and is a different job.

### No assist mode

Also absent from Settings → Accessibility, and this one is a rule rather than a
resolution.

`scenes/options.py` states the line that screen is drawn on: **none of its rows
may change how a fight resolves**, because the project's whole measurement
culture rests on balance decisions being made in `data/` where they can be swept.
An assist mode — a damage multiplier, a slow-motion toggle, extra health — is a
balance decision worn as a preference, and the day one ships behind a menu row is
the day every recorded number in [Balance](balance.md) needs a note saying which
assist state produced it.

**The difficulty tiers already are the assist mechanism**, and they are what
following that rule looks like rather than what breaking it looks like. They live
in `data/difficulty.json`, they are swept by `tools/balance.py --difficulty`,
they are pinned so the default tier is structurally the arithmetic the grid was
measured against, and they are chosen on the character select beside the class —
the other decision taken once per run.

So the answer to "there is no assist mode" is Easy, and the honest thing to say
about Easy is what
[the unmeasured list](#three-of-the-four-difficulty-tiers-are-unmeasured) already
says: it carries `_measured: false`. The sweep recorded in its own `_comment` is
`20/20 clean, and the face-tank bot still loses every run` — a real reading, and
one class over twenty stages, which is a start rather than a verdict. Nothing has
swept it for the ten advanced classes or for stages 21–50, and nothing has swept
it run-level at all.

**Measuring it is a balance job, not an accessibility one**, and it is the thing
worth doing next for the player this section is about — a tier that is easier by
an unmeasured amount is a worse answer than one that is easier by a known one.

---

## Unmeasured

### Nothing measures which door is worth taking

`autoplay` walks from a room's entrance to a door and **touches nothing on the
way**. So no number in `data/rooms.json` is measured by anything: not whether a
fountain should heal 15% or 40%, not whether a chest pays enough to be worth a
door, not whether the shrine's point beats either. `--allocate` does not change
this: a policy for spending a point is not a route that walks onto the plinth
handing them out.

`stall_every: 3` is the newest number in that list and the one with most riding
on it. **Eighteen** stalls across a run that banks ~24,500 g, against 2,060 g to
max the permanents, presses on the late-run surplus from the opposite side to the
Elixir — and the bot neither buys nor cares which door it takes, so nothing here
can say whether eighteen is generous or mean. It was seven, at `stall_every: 5`,
and that figure was no better measured than this one.

`stall_on_boss_floors` sits beside it and is a different kind of unmeasured: what
it buys — a shop on the floor after every act boss — is a thing the interval used
to supply by accident, and the reason it is now a rule is that moving the
interval would otherwise have removed it without a word. Whether a boss is the
right moment to be offered a shelf is still a question for hands on a keyboard.

That is deliberate and it was arrived at the hard way. The first draft had the
bot use the fixture. Three of the four rewards were inert to it regardless — it
never buys at a stall, never spends a shrine's point, never spends a chest's gold
— so only the fountain did anything, and over twelve seeds it flipped one run
from won to lost. The trace settled what kind of failure that was: the losing run
reached the stage it died on with **more** health than the surviving one. A
deterministic fight amplifies a nudge over thirty-nine stages, and the grid
reported the amplification in the same units it reports difficulty.

So the bot walks past, and rooms cost the measurement nothing at all — the
run-level figures are byte-identical to the ones recorded before rooms existed.
That survived the rooms learning to turn: the doors moved onto three different
walls and door 0 became the left one rather than the top, and the figures did not
move, because "walk at door 0 and touch nothing" is a claim about the fixture and
not about the wall it stands on. The clearance it rests on is now swept over all
four approaches, worst case 45.5 px against a reach under 15.
The hole this leaves is the same one the shop has: an instrument that spends is
an instrument that has stopped being a fixed reference, and this project has
chosen the fixed reference every time it has been asked.

### Three of the four difficulty tiers are unmeasured

`Normal` is measured by every recorded number in the project, and structurally
so: at the identity multiplier the arithmetic is the arithmetic the grid was
measured against, `data/difficulty.json` refuses to load if the default is
anything else, and `test_difficulty.py` runs a default-tier fight beside one
built by a world that has never heard of difficulty and demands the same health
tick for tick.

**Every number on Easy, Hard and Nightmare is an opening bid**, and there are
now seven dials per tier rather than one — `incoming` plus six on the monsters.
They are round numbers picked to be legible, not swept values, and all three
tiers are flagged as untuned in the data file *and on the select screen*, so a
player choosing one is told.

The per-stage bracket **has** been swept for all three, and it moved every
number twice: Easy clears 20/20, Hard 19/20, Nightmare 15/20, at eight seeds
over stages 1–20. The first draft of Nightmare left fifteen of twenty stages
unclearable from full health, because six moderate dials compound into an
impossible one. `data/difficulty.json` carries the trace.

What is still unmeasured is everything run-level — both harder tiers finish 0/8
runs, and that cannot be read as a verdict while the run bracket is red at
Normal too. `cadence` is the dial most likely to be doing nothing: it scales
only the pause, which is 20 ticks of a chaser's ~65-tick cycle, so Nightmare's
12.5% cut moves the gap a chaser actually shows you by about 5%.

**One cell must not be tuned with these dials at all.** Stage 20, the Sovereign,
is chaotic in them rather than monotonic — at 32 seeds Normal clears 31/32 and
Hard 14/32, while a *harsher* Nightmare draft cleared 26/32, and putting a
single dial back to its identity made it worse. Same shape as the fountain that
flipped a run by healing the hero. Only `incoming` moves it monotonically, and
gently.

What is pinned rather than guessed is the thing a tier could quietly destroy: a
hero that walks in swinging still loses every run on the gentlest tier, checked
against whichever tier is gentlest rather than against a name, so adding a
softer one below cannot slide out from under it. Gentlest is file order now,
because with seven dials there is no single number to minimise.

`tools/balance.py --difficulty <tier>` is how this stops being true.

### Nothing measures the shop

`autoplay` never buys anything and never detours for a pickup, which is exactly
why the balance grid is provably unmoved by the loot layer — and exactly why
nobody knows whether four Tonics trivialise act two. The loot numbers are a first
pass and [`data/loot.json`](../data/loot.json) says so at the top.

**This is now the reason damage and maximum health are not on the shelves, and
it is a weaker reason than the one it replaced.** It used to be structural: the
shop could not sell a stat because there was nowhere to put one. The attribute
layer removed that, and the Boots demonstrate it. What is left is a judgement —
that a good competing with levelling for the same gold is two unmeasured systems
bidding against each other, and that speed is the safest of the eight to try
first because it changes how a fight is fought rather than how hard the hero
hits. Teaching the bot to spend is what would turn any of this into a
measurement, and it stops the grid being a fixed reference on the same day.

### The fifteen attacks

The reference bot plays light-only by design, so it cannot see the neutral, heavy
or ultimate slots. The suite pins the relationships between slots, not the values.

The Priest's `buff_haste` is unmeasured in a second way: it multiplies the value
of the two slots it speeds up, and both of those are unmeasured too. Nothing
knows what a Consecrate every 1120 ticks instead of 1600 is worth, because
nothing knows what one is worth at all.

The five buffs in the neutral slot are the least measured numbers in the game:
neither instrument presses the slot, and `Skilful` now skips it deliberately
rather than by accident. The Priest's `regen` is the flagged one — the recorded
finding is that past a point the hero dies *inside* a stage rather than to
attrition between them, so the risk is that sustain is worthless there rather
than that it is too strong. Nothing measures which.
See [Balance](balance.md#what-is-not-measured).

### The twenty attacks the advanced classes bring

Half of what this section used to say has been fixed and half of it is worse than
before.

**Fixed:** the bot promotes now. All ten advanced classes are swept against all
twenty stages after the fork, one cell each, and a branch that cannot clear act
VII fails the suite. When this was a capstone, none of that existed and a branch
could only ever be judged against the Sovereign.

**Still true, and now the largest unmeasured surface in the project:** `autoplay`
plays light-only, and an advanced class's light is the one it inherited. So the
grid measures each branch's *health and body* against the late campaign, and the
twenty heavies and ultimates are as unmeasured as they ever were. What separates
the Dark Knight from the Holy Knight in a sweep is fifteen points of health;
what separates them at a keyboard is Black Tide and Sanctuary, and nothing has
an opinion about those.

That is deliberate rather than neglected, and it is the same trade the original
fifteen attacks are on: a light-only reference is what keeps every recorded
number comparable across every change since. The consequence to be honest about
is that acts V–VIII are tuned to be clearable *without* the new kit, so a player
who uses it has an easier time than the grid says. `tools/balance.py` can be
pointed at the `skilful` policy to ask how much easier; nobody has.

### The dodge's worth is measured, not settled

The reference bots gain little from it, and the twitchiest one is actively
crippled by it. They have perfect information and only the crudest sense of
pillars, so that says more about them than about the roll — but it is the claim in
this documentation most likely to be overturned by hands on a keyboard.

> [!NOTE]
> **Until recently a human could not have overturned it, because the roll was
> not reliably coming out.** `PlayScene` cleared its edge-triggered inputs once
> per rendered frame rather than once per simulation tick, so a dodge was
> discarded on any frame that paid out no tick — and, far more often, on every
> frame swallowed by hitstop, which is up to eleven ticks after each landed hit.
> The press was being lost precisely in the moment the roll is reached for.
>
> Worse, and this is the part worth carrying: **fixing the loss changed
> nothing.** A press made during hitstop still landed 0 times out of 16, because
> `freeze` drains without stepping and the `stagger` underneath it therefore
> has not started counting down — the press arrived on time and was refused. It
> took a bounded input buffer, one tick longer than the stagger, to take that
> to 15 out of 15.
>
> None of the measurement above is affected: the bots go through `sim.step`
> directly and never touched the scene. But every impression anyone formed
> playing this by hand was formed against an input path that dropped presses,
> and this section is where that matters. **The dodge has never actually been
> judged by a human on a working control.**

### Five classes, one campaign

Every stage is tuned against the Knight and only checked against the other four.
They are **not balanced against each other** — the Rogue and the Archer take about
17% of their health on a median stage where the Knight takes 28%, and no attempt
has been made to close that.

---

## Engineering

### `autoplay` can sidestep now, but the reference still does not

The recorded blocker on the `flanker` demon was that the reference bot's entire
defensive repertoire is backing away in a straight line -- which is exactly what
that brain exists to defeat, so the grid reported *"the instrument has no
answer"* in the same units as *"the fight is too hard"*.

`autoplay.Evasive` is that gap closed as a **second instrument**, not as a change
to the reference: it overrides one method, `_retreat_direction`, and
`test_the_evasive_policy_leaves_the_reference_untouched` fails if it ever
overrides a second. So every recorded number still means what it meant, and
`tools/balance.py --policy evasive` is how the comparison gets made.

What is still true: **the reference bot cannot sidestep**, and until a sidestep
is promoted into it -- a decision that moves the grid on the day it lands, and
the same kind of decision as teaching the bot to spend gold -- placing the demon
is still measuring the instrument. `EVASIVE_DEGREES` is itself unswept; the
`flanker`'s measured 35-to-55 cliff is the *enemy's* approach and says nothing
about the hero's disengage.

### Nothing paths around walls

Enemies walk straight at you, so a pillar will hold a grunt up. This constrains
level design rather than being invisible: a pillar that seals a lane strands
whatever is behind it, and the player has to go and fetch a grunt that spent the
fight pushing into a wall. An early draft of stage 1 did exactly that.

It also quietly **contaminates measurement**. Running the skill-using bot over the
twenty stages, two of the eight cells that moved were not losses at all — both hit
the tick limit with the hero healthy and every surviving enemy at full health,
behind a wall and outside its own aggro radius. Nothing had gone wrong with the
balance; the fight had simply ended up somewhere neither side could route out of.

Real pathing means A\* over the tile grid, in `core/`. A flow-field attempt was
written and reverted — it broke the balance bracket for four of the five classes,
because enemies that route around pillars remove the only tool the player has
against a crowd. It is not a drop-in; it is a re-tune of the whole grid.

### Ranged escorts do not work on a boss stage

A bowman never becomes the nearest thing in the room, so it is never what you are
fighting, so it never dies — a damage tax for the length of the fight with no
answer available. The act III boss stage was drafted with two of them and was
unwinnable on every seed. Every boss stage is escorted by melee now, which is a
standing constraint on level design rather than a bug that got fixed.

### The enrage threshold is a fraction, so boss health barely affects difficulty

Halving a boss's HP does not halve the damage it deals you: it spends the same
*proportion* of a shorter fight enraged. Both later bosses were tuned by damage in
the end, after health changes moved the win rate by nothing at all.

### Projectiles are swept along their centre line only

`path_is_clear` ignores the arrow's radius, so a shot can clip a wall corner by a
pixel or two before it stops. Cosmetic at this scale; making it exact means
sweeping a circle rather than a segment.

### No level editor

`tools/make_level.py` describes each stage as a border plus a list of pillar
rectangles and writes the JSON. An editor is roughly half a project on its own; a
short script is still the trade being made at fifty stages, and it is well past
the line it was near at twenty. Fifty hand-written `Stage` literals is where the
absence of an editor is felt: placing a pillar means picturing a rectangle, and
placing an enemy means checking by eye that it is not inside one. The generator
refuses to write an unplayable campaign, which catches the second mistake but
not the interesting one — an enemy stranded in a pocket it never leaves is a
perfectly playable stage that nobody can finish.

> Two of the ten stages added for acts IX and X were written with an enemy
> inside a pillar, and the generator caught both before anything was written to
> disk. That is the cheap mistake; the expensive one is still unguarded.

### No CI

`python -m pytest` is the whole gate. See [Testing](testing.md).
