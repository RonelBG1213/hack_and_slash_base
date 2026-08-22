"""The first thing that reads the profile, and the rule that lets it.

`game/profile.py`'s docstring is the thing this file is written against: *"the
day an unlock rule reads one of these numbers and hands a run a head start, that
is the day the recorded class-by-stage grid moves"*. The answer is not to keep
the counters unread -- it is to make the grant **access** rather than numbers,
and to make that structural rather than a promise.

So the expensive half of this file is not the table. It is the two claims
underneath it: that an unlock cannot express a stat, and that an empty table is
the game that shipped before unlocks existed.
"""

from __future__ import annotations

import json

import pytest

from hack_and_slash.game import difficulty, unlocks
from hack_and_slash.game.profile import Profile
from hack_and_slash.game.unlocks import Grant, Requirement, Table, Unlock

SEED_PROFILE = Profile(runs_started=12, runs_won=0, deepest_stage=23, best_gold=900)


def table_from(payload: dict, tmp_path) -> Table:
    path = tmp_path / "unlocks.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return Table.load(path)


def an_entry(**overrides) -> dict:
    entry = {
        "id": "hard_tier",
        "name": "Hard",
        "kind": "difficulty",
        "target": "relentless",
        "requires": {"deepest_stage": 10},
    }
    entry.update(overrides)
    return entry


def a_payload(*entries) -> dict:
    return {"unlocks": list(entries) or [an_entry()]}


# --- access only, and it is structural ---------------------------------------
def test_the_loader_refuses_an_unlock_that_grants_an_attribute(tmp_path) -> None:
    """The whole rule, and the key somebody will reach for first."""
    payload = a_payload(an_entry(attributes={"damage": 5}))
    with pytest.raises(ValueError, match="access and never numbers"):
        table_from(payload, tmp_path)


def test_no_kind_of_grant_is_a_number() -> None:
    """Two members, both access. A third is a design decision, not a line."""
    assert {kind.value for kind in Grant} == {"difficulty", "modifier"}


def test_nothing_here_imports_the_attribute_layer() -> None:
    """The structural half of "access only": a stat grant is unrepresentable
    because there is nothing in scope that could express one."""
    source = (unlocks.__file__ or "").replace("\\", "/")
    text = open(source, encoding="utf-8").read()
    assert "import attributes" not in text
    assert "from .attributes" not in text


# --- an empty table is today's game ------------------------------------------
def test_an_empty_table_locks_nothing(tmp_path) -> None:
    """The rollback. Every tier the game ships is open on a fresh profile."""
    empty = table_from({"unlocks": []}, tmp_path)
    for tier in difficulty.table().tiers:
        assert unlocks.is_open(Grant.DIFFICULTY, tier.id, Profile(), empty)


def test_a_tier_no_entry_names_is_open(tmp_path) -> None:
    table = table_from(a_payload(), tmp_path)
    assert unlocks.is_open(Grant.DIFFICULTY, "normal", Profile(), table)
    assert not unlocks.is_open(Grant.DIFFICULTY, "relentless", Profile(), table)


def test_an_empty_table_has_earned_nothing_to_report(tmp_path) -> None:
    empty = table_from({"unlocks": []}, tmp_path)
    rich = Profile(runs_started=99, runs_won=9, deepest_stage=50, best_gold=99999)
    assert unlocks.earned(rich, empty) == frozenset()


# --- what a profile has earned -----------------------------------------------
def test_a_fresh_profile_has_earned_nothing(tmp_path) -> None:
    table = table_from(a_payload(), tmp_path)
    assert unlocks.earned(Profile(), table) == frozenset()


def test_a_counter_at_the_threshold_earns_it(tmp_path) -> None:
    """`>=`, not `>`. Reaching stage 10 is reaching stage 10."""
    table = table_from(a_payload(), tmp_path)
    assert unlocks.earned(Profile(deepest_stage=9), table) == frozenset()
    assert unlocks.earned(Profile(deepest_stage=10), table) == {"hard_tier"}


def test_every_counter_of_a_requirement_has_to_be_met(tmp_path) -> None:
    entry = an_entry(requires={"deepest_stage": 10, "runs_won": 1})
    table = table_from(a_payload(entry), tmp_path)
    assert unlocks.earned(Profile(deepest_stage=40), table) == frozenset()
    assert unlocks.earned(Profile(deepest_stage=40, runs_won=1), table) == {"hard_tier"}


def test_the_run_that_crosses_the_line_is_the_one_that_reports_it(tmp_path) -> None:
    table = table_from(a_payload(), tmp_path)
    before, after = Profile(deepest_stage=9), Profile(deepest_stage=11)

    crossed = unlocks.newly_earned(before, after, table)
    assert [entry.id for entry in crossed] == ["hard_tier"]

    # And the run after it reports nothing, because nothing crossed.
    assert unlocks.newly_earned(after, Profile(deepest_stage=20), table) == ()


def test_an_unlock_cannot_be_taken_away_by_a_worse_run(tmp_path) -> None:
    """Not a property of this code so much as of the counters it reads --
    `record_stage` takes a `max`, so the number it compares against never falls.
    Pinned here because the screen says "unlocked" and has to mean it."""
    table = table_from(a_payload(), tmp_path)
    reached = Profile(deepest_stage=30)
    assert unlocks.earned(reached, table) == {"hard_tier"}
    assert unlocks.newly_earned(reached, reached, table) == ()


