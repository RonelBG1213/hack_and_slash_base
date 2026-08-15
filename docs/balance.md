# Balance

```sh
python tools/balance.py
python tools/balance.py --class all --seeds 8
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
| **every stage**, entered at full health | clear on every seed | 8/8 each, 4–18s |
| **whole run**, health carrying | clear on every seed | 8/8, ~52s, worst finish 58/100 |
| **face-tank** — walks in swinging, never disengages | **lose every run** | 0/8 |

Only the floor and the game is unfair; only the ceiling and there is no game.
`tests/test_playthrough.py` pins all three, plus a 5×20 class×stage grid.

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

### A zero-tick reaction is an artifact, not skill

A hero answering every telegraph on the tick it opens rolls perpetually against
something winding up or swinging half the time — the boss — and never swings back.
It loses 7 of 8 runs where the twelve-tick policy wins all 8. So the reference
hero is the twelve-tick one.

That was invisible until there was a boss to expose it, and it is the reason to
distrust any single bot as a stand-in for a player.

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

Two holes, both deliberate and both stated where somebody will trip over them.

**The fifteen attacks.** The reference bot plays light-only, which is what keeps
every recorded number meaning what it meant when it was recorded. It cannot see
the neutral, heavy or ultimate slots. The suite pins the relationships between
slots, not the values.

**The shop.** `autoplay` never buys. See [Loot](loot.md#what-is-measured-and-what-is-not).

Both are the same trade, taken twice: the instrument stays fixed so the grid stays
comparable, and the price is that new systems ship unmeasured and say so.

## Known-bad cells are recorded, not deleted

`UNTUNED_STAGES` and `UNTUNED_CAMPAIGNS` in `tests/test_playthrough.py` map a cell
to a reason and produce a strict xfail. See [Testing](testing.md#known-bad-cells)
for the policy and why the *count* is the gate.
