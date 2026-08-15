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

| Good | Price | Effect | Cap |
| --- | --- | --- | --- |
| Poultice | 90g | +30 health now, clamped to your maximum | — |
| Tonic | 260g | +6 health back after every stage, permanently | 4 |
| Charm | 340g | +25% gold find, permanently | 3 |

The two permanent goods are capped because they compound. Four Tonics is +24
health after every remaining stage; three Charms is +75% on everything that drops
afterwards. Uncapped, the correct play is to buy nothing but Charms early, which
is a strategy the shop should not have.

**None of the three touches what a class is** — no damage, no speed, no maximum
health. That is load-bearing rather than squeamish; see
[Limits](limits.md#no-progression-that-makes-you-hit-harder) for why.

Keys `1` `2` `3` buy; Enter, Space or Esc leaves. The shop swallows every other
control while it is open, including Esc, which is "back to the menu" everywhere
else — dropping somebody out of a twenty-stage run because they reached for
Escape to shut a panel is not a trade worth making.

---

## What is measured and what is not

A full run banks about **4,700 gold** — around 33 on floor 1, rising to 400–550 on
the late floors — measured with the same bot the rest of the [balance
work](balance.md) uses.

| Class | Run 1 | Run 2 |
| --- | --- | --- |
| Knight | 5,035 (won) | 4,696 (won) |
| Rogue | 4,709 (won) | 4,601 (won) |
| Archer | 4,726 (won) | 4,676 (won) |
| Priest | 4,753 (won) | 4,646 (won) |
| Magician | 1,740 (died, stage 12) | 1,662 (died, stage 12) |

The prices are set against that. Maxing both permanents costs 2,060g, a little
under half a run, and the first Tonic is out of reach until roughly floor 4. The
first draft priced them at 45/120/150, which bought the whole shop out by about
stage 5 and left nothing to decide for the remaining fifteen stages.

> [!WARNING]
> **Nothing measures whether any of it is worth buying.** `autoplay` never spends
> and never detours for a pickup. That is exactly why the recorded balance grid is
> provably unmoved by the loot layer — and exactly why nobody knows whether four
> Tonics trivialise act two.
>
> So the drop rates, the rarity worths and the three effects remain a first pass.
> The suite pins only the relationships — rarer is worth more and drops less, a
> deeper floor pays more, a bigger monster pays more — never the values.

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
