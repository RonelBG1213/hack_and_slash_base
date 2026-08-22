"""The six things the game never says out loud, said once.

A third reader of the list `scenes/play.py` drains every tick, beside
`render/effects.py` and `audio/cues.py`. The rule those two are built on is the
rule this is built on -- `game/events.py`: **nothing in the sim may ever read an
event back** -- so a prompt on screen cannot reach a fight, and
`tests/test_tutorial.py` runs the same seeded fight with this running and not
running and demands the two worlds come out identical.

That guarantee is the whole reason the tutorial is here and not in a stage of its
own. A scripted tutorial level is content, and content is the one thing this
project cannot add cheaply: the recorded grid in `docs/balance.md` is 280 cells
measured against fixed stage literals, and a fifty-first stage is a fifty-first
chance for one of them to move. This teaches in the real first stage, over a live
fight, and nothing in `levels/` learns it exists.

**Two kinds of satisfier, and the split is deliberate.** A lesson about the
player's hands is cleared by the `Intent` -- what they asked for -- and a lesson
about the world is cleared by an `Event` -- what actually happened. Both are
things `PlayScene` is already holding at the moment it calls `feed`, and neither
is something this module can write to.

Strictly ordered, one at a time. A screen that offers a beginner two things to
read has told them neither, and the order is the order a run meets them: the
five that happen in an arena, then the one that happens in the room after it.

No pygame, so the guarantee above is checkable headlessly. That costs exactly one
thing and it is worth naming: a key *label* needs `scenes/keymap.py`, which is
not pure, so the table below stores `bindings.Action` members and the scene
interpolates them at the moment it draws. A prompt therefore names whatever key
the player has actually bound -- the same property, and the same single source,
that stops a HUD pip saying Q after the buff moved to C.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..bindings import Action
from ..game import skills
from ..game.events import Event, EventKind
from ..game.intent import Intent

#: Where a lesson makes sense. A prompt about doors in an arena is noise, and a
#: prompt about the roll in a room with nothing to roll away from is worse --
#: it is the game asking for something the room cannot give.
ARENA = "arena"
ROOM = "room"

#: The slots the skills lesson is about: everything but the light attack, which
#: is the lesson before it.
SKILL_SLOTS = (skills.NEUTRAL, skills.HEAVY, skills.ULTIMATE)


@dataclass(frozen=True)
class Lesson:
    """One line, and where it belongs.

    `text` is a format string keyed by `Action` *values* -- `{dodge}`, not
    `{0}` -- so the table reads as the sentence it draws, and a lesson that
    names the wrong action fails to render rather than drawing the wrong key.
    """

    id: str
    text: str
    actions: tuple[Action, ...] = ()
    context: str = ARENA

    def render(self, label: Callable[[Action], str]) -> str:
        """The line to draw, with the player's own keys in it.

        Takes the lookup rather than a prepared dict, which is what makes a
        missing label impossible instead of merely unlikely -- there is no
        second list of actions to fall out of step with `self.actions`.
        """
        return self.text.format(**{action.value: label(action) for action in self.actions})


#: The lessons, in the order a run meets them. Branched on by id in `_satisfied`
#: below, so rewording one is a change to one string and never to the wiring --
#: the `scenes/options.py` contract, applied to a table that is mostly prose.
#:
#: Six, and the count is an argument rather than an accident. The four attack
#: slots, the roll, the sheet and the reward room are the whole of what
#: `docs/roadmap.md` says is "introduced by a controls table"; the fork is
#: deliberately not here, because the promotion panel already explains itself and
#: stands twenty stages past the point anybody still needs this.
LESSONS: tuple[Lesson, ...] = (
    Lesson(
        "move",
        "{move_up}{move_left}{move_down}{move_right} to move",
        (Action.MOVE_UP, Action.MOVE_LEFT, Action.MOVE_DOWN, Action.MOVE_RIGHT),
    ),
    Lesson("attack", "{attack} or the mouse to attack", (Action.ATTACK,)),
    # The one lesson that teaches a rule rather than a key. The roll's i-frames
    # are the whole defensive layer of this game and nothing on screen says so.
    Lesson("dodge", "{dodge} to roll - nothing can hit you mid-roll", (Action.DODGE,)),
    Lesson(
        "skills",
        "{neutral} {heavy} {ultimate} are your three skills",
        (Action.NEUTRAL, Action.HEAVY, Action.ULTIMATE),
    ),
    Lesson("sheet", "{sheet} shows what this run has made of you", (Action.SHEET,)),
    Lesson("room", "use what stands here, then pick a door", (), ROOM),
)


@dataclass
class Tutorial:
    """Which lesson is live, and whether there is any point drawing one.

    Constructed `done` for a player who has seen it -- `settings.tutorial_seen`
    -- which makes the whole feature one bool and one branch for everybody who
    is not playing for the first time.
    """

    done: bool = False

    #: How many lessons are behind us. Strictly ordered, so an index says
    #: everything a set of cleared ids would and cannot disagree with itself.
    index: int = 0

    #: Where the hero was standing the last time `feed` ran. Held rather than
    #: passed to `current` as well, so the scene names the place once per tick
    #: and the drawing half cannot disagree with the clearing half about it.
    place: str = field(default=ARENA, repr=False)

    @property
    def current(self) -> Lesson | None:
        """The lesson to draw, or `None` for a screen that stays quiet.

        Quiet is the common answer and deliberately so: it is what a finished
        tutorial returns, and what a pending arena lesson returns while the
        player is standing in a reward room.
        """
        if self.done or self.index >= len(LESSONS):
            return None
        lesson = LESSONS[self.index]
        return lesson if lesson.context == self.place else None

    def feed(
        self,
        events: list[Event],
        intent: Intent,
        in_room: bool = False,
        inspecting: bool = False,
    ) -> None:
        """Take one tick. Called every tick, before drawing.

        Mirrors `Effects.feed(events, hitstop)`: the events, plus the things a
        player did that the events do not carry. Movement emits nothing at all,
        and no payload names which of the four slots swung -- so both come off
        the `Intent`, which is the record of what was asked for.
        """
        self.place = ROOM if in_room else ARENA

        lesson = self.current
        if lesson is None:
            return

        if self._satisfied(lesson, events, intent, inspecting):
            self.index += 1
            if self.index >= len(LESSONS):
                # The last one cleared is the tutorial over. The scene watches
                # this to write the preference, so a player who finishes it is
                # never taught anything twice.
                self.done = True

    def dismiss(self) -> None:
        """Enough. The whole thing, for good -- see the note in `scenes/play.py`
        about which key does this and why it is not a rebindable one."""
        self.done = True

    def _satisfied(
        self,
        lesson: Lesson,
        events: list[Event],
        intent: Intent,
        inspecting: bool,
    ) -> bool:
        match lesson.id:
            case "move":
                return intent.wants_to_move
            case "attack":
                # A swing and a shot are one lesson: which of the two a class
                # does with its light attack is the class's business, and the
                # Archer's player has still just attacked.
                return self._did(events, EventKind.SWING, EventKind.SHOOT)
            case "dodge":
                return self._did(events, EventKind.DODGE)
            case "skills":
                # The press, not the event -- and this is the one place that
                # distinction is a decision rather than a shortcut. No payload
                # names a slot, and the lesson is "this key is your heavy
                # attack", which is true of a press the cooldown refused.
                return intent.attack and intent.weapon in SKILL_SLOTS
            case "sheet":
                return inspecting
            case "room":
                # PROP is one kind for a fixture and for a door alike, which is
                # exactly the granularity this lesson wants: it says "the room
                # is a thing you use", and either half of that answers it.
                return self._did(events, EventKind.PROP)
        return False

    @staticmethod
    def _did(events: list[Event], *kinds: EventKind) -> bool:
        """Whether the hero did one of these this tick.

        `is_hero` throughout: a grunt swinging is not the player learning to
        swing, and in a crowded arena it would clear the lesson before they had
        pressed anything.
        """
        return any(event.is_hero and event.kind in kinds for event in events)
