# Loot and gold

Everything you kill drops gold, and one kill in four drops a valuable on top of
it. Both land on the floor and are picked up by walking over them; anything still
lying there when the room is cleared is swept up automatically, so finishing a
stage never costs you a drop.

Every number below lives in [`data/loot.json`](../data/loot.json).
`game/loot.py` and `game/shop.py` hold the arithmetic and none of the values.

---

## What a kill pays

```
gold = base × monster level × (1 + floor_step × (floor − 1))
```

rolled within ±20% and never rounding below 1. With `base 3` and `floor_step
0.15`: a rat on floor 1 pays 3, a Sovereign on floor 20 pays about 92.

Two multipliers rather than one, because they answer different questions.

**Monster level** is *was that worth fighting.* It is a number per enemy in
[`data/entities.json`](../data/entities.json), running from the rat at 1 to the
Sovereign at 8, and it is deliberately **not derived from health** — a Brute has
nearly four times a Bowman's hp and is worth twice as much, because most of that
health is time rather than danger.

**Floor step** is *how deep are you.* At 0.15 the twentieth floor pays 3.85× the
first, so the same rat is worth more down there without a rat ever becoming
interesting.

An enemy with no `level` quietly pays a rat's wage forever, which is not an error
anywhere — so `tests/test_entities.py` refuses an enemy still sitting on the
default.

## Rarity is worth, not power

There is no inventory and nothing to equip. A valuable's rarity multiplies the
gold the kill already produced.

| Rarity | Chance | Worth |
| --- | --- | --- |
| Common | 60% | ×1 |
| Uncommon | 25% | ×2 |
| Rare | 10% | ×4 |
| Epic | 4% | ×8 |
| Legendary | 1% | ×16 |

Weights in the data file are **relative, not percentages** — they are summed and
rolled against, so adding a tier does not mean rebalancing the others back to 100.

A legendary off the Sovereign on floor 20 is around 1,500 gold — roughly ten
stages of ordinary income, and meant to be the kind of thing you remember.

The weights are **flat across floors on purpose.** Depth already pays more
through the gold formula, and tilting the rarities as well is two dials doing one
job. If loot ever starts feeling samey deep in a run, that is the moment to add a
depth term — not before.

## The stall

