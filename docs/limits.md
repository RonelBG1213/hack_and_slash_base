# Known limits

Everything here is known, and most of it is deliberate. Where a limit was a
decision, the reasoning is given — so that reversing it is a decision too, taken
with the same information.

---

## Deliberate

### Almost no progression that makes you hit harder

For nineteen of the twenty stages, none at all. The shop sells health now, health
per stage, and gold find; nothing it stocks touches damage, speed or maximum
health.

That is load-bearing rather than squeamish. Because the hero's **output** does not
grow across a run, health on a later boss buys fight *length* and nothing else —
so the act bosses are not much tougher than the first and take their difficulty
from reach, cadence and arena instead. Both later bosses were drafted far tankier
and were unwinnable on every seed.

**The one exception is [promotion](design.md#promotion), and it is confined to the
last stage on purpose.** An advanced class changes maximum health and replaces two
attacks, which is exactly the kind of change the paragraph above says the game
cannot absorb. It is survivable here only because there is no stage after it: no
later fight has to be re-tuned around a hero that hits harder, because there is no
later fight. Moving the trigger earlier is one condition in `play.py` and a
re-tune of everything after it.

What still has no answer is equipment. Selling a damage upgrade would need a
per-`Entity` stat layer that every lookup in the game went through, and would
invalidate the whole recorded balance grid on the day it shipped. Promotion sits
in `EntityType`, which is frozen content — it swaps which type a body points at
rather than adding a layer under it.

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

### The ten advanced classes, and the twenty attacks they bring

The largest unmeasured surface in the project. `autoplay` plays light-only *and*
never promotes, so it cannot see any of this — not the classes, not their heavies,
not their ultimates. Every number was reasoned about and none was measured.

That is also what keeps the balance grid honest: promotion is offered by the
scene, never by the bot, so the recorded 5×20 grid measures the same game it
measured before any of this existed. The two facts are the same fact.

One further hole specific to the trigger: because promotion happens on the way
into the last stage, a branch can only ever be judged against the Sovereign. No
data exists on whether any of them would be sane for fifteen stages.

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
short script is still the honest trade at twenty stages, though it is nearer the
line than it was at four.

### No CI

`python -m pytest` is the whole gate. See [Testing](testing.md).
