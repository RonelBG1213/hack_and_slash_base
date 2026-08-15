"""Which of a class's four attacks is which.

Positional, like the boss weapons in `ai.py` and for the same reason: the sim
selects an attack by index (`Intent.weapon`), so the meaning of each index is a
contract between the content files, the input layer and the HUD. Named here
rather than repeated as bare integers in three places, and enforced by a test --
a class that lists its attacks in another order loads perfectly and then binds
the ultimate to the light-attack button.

The order is ascending commitment, which is also the order the HUD draws:

* **light** -- the attack the class has always had. Index 0, no cooldown, and
  the only one the reference bot ever presses. That is what keeps every recorded
  balance number measuring the same thing it measured before skills existed.
* **neutral** -- answers the situation the light attack is worst in. Cheap,
  frequent, buys position rather than killing things.
* **heavy** -- roughly double the light attack in damage and in commitment.
* **ultimate** -- the largest numbers the class has, once or twice a stage.

Pure constants: no pygame, no imports, so `render/` and `scenes/` can both read
them without either depending on the other.
"""

from __future__ import annotations

LIGHT = 0
NEUTRAL = 1
HEAVY = 2
ULTIMATE = 3

#: Every slot, in declaration order. Iterate this rather than `range(4)` so the
#: HUD and the tests cannot disagree with the content about how many there are.
SLOTS = (LIGHT, NEUTRAL, HEAVY, ULTIMATE)

#: What each slot is called, for the HUD and for assertion messages.
SLOT_NAMES = {
    LIGHT: "light",
    NEUTRAL: "neutral",
    HEAVY: "heavy",
    ULTIMATE: "ultimate",
}

#: The slots that sit on a cooldown and therefore need a pip drawn for them.
#: Light is excluded because it has none -- a pip that is always full is noise.
COOLDOWN_SLOTS = (NEUTRAL, HEAVY, ULTIMATE)