**Reached by walking up to a stall in a shop room, and by nothing else.** It used
to open on every one of the thirty-nine transitions; it is now one of the four
things a reward room can hold, and getting to one means having chosen that door
two rooms earlier. See [the rooms between](design.md#the-rooms-between).

Opening it pauses the game, which nothing else in a run does — the between-stage
banner deliberately does not. Spending gold is a decision, and a decision taken
while a grunt walks up behind you is a decision taken badly.

It has **two sections**, one continuous run of digits down both:

- **Gear**, on top. Three pieces rolled for this room, at a rarity that scaled
  the piece and its price by the same factor, priced against the floor, and gone
  the moment you walk out. [Below](#the-gear-a-stall-rolls).
- **Goods**, underneath. The five consumables, the same five on every shelf of
  every run, [below](#the-goods).

## The gear a stall rolls

`data/equipment.json` holds a pool of twelve **pieces**. A piece is a name and an
`Attributes` block — it is not a weapon, it is not worn, there are no slots and
nothing is replaced. Buying one adds its block to `run.earned` permanently, which
is exactly the road the Boots already travelled and deliberately not a second
mechanism beside it.

Three of the twelve are drawn per stall, without replacement, and each gets its
own **rarity** roll off `data/loot.json`'s existing 60/25/10/4/1 weights. The
rarity multiplies the block and the price by the same factor:

| Rarity | Scale | A 300g Cuirass on floor 1 |
| --- | --- | --- |
| common | ×1 | 300g, +10 Health +1 Defense |
| uncommon | ×2 | 600g, +20 Health +2 Defense |
| rare | ×3 | 900g, +30 Health +3 Defense |
| epic | ×4 | 1,200g, +40 Health +4 Defense |
| legendary | ×6 | 1,800g, +60 Health +6 Defense |

**A rarity is never a better deal, only a bigger one.** Both halves move by the
same factor on purpose — if they came apart, one tier would be strictly the thing
to hold out for and the other four would be noise. What a good roll buys is the
*chance to spend a lot at once*, which matters precisely because a shelf is three
rows in one room and then never again.

The scale is deliberately **not** the loot table's `worth` (1/2/4/8/16). A 16×
gold pile is a number, spent and gone; a 16× attribute block is permanent and
compounds with everything bought after it, so the same curve there would make one
lucky stall the whole run.

Price carries the same 0.15 depth step a kill and a chest already use, so the
fortieth floor prices a piece at 6.85× the first — about what the fortieth floor
pays, which is what keeps a late stall roughly as affordable as an early one.

Two rules are enforced at load rather than left to taste:

- **At most two attributes per piece.** The blurb column has about 150px before
  the rarity word, and a third field draws through it.
- **Every rarity in `data/loot.json` must have a scale, and vice versa.** Both
  directions, the way `shop.stock()` and `progression.Table.load` check theirs.

**The roll is stateless.** It comes from a `Random` built out of `(seed, index)`
and thrown away — `rooms.offer`'s trick, for `rooms.offer`'s two reasons. It
cannot reach `world.rng`, and a run picked back up off disk finds the same three
pieces at the same prices with the save file saying nothing about a shelf at all.
The one thing that *is* recorded is which rows were bought, and that rides in
`run.purchases` under an `eq:` prefix beside the shop's own tally — no save field
and no migration.

> [!WARNING]
> **This re-opens a documented dead end, deliberately.** A stat upgrade in the
> shop was refused for years because `EntityType` is frozen content shared by
> every run of a class, so it needed a per-entity layer that did not exist. That
> layer is `game/attributes.py` and the Boots were the first good through it.
>
> What has *not* changed is the caution underneath: `autoplay` never enters a
> panel and never spends, so **nothing measures whether any of this is worth
> buying**. Every price and every scale is an opening bid in the same sense every
> number in `data/rooms.json` is. By the same token none of it moves a recorded
> bracket — `run.earned` is neutral in every sweep.

Rollback is a number: `stall.offers: 0` in `data/rooms.json` and the stall is the
five-row shop it replaced.

## The goods

> [!NOTE]
> **What that changes about the prices, which is nothing yet.** Every price here
> was set against a measured income of ~24,500g over a full run, and the income
> has gone *up* — chests pay, and `tools/balance.py` is the thing that measures
> it. But the number of shop *visits* has gone down and is no longer fixed, so
> "can this run afford four Tonics" now depends on how it spent its doors. None
> of that has been re-measured, and the prices are unchanged on purpose: moving
> them at the same time as the thing that reaches them would leave nothing to
> compare against.

| Good | Price | Effect | Cap | From |
| --- | --- | --- | --- | --- |
| Poultice | 90g | +30 health now, clamped to your maximum | — | stage 1 |
| Tonic | 260g | +6 health back after every stage, permanently | 5 | stage 1 |
| Charm | 340g | +25% gold find, permanently | 4 | stage 1 |
| Boots | 520g | +5% walking speed, permanently | 4 | stage 1 |
| Elixir | 2,400g | +10 health back after every stage, permanently | 4 | **stage 21** |

The permanent goods are capped because they compound. Maxed, that is +70 health
after every remaining stage and +100% on everything that drops. Uncapped, the
correct play is to buy nothing but Charms early, which is a strategy the shop
should not have.

**The Elixir is a shelf, not a mechanic.** It writes the same `bonus_heal` the
Tonic does — more of it, nine times the price, and not stocked until the first
stage after the fork.

It exists because of arithmetic. A forty-stage run banks about **24,500 gold**
where a twenty-stage run banked 4,700 — five times as much, because the floor
multiplier compounds. Against the old three shelves, 2,060 bought every
permanent in the game before the end of act II and left thirty stages with
nothing to decide: the same failure the first draft's 45/120/150 prices had,
arriving twenty-five stages later.

**The early prices are deliberately untouched.** They were measured against
4,700 gold and they still face 4,700 gold — the first half's economy did not
change. Tripling the Tonic to soak up the new income would have priced the first
one out of act I, which fixes a late-game problem by breaking an early-game one.
So the whole sink is in the late shelf: 14,340 to max everything, a little over
half a run, which is about the fraction 2,060 was of the run it was priced
against.

**The Boots are the one *good* that touches what a class is** — the gear above
them all does, and the Boots are what opened the door. The other four are
integers on the `Run`; the Boots write `move_speed` into the attribute block
that `Entity.attrs` sums, which is the same road levelling travels. That used to
be structurally impossible — `EntityType` is frozen content shared by every run
of a class, so a stat upgrade needed a per-entity layer that did not exist. It
does now, and this is the first thing in the shop to use it. See
[Limits](limits.md#almost-no-progression-that-makes-you-hit-harder) for what is
still deliberately not sold, and [promotion](design.md#promotion) for the other
exception.

Two things about it are decisions rather than details. **It is walking speed
only** — the dodge roll's distance is untouched, because how far a roll travels
is how much ground one i-frame window covers, so scaling it would sell
invulnerability rather than mobility. And **it is capped at four**, harder than
it looks: this game has no enemy pathing, so outrunning a crowd is the hero's
main answer to one. Uncapped speed does not make the shop a worse decision, it
makes the arena a solved one.

Its **price** is set against income like every other shelf. Its **amount is a
guess** — the only shelf here of which that is true, and it is flagged in
`data/loot.json` beside the drop rates for the same reason.

Keys `1`–`8` buy; Enter, Space or Esc leaves. The stall draws seven rows for the
first twenty stages and eight after — three gear, then four or five goods — and
the row a player reads is always the key they press. **`shop_panel.rows()` is the
one list both the panel and the key handler index into**, which is what makes
that true across two sections that are bought through two different functions.

The stall swallows every other control while it is open, including Esc, which is
"back to the menu" everywhere
else — dropping somebody out of a forty-stage run because they reached for
Escape to shut a panel is not a trade worth making. The promotion panel goes
further and has no exit key at all; see [Design](design.md#promotion).

---

## What is measured and what is not

A full run banks about **24,500 gold** — around 33 on floor 1 and several hundred
a stage on the late floors — measured with the same bot the rest of the [balance
work](balance.md) uses.

| Class | Run 1 | Run 2 | banked by stage 20 |
| --- | --- | --- | --- |
| Knight | 24,900 (won) | 24,664 (won) | 5,035 |
| Rogue | 24,409 (won) | 23,709 (won) | 4,709 |
| Archer | 25,561 (won) | 23,144 (won) | 4,726 |
| Priest | 24,922 (won) | 24,451 (won) | 4,753 |
| Magician | 1,740 (died, stage 12) | 1,662 (died, stage 12) | — |

The last column is worth more than it looks. Those four figures are identical to
the ones recorded against the twenty-stage campaign, to the gold — the same
seeds paying out the same amounts through the same twenty stages. It is the
economy's half of the proof that acts I–IV were not touched.

The prices are set against the full figure: 14,340 to max everything, a little
over half a run, with most of the increase in a shelf that does not appear until
stage 21.

> [!WARNING]
> **Nothing measures whether any of it is worth buying.** `autoplay` never spends
> and never detours for a pickup. That is exactly why the recorded balance grid is
> provably unmoved by the loot layer — and exactly why nobody knows whether four
> Tonics trivialise act two.
>
> So the drop rates, the rarity worths and the five effects remain a first pass.
> The suite pins only the relationships — rarer is worth more and drops less, a
> deeper floor pays more, a bigger monster pays more — never the values.
>
> The Boots join that list rather than lengthening it. The bot buys nothing, so
> `move_speed` is zero on every body in every sweep — and `sim._walk_speed`
> returns the type's own number at zero rather than multiplying it by one, so
> the grid is untouched as arithmetic rather than as a rounding argument.

### What the ceiling *is* measured on, as of the forty-stage pass

One thing that had never been checked in either direction: whether the caps allow
a purse to buy its way out of the game. A run with **every permanent maxed from
stage one** — +70 health a stage, +100% gold find — was played out against both
reference policies:

| | result |
| --- | --- |
| skilled hero, everything maxed | 6/6, worst finish **54** health |
| skilled hero, buying nothing | 6/6, worst finish **53** health |
| face-tank, everything maxed | 0/6, dying on stage 2 or 3 |

One point of health between them. That is a real finding rather than a null one:
past a certain point the hero dies **inside** a stage rather than to attrition
between them, and healing between stages has nothing to say about that. It is
also why the face-tank ceiling is unmoved by any amount of shopping — the bracket
that says the arena still applies cannot be bought off.

## Turning it off

Two edits in [`data/loot.json`](../data/loot.json): set `gold.base` to 0 and
`item_chance` to 0. Nothing then drops, the shop can never be afforded, and the
code goes quiet without being removed. That is also the rollback.

The rooms have their own switch and it is separate: `"enabled": false` in
[`data/rooms.json`](../data/rooms.json). No reward room is then built, a cleared
arena leads straight to the next one, and the shop goes back to opening on every
transition — which is the campaign exactly as it was measured. Kept apart from
the loot switch deliberately: one turns off what drops, the other turns off where
you spend it, and a single flag doing both would make either rollback cost the
other.

---

## How it works

Two implementation facts worth knowing before changing anything here.

**Loot never draws from `world.rng`.** It has its own seeded generator. This is
the guarantee that adding loot to a tuned game moved nothing — see
[Architecture](architecture.md#three-random-streams-not-one).

**Drops are swept up the moment a stage is won, and that is not a convenience.**
A stage is won on the tick its last enemy dies, and the run layer builds the next
`World` on that same tick — so a drop from the final kill would be destroyed
before anyone could walk to it. `sim._settle` judges the run, pays out the dead,
*then* culls them, in that order: a body that has already been culled cannot be
asked what it was worth.

**Pickups are not entities.** They sit beside projectiles on the `World`. A
pickup in `world.entities` would be handed to the broadphase, the separation pass
and every AI brain in the game.