# --- the loader --------------------------------------------------------------
def test_every_requirement_names_a_counter_the_profile_keeps(tmp_path) -> None:
    payload = a_payload(an_entry(requires={"stages_cleared": 3}))
    with pytest.raises(ValueError, match="which the profile does not keep"):
        table_from(payload, tmp_path)


def test_the_counters_are_derived_from_the_profile_rather_than_listed() -> None:
    """So a fifth counter is usable by the data file the day it is declared."""
    assert unlocks.COUNTERS == ("runs_started", "runs_won", "deepest_stage", "best_gold")
    assert set(unlocks.COUNTERS) == set(vars(Profile()).keys())


def test_the_loader_refuses_an_unlock_that_asks_for_nothing(tmp_path) -> None:
    with pytest.raises(ValueError, match="asks for nothing"):
        table_from(a_payload(an_entry(requires={})), tmp_path)


def test_the_loader_refuses_a_requirement_of_zero(tmp_path) -> None:
    """The same fault wearing a number. A threshold of zero is met by a profile
    that has never played, which is the row that teaches a player the screen is
    decoration."""
    with pytest.raises(ValueError, match="asks for nothing"):
        table_from(a_payload(an_entry(requires={"deepest_stage": 0})), tmp_path)


def test_the_loader_refuses_two_unlocks_sharing_an_id(tmp_path) -> None:
    with pytest.raises(ValueError, match="share the id"):
        table_from(a_payload(an_entry(), an_entry()), tmp_path)


def test_the_loader_refuses_a_tier_that_does_not_exist(tmp_path) -> None:
    payload = a_payload(an_entry(target="merciless"))
    with pytest.raises(ValueError, match="data/difficulty.json does not declare"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_a_modifier_nothing_implements(tmp_path) -> None:
    payload = a_payload(an_entry(kind="modifier", target="double_gold"))
    with pytest.raises(ValueError, match="which nothing implements"):
        table_from(payload, tmp_path)


def test_the_loader_refuses_a_kind_that_is_neither(tmp_path) -> None:
    with pytest.raises(ValueError, match="not one of"):
        table_from(a_payload(an_entry(kind="stat")), tmp_path)


# --- the shipped table -------------------------------------------------------
def test_the_shipped_table_offers_every_modifier_the_code_implements() -> None:
    """A content test rather than a loader guard, deliberately: as a guard it
    would make `"unlocks": []` illegal, and that empty list is the rollback."""
    offered = {entry.target for entry in unlocks.table().for_kind(Grant.MODIFIER)}
    assert offered == set(unlocks.MODIFIERS)


def test_the_default_tier_is_never_behind_an_unlock() -> None:
    """The load-bearing one. `select.index_of_default` opens the cursor on this
    tier, so a lock in front of it would strand the screen on a row it is not
    allowed to pick -- and it would mean a fresh player's first run is on
    something other than the tier every recorded number was measured against."""
    tiers = difficulty.table()
    assert unlocks.is_open(Grant.DIFFICULTY, tiers.default_id, Profile())


def test_the_gentlest_tier_is_never_behind_an_unlock() -> None:
    """The other end of the same argument: a locked Easy would mean the player
    who most needs it is the one who cannot reach it."""
    tiers = difficulty.table()
    assert unlocks.is_open(Grant.DIFFICULTY, tiers.gentlest.id, Profile())


def test_every_shipped_unlock_can_say_what_it_wants() -> None:
    """A row with no readable requirement is a padlock with no rule behind it,
    which is what the Unlockables screen refused to be when it was a stub."""
    for entry in unlocks.table().entries:
        assert entry.name
        assert entry.requires.describe()


def test_a_requirement_of_one_reads_as_one() -> None:
    assert Requirement((("runs_won", 1),)).describe() == "win a run"
    assert Requirement((("runs_won", 3),)).describe() == "win 3 runs"


def test_a_requirement_on_a_counter_with_no_phrase_still_reads() -> None:
    """A counter added to `Profile` must not be able to crash a menu."""
    assert "7" in Requirement((("best_gold", 7),)).describe()


# --- the table's own shape ---------------------------------------------------
def test_an_unknown_id_raises_rather_than_returning_nothing(tmp_path) -> None:
    table = table_from(a_payload(), tmp_path)
    with pytest.raises(KeyError):
        table["no_such_unlock"]


def test_gating_answers_none_for_a_thing_nothing_gates(tmp_path) -> None:
    table = table_from(a_payload(), tmp_path)
    assert table.gating(Grant.DIFFICULTY, "normal") is None
    assert table.gating(Grant.MODIFIER, "champions") is None
    assert table.gating(Grant.DIFFICULTY, "relentless") is not None


def test_an_unlock_knows_whether_a_profile_earned_it() -> None:
    entry = Unlock(
        id="x",
        name="X",
        kind=Grant.MODIFIER,
        target="champions",
        requires=Requirement((("runs_won", 1),)),
    )
    assert not entry.earned_by(Profile())
    assert entry.earned_by(Profile(runs_won=1))
