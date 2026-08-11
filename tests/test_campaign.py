"""The campaign model and its manifest.

Validation matters more here than anywhere else in the loading code: a fault in
stage 4 that only surfaces when a player finally reaches it has cost them the
three stages they already played.
"""

from __future__ import annotations

import json

import pytest

from hack_and_slash.core import campaign_io, level_io
from hack_and_slash.core.campaign import Campaign
from hack_and_slash.core.campaign_io import CampaignFormatError
from hack_and_slash.core.level import EnemySpawn, Level

ROOM = (
    "#####",
    "#...#",
    "#.#.#",
    "#...#",
    "#####",
)


def stage(name: str, hero=(1, 1), enemies=(("grunt", (3, 3)),)) -> Level:
    return Level(
        name=name,
        rows=ROOM,
        hero_spawn=hero,
        enemy_spawns=tuple(EnemySpawn(t, pos) for t, pos in enemies),
        tile=16,
    )


def campaign_of(*names: str) -> Campaign:
    return Campaign(name="test run", stages=tuple(stage(n) for n in names))


def write_campaign(tmp_path, campaign: Campaign) -> "object":
    files = [f"stage{i + 1}.json" for i in range(len(campaign))]
    for level, filename in zip(campaign.stages, files):
        level_io.save(level, tmp_path / filename)
    path = tmp_path / "campaign.json"
    campaign_io.save(campaign, path, files)
    return path


# --- the model ---------------------------------------------------------------
def test_stages_are_ordered_and_countable() -> None:
    run = campaign_of("first", "second", "third")
    assert len(run) == 3
    assert run[0].name == "first"
    assert run[2].name == "third"


def test_the_last_stage_knows_it_is_last() -> None:
    # This is what decides whether clearing a stage advances or wins the run.
    run = campaign_of("a", "b")
    assert not run.is_final(0)
    assert run.is_final(1)


def test_stage_numbers_are_one_based_for_players() -> None:
    run = campaign_of("a", "b")
    assert run.stage_number(0) == 1
    assert run.stage_number(1) == 2


# --- validation --------------------------------------------------------------
def test_a_good_campaign_reports_no_problems() -> None:
    assert campaign_of("a", "b").problems() == []
    assert campaign_of("a", "b").is_playable


def test_a_faulty_stage_is_reported_with_its_stage_number() -> None:
    """"The hero spawns inside a wall" is far more useful with a stage on it."""
    broken = Campaign(
        name="test run",
        stages=(stage("fine"), stage("bad", hero=(2, 2))),  # (2,2) is the pillar
    )
    problems = broken.problems()
    assert any("stage 2" in p and "inside a wall" in p for p in problems)
    assert not any("stage 1" in p for p in problems)
    assert not broken.is_playable


def test_every_faulty_stage_is_reported_not_just_the_first() -> None:
    # Reported rather than raised so one pass over the campaign lists them all.
    broken = Campaign(
        name="test run",
        stages=(stage("a", hero=(2, 2)), stage("b", enemies=(("grunt", (2, 2)),))),
    )
    problems = broken.problems()
    assert any("stage 1" in p for p in problems)
    assert any("stage 2" in p for p in problems)


def test_a_campaign_with_no_stages_is_not_playable() -> None:
    assert Campaign(name="empty", stages=()).problems() == ["the campaign has no stages"]


# --- the manifest ------------------------------------------------------------
def test_a_campaign_round_trips_through_disk(tmp_path) -> None:
    original = campaign_of("first", "second", "third")
    loaded = campaign_io.load(write_campaign(tmp_path, original))

    assert loaded.name == original.name
    assert [s.name for s in loaded.stages] == ["first", "second", "third"]
    assert loaded.stages == original.stages


def test_stage_order_is_the_manifest_order_not_the_filename_order(tmp_path) -> None:
    """The order is a design decision, which is why it is written down rather
    than inferred from how the files happen to be named."""
    level_io.save(stage("last"), tmp_path / "a.json")
    level_io.save(stage("first"), tmp_path / "z.json")
    (tmp_path / "campaign.json").write_text(
        json.dumps({"schema_version": 1, "name": "run", "stages": ["z.json", "a.json"]}),
        encoding="utf-8",
    )
    loaded = campaign_io.load(tmp_path / "campaign.json")
    assert [s.name for s in loaded.stages] == ["first", "last"]


def test_saved_manifests_carry_a_schema_version(tmp_path) -> None:
    path = write_campaign(tmp_path, campaign_of("a"))
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == (
        campaign_io.SCHEMA_VERSION
    )


def test_a_missing_stage_file_names_both_the_stage_and_the_file(tmp_path) -> None:
    (tmp_path / "campaign.json").write_text(
        json.dumps({"stages": ["stage1.json", "gone.json"]}), encoding="utf-8"
    )
    level_io.save(stage("a"), tmp_path / "stage1.json")

    with pytest.raises(CampaignFormatError, match="stage 2") as caught:
        campaign_io.load(tmp_path / "campaign.json")
    assert "gone.json" in str(caught.value)


def test_a_broken_stage_file_is_reported_against_its_stage(tmp_path) -> None:
    (tmp_path / "campaign.json").write_text(
        json.dumps({"stages": ["stage1.json"]}), encoding="utf-8"
    )
    (tmp_path / "stage1.json").write_text("{ not json", encoding="utf-8")

    with pytest.raises(CampaignFormatError, match="stage 1"):
        campaign_io.load(tmp_path / "campaign.json")


def test_a_missing_manifest_says_which_command_builds_it(tmp_path) -> None:
    with pytest.raises(CampaignFormatError, match="make_level"):
        campaign_io.load(tmp_path / "nothing.json")


def test_a_manifest_from_a_newer_build_is_refused(tmp_path) -> None:
    (tmp_path / "campaign.json").write_text(
        json.dumps({"schema_version": 99, "stages": ["a.json"]}), encoding="utf-8"
    )
    with pytest.raises(CampaignFormatError, match="newer build"):
        campaign_io.load(tmp_path / "campaign.json")


def test_a_manifest_with_no_stages_is_refused(tmp_path) -> None:
    (tmp_path / "campaign.json").write_text(json.dumps({"stages": []}), encoding="utf-8")
    with pytest.raises(CampaignFormatError, match="non-empty"):
        campaign_io.load(tmp_path / "campaign.json")
