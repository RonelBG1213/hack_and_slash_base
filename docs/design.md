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

### The bosses

Each act ends on one, and all four ask the same three questions from the same
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

> The boss brain reads its weapons **positionally** — index 0 is the close sweep,
> 1 the charge, 2 the projectile. Adding a boss means declaring them in that
> order. See [Content](content.md#adding-a-boss).

---

## The classes

You pick one before the run. It is almost the whole of character building — the
one other decision comes nineteen stages later, in [Promotion](#promotion) below.

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
> **These fifteen attacks are the one part of the game that has not been
> measured.** The reference bot plays light-only by design — which is what keeps
> every recorded number still meaning what it meant — so it cannot see the other
> three slots. The suite pins the *relationships* between slots, not the values.
> Treat the numbers as a first pass. See [Balance](balance.md).

Only the light attack has to obey the rule that a hero starts a swing faster than
any enemy does. A heavy telegraphing for half a second is a commitment you chose
to spend with a cooldown behind it, which is not the same thing as an enemy
striking before you can answer.

The slot order is a contract between the content files, the input layer and the
HUD — `game/skills.py` names the indices so they are not bare integers in three
places, and a test fails if a class declares its attacks in another order.

---

## The run

Twenty stages in four acts. An act introduces one enemy, spends three stages
combining it with everything that came before, and ends on a boss. Enemy counts
rise inside an act and reset at the start of the next one, because a new idea
deserves room.

Health carries between stages and you recover a fixed amount on clearing one. How
much is the class's own number, and for the Priest it is most of the class. So a
run is a single arc rather than twenty separate fights, and a bad stage costs you
rather than ending you.

`R` starts a new run as the same class, never a new stage: replaying a boss at
full health is exactly the tension the carry-over exists to create.

Gold carries too, and between stages there is a shop — see [Loot and
gold](loot.md).

---

## Promotion

Clear stage nineteen and the class you have been playing forks into two. Keys `1`
and `2` choose; Enter declines and keeps you as you are.

| Base | Kill it faster | Outlast it |
| --- | --- | --- |
| **Knight** | Dark Knight | Holy Knight |
| **Rogue** | Assassin | Shadow Rogue |
| **Archer** | Hunter | Magic Archer |
| **Magician** | Wizard | Sage |
| **Priest** | Battle Priest | Holy Priest |

An advanced class **keeps the light and neutral attacks you have used for
nineteen stages** and replaces the heavy and the ultimate. Health changes; speed,
body size and the dodge do not, with one exception — the Shadow Rogue, whose
whole identity is the roll.

> [!IMPORTANT]
> **This is a capstone, not a second half.** One fight, against the Sovereign —
> so every branch is aimed at that specific fight's three questions, and nothing
> that pays off *between* stages can pay off at all. `heal_between_stages` is
> inherited unchanged and is inert; no branch differentiates on it, and a test
> enforces that so "the healing one" cannot be reinvented later.
>
> The Holy Priest is where this bites hardest: the obvious design for it is
> "heals more", which here is worth exactly nothing. Its identity is a
> full-circle ultimate and the second-hardest knockback in the game instead.

Promotion is offered once per run and cannot be revisited. `R` restarts as the
**base** class — the advanced ones are not on the character select and never
appear there.

**None of it is measured.** The reference bot never promotes, which is what keeps
the recorded balance grid measuring the same game it always did — and is exactly
why nobody knows whether Dark Knight trivialises the last fight. See
[Limits](limits.md#the-ten-advanced-classes-and-the-twenty-attacks-they-bring).
