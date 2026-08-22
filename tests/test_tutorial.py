"""The tutorial, and the guarantee that it is only a tutorial.

The headline test is `test_a_fight_resolves_identically_with_the_tutorial_running`,
and it is `test_effects.py`'s headline test a third time -- the feel pass, the
audio pass and now this one are three readers of a single drained list, and none
of them may be the reason a fight comes out differently.

It matters more here than for either of the others, because this layer is the
first one that reads the `Intent` as well as the events. Reading what the player
asked for is safe; the moment it *changes* what the player asked for, the
tutorial is an input layer and the recorded grid is measuring something else.
"""

from __future__ import annotations

from hack_and_slash.bindings import Action
from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.game import intent as intents
from hack_and_slash.game import skills
from hack_and_slash.game.events import Event, EventKind
from hack_and_slash.game.sim import step
from hack_and_slash.render.tutorial import ARENA, LESSONS, ROOM, Lesson, Tutorial

from .helpers import add_enemy, make_world

RIGHT = Vec2(1, 0)
NOTHING: list[Event] = []


def fight(seed: int, tutorial: Tutorial | None):
    """The same scripted fight `test_effects.py` and `test_audio.py` both run.

    Deliberately identical, down to the seed and the two enemies, so all three
    guarantees are being made about one situation rather than about three.
    """
    world = make_world(seed=seed)
    add_enemy(world, "grunt", world.hero.pos + Vec2(30, 0))
    add_enemy(world, "bowman", world.hero.pos + Vec2(-90, 40))

    press = intents.Intent(move=RIGHT, aim=RIGHT, attack=True)
    for tick in range(300):
        command = press if tick % 40 < 30 else intents.dodge_toward(RIGHT)
        step(world, command)
        if tutorial is not None:
            tutorial.feed(world.drain_events(), command)

    return [(e.id, e.pos, e.hp, e.state) for e in world.entities], world.outcome


def hero_event(kind: EventKind) -> list[Event]:
    return [Event(kind, Vec2(0, 0), 1, is_hero=True)]


def advance_to(lesson_id: str) -> Tutorial:
    """A tutorial with everything before `lesson_id` behind it."""
    index = [lesson.id for lesson in LESSONS].index(lesson_id)
    return Tutorial(index=index)


# --- the guarantee -----------------------------------------------------------
def test_a_fight_resolves_identically_with_the_tutorial_running() -> None:
    """Teaching must not be able to change a fight.

    If this fails, the tutorial is writing somewhere it may only read -- most
    likely into the `Intent` it is handed, which would make a prompt on screen
    the difference between a run that lives and one that dies.
    """
    plain = fight(seed=31337, tutorial=None)
    taught = fight(seed=31337, tutorial=Tutorial())
    assert plain == taught


def test_a_finished_tutorial_changes_nothing_either() -> None:
    """The other half of the same claim, and the state every returning player
    is in: `done` must be a branch that draws nothing, not a branch that skips
    a drain and leaves a tick's events queued into the next one."""
    plain = fight(seed=31337, tutorial=None)
    seen = fight(seed=31337, tutorial=Tutorial(done=True))
    assert plain == seen


# --- what is on screen -------------------------------------------------------
def test_a_fresh_tutorial_starts_at_the_first_lesson() -> None:
    assert Tutorial().current is LESSONS[0]


def test_a_player_who_has_seen_it_is_shown_nothing() -> None:
    """The whole feature for everybody but a first-timer: one bool, one branch."""
    assert Tutorial(done=True).current is None


def test_dismissing_ends_the_whole_thing_not_just_this_lesson() -> None:
    tutorial = Tutorial()
    tutorial.dismiss()
    assert tutorial.done
    assert tutorial.current is None


def test_only_one_lesson_is_ever_on_screen() -> None:
    """A beginner offered two things to read has been told neither."""
    tutorial = Tutorial()
    for _ in range(len(LESSONS)):
        assert tutorial.current is None or isinstance(tutorial.current, Lesson)
        tutorial.index += 1


def test_the_lessons_are_reached_in_order() -> None:
    tutorial = Tutorial()
    for expected in LESSONS:
        tutorial.place = expected.context
        assert tutorial.current is expected
        tutorial.index += 1


# --- what clears a lesson ----------------------------------------------------
def test_walking_clears_the_movement_lesson() -> None:
    tutorial = Tutorial()
    tutorial.feed(NOTHING, intents.walk(RIGHT))
    assert tutorial.current is not None
    assert tutorial.current.id == "attack", "movement did not clear the first lesson"


def test_standing_still_does_not_clear_it() -> None:
    tutorial = Tutorial()
    tutorial.feed(NOTHING, intents.NOTHING)
    assert tutorial.current is LESSONS[0]


def test_swinging_clears_the_attack_lesson() -> None:
    tutorial = advance_to("attack")
    tutorial.feed(hero_event(EventKind.SWING), intents.NOTHING)
    assert tutorial.current is not None and tutorial.current.id == "dodge"


