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
works and rolling constantly does not. Its distance is fixed by your class and
nothing in the game raises it, the Boots included: how far a roll travels is how
much ground one invulnerable window covers, so selling that would be selling
invulnerability rather than mobility.

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
| **The Hollow King** | VIII | The Sovereign again with every dial a shade further on. Nothing new on the fortieth stage of a run, on purpose. |
| **The Regent** | IX | The only one with no standoff phase. Fastest body past the fork, the longest commit range in the game, and the shortest recovery on any boss sweep — a pillar is not a rest, and its arena has none in the middle. |
| **The Unmade** | X | The last fight, made of what the campaign taught: the Gaoler's reach, the Choir's fan and the Sovereign's charge on one body. Most health in the game; slow enough that the room is winnable and standing in the wrong part of it is what kills you. |

> The boss brain reads its weapons **positionally** — index 0 is the close sweep,
> 1 the charge, 2 the projectile. Adding a boss means declaring them in that
> order. See [Content](content.md#adding-a-boss).

---

## Difficulty

Three tiers, chosen on the character select beside the class and never revisited
— a run is one arc, and a dial turned halfway through makes the health carried
out of stage 12 mean something different from the health carried into it. `R`
restarts on the tier the run was begun on, for the same reason it restarts as the
base class.

| Tier | What it changes |
| --- | --- |
| **Forgiving** | A mistake costs 70% of what it costs on Normal |
| **Normal** | The game as it is tuned. Every recorded number describes this tier |
| **Relentless** | A mistake costs 130% |

**One dial, and it is damage the hero takes.** Not enemy health, not cadence,
not counts — so an enemy's time-to-kill is identical on every tier and a fight
learned on one reads the same on another. That choice is not a simplification:
enemy health has already been measured here as close to inert, because the
enrage threshold is a fraction and hero output never grows. See
[Balance](balance.md).

**Normal is not a tier so much as the absence of one.** At the default the
multiply is skipped by an early return, so the arithmetic is the arithmetic the
280-cell grid was measured against — and `data/difficulty.json` refuses to load
if its default is anything else. The other two ship marked untuned, flagged on
the select screen as well as in the data file, until the sweep says otherwise.

> The one bracket a difficulty setting can quietly break is the ceiling: *only
> the floor and the game is unfair; only the ceiling and there is no game.* A
> hero that walks in swinging has to lose every run on the gentlest tier too,
> and the suite pins that against whichever tier is gentlest rather than against
> a name.

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
| **Neutral** | `Q` | ~3s, and the only slot that is not an attack. A self-buff: no damage, no hitbox, reach 0. Answers the situation the light attack is worst in by changing the hero for a few seconds rather than by hitting something. |
| **Heavy** | `E` | ~5s. Roughly double the light attack in damage and in commitment. |
| **Ultimate** | `F` | ~25–30s. The largest payoff the class has. Once or twice a stage. |

A neutral answers the class's own worst situation, and it does it by changing the
hero rather than by hitting anything — that is the point of it, and it is why the
slot deals no damage at all. A 30-tick greatsword cycle with three grunts on you
is the Knight's actual problem, and more damage was never the answer to it.

**One buff per starting class, inherited by both branches it promotes into**, so
there are five and not fifteen — the same rule that already governs the light
attack. Four of them lean on the attribute that class's identity already names,
and the fifth reaches for something the attribute layer does not have:

| Class | | What it grants | Why that one |
| --- | --- | --- | --- |
| Knight | Resolve | `defense` | The commitment it cannot walk out of, made survivable |
| Rogue | Bloodlust | `crit_chance`, `crit_damage` | A five-damage dagger against durable enemies is the worst matchup in the game, and a crit rate is worth what the class's swing rate makes it worth — where a flat point would be worth three times as much to the Magician |
| Archer | Quickstep | `move_speed` | "Can you keep the room between you", bought continuously instead of once |
| Magician | Focus | `damage` | The hardest single hit in the game, made harder — and flat, so it is a third of a bolt and a sixth of a lance. Lining the window up with the seven-shot Nova is the class's one real combo |
| Priest | Benediction | `regen` **+ haste** | The only one that does two things, and the second is the headline: every *other* skill is stamped at 70% of its cooldown while it runs. The Priest's window is a rhythm rather than a stat — press Q first and the rest of the kit comes back faster |

The vehicle is the attribute layer, so almost nothing new happens in a fight: a
buff is a third `Attributes` block summed into `Entity.attrs` for a number of
ticks, and crit draws from `world.attr_rng` exactly as it already did. **Every
buff is shorter than the cooldown gating it**, so two can never overlap and a cast
replaces rather than stacks — pinned by test, so the question never has to be
answered at the call site.

**Haste is the one thing a buff does that is not an attribute**, and it sits on
the weapon rather than in the block on purpose. `progression.SPENDABLE` is derived
from the fields of `Attributes`, so a ninth field there would be a stat every
class can buy at a shrine, a ninth row on a character sheet whose eighth already
draws through the hint, and a ninth key on the level panel. Cooldown reduction is
a skill effect, so it lives on the skill.

> [!IMPORTANT]
> **A buff never hastes its own gate.** `actions.hasted` refuses on any weapon
> that is itself a buff, and that is the safety story rather than a detail: let
> it through and pressing the slot on cooldown shortens the wait for the next
> press, which shortens it again, until the buff is permanently live. Refusing
> keeps `0 < buff_ticks < cooldown` a *static* property of the content files
> instead of one that depends on what the hero happens to be carrying. Keyed on
> `is_buff` and not on the slot index, so it survives the buff moving off Q.
>
> Haste does not touch the dodge either. `dodge_cooldown` is the roll, which is
> designed against its own i-frame window, and shortening it is buying
> invulnerability rather than readiness — the same line `move_speed` already
> declines to cross.

Being hit during the windup loses you the cast *and* the cooldown, like any other
attack. That is what keeps the commitment real, and it falls out of the state
machine rather than being coded for.

> [!IMPORTANT]
> **The neutral, heavy and ultimate slots are the part of the game that has not
> been measured**, and the neutral is now the furthest out of reach of the two
> instruments — the skill-using bot skips the slot explicitly, because a policy
> with no model of *buff, then fight* would measure its own attack ordering
> rather than the buff. The rest of this note stands unchanged — fifteen attacks across the starting classes and twenty more
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

Fifty stages in ten acts. An act introduces one enemy, spends three stages
combining it with everything that came before, and ends on a boss. Enemy counts
rise inside an act and reset at the start of the next one, because a new idea
deserves room.

The seam is [promotion](#promotion), and there is exactly one. Stages 1–20 are
fought as the class you chose, ending on the Sovereign; stages 21–50 are fought
as the class you become. Acts VII and VIII introduce no new enemy, the same way
act IV does not — two acts of new creatures is enough per half, and an act that
taught something new at the end would be teaching it at the moment the player
can least afford to learn.

**Acts IX and X introduce none either, and the fork is why.** A stage is hard
for the hero that fights it, and which hero that is changes exactly once. Acts V
and VI could each afford a new creature because the class meeting it had just
doubled its kit; nothing of the sort happens at stage 41, so a ninth creature
there would be a step up with nothing handed over to answer it. Those ten stages
are built out of the four things that ask more of a player without asking
anything new of their class — count, placement, cadence and reach. Act IX takes
the arena itself away: act VIII's rosters in the tightest rooms since act II,
where a revenant is between you and where you were going rather than somewhere
in a large hall. Act X gives the floor back and fills it.

**A new face is not a new enemy**, and the distinction is deliberate. Most stages
field *variants* — a goblin, an orc, a beastman — that are byte-identical to the
grunt, brute and revenant they stand in for. They exist so eight creatures can
carry fifty stages without the campaign looking like eight creatures, and because
they carry no numbers of their own they teach the player nothing false: a body
the size of a brute hits like a brute, whatever colour it is. What an act
introduces is still one *idea*, and the count of ideas has not moved.

Health carries between stages and you recover a fixed amount on clearing one. How
much is the class's own number, and for the Priest it is most of the class. So a
run is a single arc rather than fifty separate fights, and a bad stage costs you
rather than ending you.

`R` starts a new run as the same class, never a new stage: replaying a boss at
full health is exactly the tension the carry-over exists to create. It restarts
as the **base** class, whatever you promoted into — a restart is a second
attempt at the run, and the fork is part of the run.

Gold carries too — see [Loot and gold](loot.md).

### The rooms between

Between two arenas is a **reward room**: a small walkable box with one fixture at
its centre and three doors, standing on the three walls you did *not* come in
through. Four kinds, and they are the whole of what a run gives you that is not a
fight.

| Room | What is in it |
| --- | --- |
| **The Spring** | A fountain. Heals a percentage of your maximum, on top of what clearing the stage already gave you |
| **The Stall** | The shop. **This is now the only way into it.** Three pieces of gear rolled for this room, over the five consumables |
| **The Shrine** | A point, and **three of the eight attributes** to spend it on — and the only way to reach that panel in the shipped game, since nothing earns experience |
| **The Cache** | A chest, worth more the deeper you are |

The doors name **the room after the *next* arena**, not the one you are about to
walk into. That one-room delay is the whole of what makes it a choice rather than
a menu: you are deciding what you will want on the far side of a fight you have
not had yet, and the fixture in front of you was chosen two rooms ago by somebody
who did not know how that fight would go. The room after stage one was never
chosen at all, so it is fixed — a fountain, which is also where the mechanic
explains itself.

**The door you take is the wall you arrive by.** Walk out of the east side of one
room and you are standing at the west side of the next, choosing between its
north, east and south. That is the whole of why a room is somewhere you have been
rather than a screen that repeats: the three walls in front of you are three
walls *because of the last decision you made*.

> [!IMPORTANT]
> **The shop no longer opens on its own, and it is now on a timetable.** It used
> to open on every one of the thirty-nine transitions, whether or not there was
> anything to decide, and the pause was the same length whether you spent four
> hundred gold or nothing. What changed is not the shop — the panel, the shelves
> and the keys are untouched — but that reaching it is somewhere you go.
>
> **The stall stands on every third floor, and on every floor that follows a
> boss**: floors 3, 5, 6, 9, 10, 12, 15, 18, 20 and so on, eighteen of them in a
> run. Off those floors a stall is not rare, it is unreachable — which is what
> makes one a landmark rather than a fixture.
>
> The boss half is a rule rather than a coincidence, and it used to be the other
> way round. At `stall_every: 5` the interval landed on 5, 10, 15 … 40 — exactly
> the eight act bosses — so a shop after every boss fell out of the arithmetic
> and nothing recorded that anyone wanted it. Moving the interval to three would
> have thrown it away silently, so it is written down now: `stall_on_boss_floors`
> in [`data/rooms.json`](../data/rooms.json), reading where the bosses actually
> stand rather than carrying a list that could disagree with them.
>
> Gold that can never be spent is not a reward, and a schedule promises that
> better than the guarantee it replaced ("a stall within four transitions if none
> turned up"). You are not trusting one to appear; you know where it is.

The cost, and it is real: there are three kinds outside the stall and three doors,
so off a stall floor every room offers all three and only their order moves. The
old tension — four kinds, three doors, one always missing — now survives only on
the stall floors. Two doors would bring it back everywhere, and `doors` in
[`data/rooms.json`](../data/rooms.json) is the one number that would do it.

None of the four fixtures is measured, and that is a decision rather than an
oversight — the reference bot walks past all of them, which is what keeps every
recorded number in the project meaning what it meant. See
[Balance](balance.md#the-brackets) for what happened when it did not.

### What the floor does at depth

Until floor three the ground is safe and the only thing you read is what is
walking at you. After it, the arena itself is part of the fight.

| Trap | From | The question it asks |
| --- | --- | --- |
| **Spike** | floor 3 | *Are you standing still?* A floor plate that blinks — dormant, a tell, then teeth |
| **Flame** | floor 9 | *When do you cross?* Bolted to a side wall, firing a lane inward on a long cycle |
| **Blade** | floor 16 | *Where will it be?* A pendulum on a track, and the only one that cannot be waited out |

They arrive one per act, in that order, because a mechanic gets taught alone or
it does not get taught. **How many an arena carries also comes from the floor** —
one at first, four by the thirties — so depth means both new traps and more of
them. The numbers are all in [`data/hazards.json`](../data/hazards.json).

**The roll is the answer to all three.** A dodge's i-frames pass through a jet
exactly as they pass through a sword, which is the whole reason the layer could
be added without a new defensive verb. What a trap will *not* do is stagger you
or cancel the swing you were mid-way through: a mistimed step should cost health,
not health and the attack, because the two together is more than the mistake was
worth.

> [!IMPORTANT]
> **Traps hurt you and not them, and that is deliberate.** Nothing in this game
> paths around anything — enemies walk in straight lines at you, which is the
> constraint half of `tools/make_level.py` is about. Faction-neutral traps would
> therefore make the best play *stand behind the spikes and let the pack walk
> in*, and a floor-forty arena with four traps would be easier than a floor-three
> arena with one. The mechanic would invert its own intent.
>
> `harms` in [`data/hazards.json`](../data/hazards.json) flips it, and the day
> anything in this game paths, that is the line to revisit.

The eight act enders carry no traps. Not because a boss with traps is a bad idea
— because those are the most tuned cells in the game and the boss brain is
positional, so shoving one around should be a decision rather than a side effect
of switching this layer on. `bosses` is that switch.

Unlike the fixtures above, **every number here is on a measured tick.** The
campaign was re-swept with the traps in it and every individual arena still
clears — all 280 class x stage cells, on every seed, at full strength.

What that sweep cannot tell you is whether a whole forty-stage *run* with traps
is tuned, and the reason is worth reading before trusting any number here:
[Traps, and the limit of the run-level bracket](balance.md#traps-and-the-limit-of-the-run-level-bracket).

A reward room is **not a fight, and the code knows the difference by being told**
rather than by noticing there is nothing in it. `Level.kind` says what a room is
for; a room outside `FIGHTING_KINDS` is never cleared by being empty, which is
what stops a fountain being finished on the tick it opens. It is also why boss
arenas carry a kind of their own — the eight act enders declare it in
`tools/make_level.py`, so the campaign's shape is a claim the data can be checked
against rather than an index computed twice.

### Attributes and levels

> [!NOTE]
> **The levelling half is switched off; the attributes are reachable by two
> other roads.** Eight attributes — crit rate, crit damage, health, damage,
> defense, dodge, health regen and move speed — and a level-up system that feeds
> them: kills pay experience, levels pay points, a panel spends them. The
> *earning* is what ships off: `data/progression.json` sets `xp_base: 0`, so no
> kill is ever worth anything and no level is ever reached.
>
> Two things reach the attributes anyway, and neither goes through experience.
> **The gear a stall rolls**, and **the Boots** beneath it, buy attributes with
> gold. **The shrine**,
> one of the four reward rooms, hands out a point directly — so the panel a
> levelling system would have opened is opened by walking up to a standing stone
> instead. See [the rooms between](#the-rooms-between) and
> [Loot and gold](loot.md#the-stall).
>
> That split is the point rather than an accident. Turning experience on would
> pay out on every kill on all forty stages and move the recorded grid on the day
> it landed; a shrine pays out where the run is already stopped, on a room the
> player chose, and the grid cannot see a room at all.
>
> That is deliberate and it is the only way this could land on a tuned game.
> Every attribute defaults to the identity of its own operation, so the
> arithmetic is provably the arithmetic all forty stages were measured against
> — see [Limits](limits.md#the-attribute-layer) for how, and
> [Balance](balance.md#what-is-not-measured) for what has to happen before the
> dial goes up.

Two of the eight sit awkwardly against the rest of this document, and it is
better to say so here than to discover it in play.

**Dodge is a die the game rolls for you**, and the opening line of this document
says a hit is a decision you made rather than something the arena did to you. It
is priced as a garnish for that reason, it is zero on every enemy, and it is the
attribute most likely to be cut once somebody plays it.

**Defense compresses the classes.** A Rogue swings for 5 and a Magician for 15,
so a flat point off every hit is worth three times as much against the Rogue —
and `MIN_DAMAGE` floors every hit at 1 underneath, which turns enough of it into
a stage that cannot end rather than a fight that is hard. It is zero on every
enemy, and the enemy side of it is the piece least likely to survive tuning.

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
[Limits](limits.md#the-twenty-attacks-the-advanced-classes-bring).
