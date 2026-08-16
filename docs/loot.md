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

## The shop

Opens between every stage and pauses the game, which nothing else in a run does —
the between-stage banner deliberately does not. Spending gold is a decision, and a
decision taken while a grunt walks up behind you is a decision taken badly.

| Good | Price | Effect | Cap | From |
| --- | --- | --- | --- | --- |
| Poultice | 90g | +30 health now, clamped to your maximum | — | stage 1 |
| Tonic | 260g | +6 health back after every stage, permanently | 5 | stage 1 |
| Charm | 340g | +25% gold find, permanently | 4 | stage 1 |
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
So the whole sink is in the late shelf: 12,260 to max everything, about half a
run, which is the same fraction 2,060 was of the run it was priced against.

**None of the four touches what a class is** — no damage, no speed, no maximum
health. That is load-bearing rather than squeamish; see
[Limits](limits.md#almost-no-progression-that-makes-you-hit-harder) for why —
and for the single exception, which is [promotion](design.md#promotion).

Keys `1`–`4` buy; Enter, Space or Esc leaves. The shop draws three rows for the
first twenty stages and four after, and the row a player reads is always the key
they press — `shop.available()` is what both the panel and the key handler use. The shop swallows every other
control while it is open, including Esc, which is "back to the menu" everywhere
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

The prices are set against the full figure: 12,260 to max everything, about half
a run, with all of the increase in a shelf that does not appear until stage 21.

> [!WARNING]
> **Nothing measures whether any of it is worth buying.** `autoplay` never spends
> and never detours for a pickup. That is exactly why the recorded balance grid is
> provably unmoved by the loot layer — and exactly why nobody knows whether four
> Tonics trivialise act two.
>
> So the drop rates, the rarity worths and the four effects remain a first pass.
> The suite pins only the relationships — rarer is worth more and drops less, a
> deeper floor pays more, a bigger monster pays more — never the values.

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

---

## How it works

Two implementation facts worth knowing before changing anything here.

**Loot never draws from `world.rng`.** It has its own seeded generator. This is
the guarantee that adding loot to a tuned game moved nothing — see
[Architecture](architecture.md#two-random-streams-not-one).

**Drops are swept up the moment a stage is won, and that is not a convenience.**
A stage is won on the tick its last enemy dies, and the run layer builds the next
`World` on that same tick — so a drop from the final kill would be destroyed
before anyone could walk to it. `sim._settle` judges the run, pays out the dead,
*then* culls them, in that order: a body that has already been culled cannot be
asked what it was worth.

**Pickups are not entities.** They sit beside projectiles on the `World`. A
pickup in `world.entities` would be handed to the broadphase, the separation pass
and every AI brain in the game.
