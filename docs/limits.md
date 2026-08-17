# Known limits

Everything here is known, and most of it is deliberate. Where a limit was a
decision, the reasoning is given — so that reversing it is a decision too, taken
with the same information.

---

## Deliberate

### Almost no progression that makes you hit harder

> [!NOTE]
> **This section was written when it was true of the whole game, and it is now
> true only of the shipped configuration.** A seven-attribute layer and a
> level-up system landed underneath it — crit rate, crit damage, health,
> damage, defense, dodge and health regen — and they ship **switched off**
> (`xp_base: 0` in [`data/progression.json`](../data/progression.json)).
>
> Nothing below has changed as a *fact about what you can play today*. What
> changed is that it is now a dial rather than an absence, and the paragraph
> further down claiming equipment "has no answer" has been overtaken. See
> [The attribute layer](#the-attribute-layer) at the end of this section.

The shop sells health now, health per stage, and gold find; nothing it stocks
touches damage, speed or maximum health, on any of the forty stages.

That is load-bearing rather than squeamish. Because the hero's **output** does not
grow across a run, health on a later boss buys fight *length* and nothing else —
so the act bosses are not much tougher than the first and take their difficulty
from reach, cadence and arena instead. Both act III and act IV bosses were
drafted far tankier and were unwinnable on every seed; the four late bosses were
built inside that finding rather than rediscovering it, and the heaviest of them
is twenty health above the Sovereign.

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

### The attribute layer

The refusal above was correct about the cost and wrong about the conclusion, and
the half that survives is worth keeping: **the layer is what invalidates the
grid, so the layer had to be able to prove it hadn't.**

Seven attributes — crit rate, crit damage, health, damage, defense, dodge and
health regen — in two halves. `EntityType.attributes` is content, frozen and
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
- **One field on `EntityType`, not seven.** `test_a_variant_is_stat_identical_to_what_it_varies`
  iterates `dataclasses.fields`, so all nine variants were held to the whole
  block with no test edit — and an eighth attribute is covered the day it lands.
- **The claim is settled structurally, not by a sweep.**
  `test_neutral_attributes_reproduce_todays_arithmetic` checks every weapon in
  the content files in milliseconds. `tools/balance.py` takes minutes and proves
  less.

**What is not answered is whether any of it is any good.** The values in
`data/progression.json` are a first pass and the file says so. Worse than that,
and stated plainly because it is the trap: `autoplay` does not spend points.
Unlike gold — which a player might reasonably not spend — levels are always
spent, so a sweep run against an unlevelled hero measures a game nobody plays
and reports it in the same units as difficulty. That is the
[flanker demon](balance.md#findings) again. **Teach the bot to allocate before
turning `xp_base` up, not after.**

Setting `xp_base` back to 0 is the rollback, and it is the state it ships in.

### The bosses have one phase change and no second moveset

Below half health each stops pausing between attacks. Deliberate — nothing new to
learn at the moment you can least afford to — but it does mean a fight holds no
surprise once you have read the three attacks, and all four bosses share the
shape.

### Enemies do not dodge

Expressed as data: they have no `dodge_ticks`. The roll is the player's verb
alone.

### The charger commits absolutely

Once it dashes it cannot stop, including into a wall. That is the point, but it
does mean a clever player can farm it against pillars.

### Placeholder art

Generated shapes, not drawn sprites. Replace `assets/sprites.png` with a PNG of
the same cell layout to swap in real art — see [Content](content.md#tools).

### No sound

Nothing here would have to change to add it; hits already emit events with
everything a sound cue needs.

---

## Unmeasured

### Nothing measures the shop

`autoplay` never buys anything and never detours for a pickup, which is exactly
why the balance grid is provably unmoved by the loot layer — and exactly why
nobody knows whether four Tonics trivialise act two. The loot numbers are a first
pass and [`data/loot.json`](../data/loot.json) says so at the top.

### The fifteen attacks

The reference bot plays light-only by design, so it cannot see the neutral, heavy
or ultimate slots. The suite pins the relationships between slots, not the values.
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

### Five classes, one campaign

Every stage is tuned against the Knight and only checked against the other four.
They are **not balanced against each other** — the Rogue and the Archer take about
17% of their health on a median stage where the Knight takes 28%, and no attempt
has been made to close that.

---

## Engineering

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
short script is still the trade being made at forty stages, and it is well past
the line it was near at twenty. Forty hand-written `Stage` literals is where the
absence of an editor is felt: placing a pillar means picturing a rectangle, and
placing an enemy means checking by eye that it is not inside one. The generator
refuses to write an unplayable campaign, which catches the second mistake but
not the interesting one — an enemy stranded in a pocket it never leaves is a
perfectly playable stage that nobody can finish.

### No CI

`python -m pytest` is the whole gate. See [Testing](testing.md).
