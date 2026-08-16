# Design

What the game asks of the player, and why each piece is shaped the way it is.

[Loot and the shop](loot.md) is a separate document. So is [how any of this was
measured](balance.md) — this one is the intent, that one is the evidence.

---

## The fight

You are faster than everything you fight. That is the deal the whole arena rests
on — in open ground you can always break away, so taking a hit is a decision you
made rather than something the arena did to you. Boxed in by five things at once,
you cannot, and that is the arena working as intended.

Every attack in the game runs the same three phases:

```
WINDUP  ->  ACTIVE  ->  RECOVERY
 tell      hitbox      punishable
```

Only `ACTIVE` can hit anything. **Windup** is the tell — it is what makes an
attack readable, and it is the first number to change when something feels
unfair. **Recovery** is the price of missing: whiffing into empty air is a
mistake, not a free action.

Your dodge roll is invulnerable from its very first frame, and the
invulnerability ends *before* the roll does — so rolling at the right moment
works and rolling constantly does not.

You keep a fraction of your speed mid-swing, not none of it — committing to an
attack should cost position, not responsiveness.

---

## The enemies

Each one asks a different question, and the answer is always positional.

| Enemy | What it asks you |
| --- | --- |
| **Grunt** | Can you make space? Walks in and swings. |
| **Charger** | Are you standing in a line with it? Long telegraph, committed dash — sidestep it or eat it. |
| **Bowman** | Are you standing still in the open? Keeps its distance and needs line of sight, so pillars are the answer. |
| **Mage** | The same question from further out, and it hurts more. The hex is slow enough to walk out of, so it costs you position rather than health. |

Two more arrive later. The **rat** is almost as fast as you are, so unlike a
grunt it cannot be walked away from and left — it dies to one hit of anything and
never turns up alone. The **brute** is the opposite: slow enough to ignore and
tough enough that killing it costs you the attention everything else in the room
wants.

Two more again, after the fork, and both are built to take away something the
first twenty stages let you rely on:

| Enemy | What it asks you |
| --- | --- |
| **Revenant** | Which of these can you afford to leave? A brute's durability at a grunt's walking pace — the one thing in the game that is both too tough to kill quickly and too fast to walk away from. |
| **Stalker** | Can you still afford that? A charger that commits from further out and tells you later. It is aimed squarely at the heavy and the ultimate a promotion just handed you, which are the longest commitments you have. |

### The bosses

Each act ends on one, and all eight ask the same three questions from the same
three distances — sweep up close, a committed charge at mid range, a fan of shots
from far — so every position has a known answer and the fight is about moving
between them. Below half health each one stops pausing between attacks. None of
them learns a new move, so nothing you worked out stops being true.

| Boss | Act | What is different about it |
| --- | --- | --- |
| **The Warden** | I | The one that teaches the pattern. Slowest thing in the game, longest gaps between attacks. |
| **The Houndmaster** | II | The same three questions in a hurry — faster body, shorter tells, a tight three-shot spray. |
| **The Effigy** | III | The opposite reading. Enormous reach, the longest telegraph in the game, embers everywhere. |
| **The Sovereign** | IV | Nothing new, and no room. Nine shots across a half-circle, and the reach to punish standing anywhere. |
| **The Herald** | V | The Houndmaster's hurry at the Sovereign's reach. Deliberately a pattern you already know — the unfamiliar thing in this fight is meant to be your own new class. |
| **The Gaoler** | VI | Slowest body in the game, longest reach in it. A chain across 240 degrees denies more floor than anything else; you have to already be elsewhere when it opens. |
| **The Choir** | VII | Eleven shots from further out than anything shoots. The weakest of the eight up close, and the arena is the most heavily pillared in the game, because closing the distance is the fight. |
| **The Hollow King** | VIII | The Sovereign again with every dial a shade further on. Nothing new on the last stage of a forty-stage run, on purpose. |