def test_shooting_clears_it_too() -> None:
    """The Archer's light attack is a shot, and its player has still attacked."""
    tutorial = advance_to("attack")
    tutorial.feed(hero_event(EventKind.SHOOT), intents.NOTHING)
    assert tutorial.current is not None and tutorial.current.id == "dodge"


def test_an_enemy_swinging_does_not_clear_the_attack_lesson() -> None:
    """The failure this guards: in a crowded arena the lesson would clear itself
    before the player had pressed anything at all."""
    tutorial = advance_to("attack")
    tutorial.feed([Event(EventKind.SWING, Vec2(0, 0), 9, is_hero=False)], intents.NOTHING)
    assert tutorial.current is LESSONS[1]


def test_rolling_clears_the_dodge_lesson() -> None:
    tutorial = advance_to("dodge")
    tutorial.feed(hero_event(EventKind.DODGE), intents.NOTHING)
    assert tutorial.current is not None and tutorial.current.id == "skills"


def test_a_skill_press_clears_the_skills_lesson() -> None:
    tutorial = advance_to("skills")
    tutorial.feed(NOTHING, intents.Intent(attack=True, weapon=skills.HEAVY))
    assert tutorial.current is not None and tutorial.current.id == "sheet"


def test_the_light_attack_does_not_clear_the_skills_lesson() -> None:
    """It is the lesson before it, and holding the mouse down is the normal
    state of playing this game -- so the light attack would clear this one
    instantly and teach nothing."""
    tutorial = advance_to("skills")
    tutorial.feed(NOTHING, intents.Intent(attack=True, weapon=skills.LIGHT))
    assert tutorial.current is LESSONS[3]


def test_opening_the_sheet_clears_the_sheet_lesson() -> None:
    tutorial = advance_to("sheet")
    tutorial.feed(NOTHING, intents.NOTHING, inspecting=True)
    assert tutorial.current is None, "the last arena lesson left something behind it"


def test_using_a_prop_clears_the_room_lesson_and_finishes() -> None:
    tutorial = advance_to("room")
    tutorial.feed(hero_event(EventKind.PROP), intents.NOTHING, in_room=True)
    assert tutorial.done, "clearing the last lesson did not finish the tutorial"
    assert tutorial.current is None


# --- where a lesson belongs --------------------------------------------------
def test_the_room_lesson_stays_hidden_in_an_arena() -> None:
    tutorial = advance_to("room")
    tutorial.feed(NOTHING, intents.NOTHING, in_room=False)
    assert tutorial.current is None


def test_an_arena_lesson_stays_hidden_in_a_room() -> None:
    """A prompt about the roll, in a room with nothing to roll away from, is the
    game asking for something the room cannot give."""
    tutorial = advance_to("dodge")
    tutorial.feed(NOTHING, intents.NOTHING, in_room=True)
    assert tutorial.current is None


def test_a_lesson_out_of_its_place_cannot_be_cleared() -> None:
    tutorial = advance_to("room")
    tutorial.feed(hero_event(EventKind.PROP), intents.NOTHING, in_room=False)
    assert not tutorial.done
    tutorial.feed(hero_event(EventKind.PROP), intents.NOTHING, in_room=True)
    assert tutorial.done


def test_the_place_follows_the_room_the_scene_names() -> None:
    tutorial = Tutorial()
    tutorial.feed(NOTHING, intents.NOTHING, in_room=True)
    assert tutorial.place == ROOM
    tutorial.feed(NOTHING, intents.NOTHING, in_room=False)
    assert tutorial.place == ARENA


# --- the table ---------------------------------------------------------------
def test_every_lesson_renders_with_the_keys_it_names() -> None:
    """The failure this guards is a mistyped placeholder, which is a `KeyError`
    thrown from `draw` -- a crash, in the frame a beginner is being taught."""
    for lesson in LESSONS:
        line = lesson.render(lambda action: action.value.upper())
        assert "{" not in line, f"{lesson.id} left a placeholder unfilled"
        assert line.strip(), f"{lesson.id} renders as nothing"


def test_a_rebound_key_changes_what_the_prompt_says() -> None:
    """The single source that stops a prompt saying J after the attack moved."""
    lesson = next(item for item in LESSONS if item.id == "attack")
    assert "J" in lesson.render(lambda action: "J")
    assert "M" in lesson.render(lambda action: "M")


def test_the_lesson_ids_are_unique() -> None:
    ids = [lesson.id for lesson in LESSONS]
    assert len(ids) == len(set(ids))


def test_every_lesson_belongs_somewhere_real() -> None:
    for lesson in LESSONS:
        assert lesson.context in (ARENA, ROOM), lesson.id


def test_every_action_a_lesson_names_is_a_real_one() -> None:
    """A lesson naming an action `bindings.py` does not have is a prompt that
    cannot be rendered and a key that cannot be rebound."""
    for lesson in LESSONS:
        for action in lesson.actions:
            assert action in tuple(Action), f"{lesson.id} names {action}"