> The boss brain reads its weapons **positionally** — index 0 is the close sweep,
> 1 the charge, 2 the projectile. Adding a boss means declaring them in that
> order. See [Content](content.md#adding-a-boss).

---

## The classes

You pick one before the run. It is almost the whole of character building — the
one other decision comes twenty stages later, in [Promotion](#promotion) below.

| Class | What it asks of you |
| --- | --- |
| **Knight** | Can you afford to commit? Most health, most damage, worst mobility. The reference class — the campaign is measured against it. |
| **Rogue** | Can you stay in? Fragile and very fast, with a swing so short that whiffing costs nothing. |
| **Archer** | Can you keep the room between you? Ranged, and a shot spends itself on the first thing it meets — so the pillars that protect you eat your damage too. |
| **Magician** | Can you find the gap? The hardest single hit in the game, behind the longest commitment. |
| **Priest** | Can you last? Unremarkable in any one fight, and recovers two thirds of its health between stages. |

### The four slots

Every class has four attacks, on ascending commitment and ascending cooldown.

| Slot | Key | What it is |
| --- | --- | --- |
| **Light** | click / `J` | No cooldown. The attack in the table above — the one the class *is*. |
| **Neutral** | `Q` | ~3s. Answers the situation the light attack is worst in, and always hits for less. The Archer's kick, the Magician's ward, the Rogue's thrown knife. |
| **Heavy** | `E` | ~5s. Roughly double the light attack in damage and in commitment. |
| **Ultimate** | `F` | ~25–30s. The largest payoff the class has. Once or twice a stage. |

A neutral buys position rather than kills things — that is the point of it, and it
is why every one of them does less damage than the attack it sits beside. The
Knight's Shield Bash shoves a crowd nearly twice as far as a greatsword swing for
five damage, because a 30-tick greatsword cycle with three grunts on you is the
Knight's actual problem and more damage was never the answer to it.

> [!IMPORTANT]
> **The neutral, heavy and ultimate slots are the part of the game that has not
> been measured** — fifteen attacks across the starting classes and twenty more
> across the ten they promote into. The reference bot plays light-only by design,
> which is what keeps every recorded number still meaning what it meant, so it
> cannot see the other three slots for any of the fifteen classes. The suite pins
> the *relationships* between slots, not the values. Treat the numbers as a first
> pass. See [Balance](balance.md).

Only the light attack has to obey the rule that a hero starts a swing faster than
any enemy does. A heavy telegraphing for half a second is a commitment you chose
to spend with a cooldown behind it, which is not the same thing as an enemy
striking before you can answer.

The slot order is a contract between the content files, the input layer and the
HUD — `game/skills.py` names the indices so they are not bare integers in three
places, and a test fails if a class declares its attacks in another order.

---

## The run

Forty stages in eight acts. An act introduces one enemy, spends three stages
combining it with everything that came before, and ends on a boss. Enemy counts
rise inside an act and reset at the start of the next one, because a new idea
deserves room.

It is two halves of four acts, and the seam is [promotion](#promotion). Stages
1–20 are fought as the class you chose, ending on the Sovereign; stages 21–40
are fought as the class you become. Acts VII and VIII introduce no new enemy,
the same way act IV does not — two acts of new creatures is enough per half, and
an act that taught something new at the end would be teaching it at the moment
the player can least afford to learn.

Health carries between stages and you recover a fixed amount on clearing one. How
much is the class's own number, and for the Priest it is most of the class. So a
run is a single arc rather than forty separate fights, and a bad stage costs you
rather than ending you.

`R` starts a new run as the same class, never a new stage: replaying a boss at
full health is exactly the tension the carry-over exists to create. It restarts
as the **base** class, whatever you promoted into — a restart is a second
attempt at the run, and the fork is part of the run.

Gold carries too, and between stages there is a shop — see [Loot and
gold](loot.md).

---

## Promotion

Clear stage twenty — the Sovereign, and the end of the campaign's first half —
and the class you have been playing forks into two. Keys `1` and `2` choose.
There is no third answer: the panel has no exit key and the arena stays paused
until you pick one.

| Base | Kill it faster | Outlast it |
| --- | --- | --- |
| **Knight** | Dark Knight | Holy Knight |
| **Rogue** | Assassin | Shadow Rogue |
| **Archer** | Hunter | Magic Archer |
| **Magician** | Wizard | Sage |
| **Priest** | Battle Priest | Holy Priest |

An advanced class **keeps the light and neutral attacks you have used for twenty
stages** and replaces the heavy and the ultimate. Health changes; speed, body
size and the dodge do not, with one exception — the Shadow Rogue, whose whole
identity is the roll.

> [!IMPORTANT]
> **This is a second half, not a capstone.** It used to be one fight, and
> everything about the shape of these ten classes still shows it: they are two
> attacks and a health number, because that is all a capstone needs. Twenty
> stages now follow, which changes what the decision is worth without changing
> what it is.
>
> Two consequences worth knowing. `heal_between_stages` is now a live dial — it
> pays out on every stage after the fork — and the second half needed more of it
> than the first: the Knight line recovers 84 where the Knight recovers 56, the
> Rogue line 60 where the Rogue recovers 38, and the other three lines needed
> nothing. **The fork is still never a decision about healing**, though: the two
> branches of a class always share the number, so "the healing one" cannot be
> anybody's pitch.
>
> The second: because the light attack is inherited, an advanced class swings
> what its base class swung. That is why the fork can sit in the middle of a
> campaign at all — the hero's damage per swing does not jump, so the twenty
> stages after it are tuned much the way the twenty before it were.

Promotion is offered once per run and cannot be revisited or declined. `R`
restarts as the **base** class — the advanced ones are not on the character
select and never appear there.

**The classes are measured; their new attacks are not.** The reference bot
promotes now, so all ten advanced classes are swept against all twenty late
stages — but the bot presses only the light attack, and the light is inherited.
So what the grid checks is each branch's health and body against acts V–VIII,
and the twenty heavies and ultimates remain a first pass. That is the same deal
the original fifteen attacks have, and it means the new kit is upside rather
than something a stage requires. See
[Limits](limits.md#the-ten-advanced-classes-and-the-twenty-attacks-they-bring).
