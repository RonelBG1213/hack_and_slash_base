"""Preferences and the scoreboard -- the two files that are not content.

Both in one place because they are the same kind of thing and are tested for the
same property: **neither may ever stop the game starting.** `data/*.json` refuses
loudly on a malformed field, because a typo in a damage number is a bug somebody
has to see. These two do the opposite and come back as defaults, because a
half-written preferences file is not a bug in the game and the player's answer to
it should be "my scale reset", not "it will not open".

That asymmetry is deliberate and it is the thing most likely to be undone by
somebody tidying up, so it is asserted rather than commented.
"""

from __future__ import annotations

import json

from hack_and_slash import settings as settings_module
from hack_and_slash.game import profile
from hack_and_slash.audio.cues import DEFAULT_VOLUME, MAX_VOLUME
from hack_and_slash.settings import AUTO_SCALE, Settings


# --- settings ----------------------------------------------------------------
def test_a_fresh_install_is_the_game_as_it_shipped() -> None:
    """Every default is today's behaviour.

    The whole argument that this layer cannot have moved anything: a player who
    never opens the options screen is playing the game that was measured.
    """
    fresh = Settings()
    assert fresh.scale == AUTO_SCALE
    assert fresh.fullscreen is False
    assert fresh.screenshake is True
    assert fresh.damage_numbers is True
    assert fresh.seed == 0
    # Empty rather than filled in with `bindings.DEFAULTS`, and the difference
    # is the whole point: this player follows the shipped key if it ever moves.
    assert fresh.bindings == {}


def test_settings_survive_a_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    settings_module.save(
        Settings(scale=5, fullscreen=True, screenshake=False, seed=1234), path
    )

    read = settings_module.load(path)
    assert read.scale == 5
    assert read.fullscreen is True
    assert read.screenshake is False
    assert read.damage_numbers is True
    assert read.seed == 1234


def test_bindings_survive_a_round_trip(tmp_path) -> None:
    """Key *names*, so the file is one a person can read and fix.

    `bindings.py` and this module are both pygame-free -- the window size is
    read before there is a window to ask -- so neither could name a `K_*` even
    if a raw keycode were the better thing to store, which it is not.
    """
    path = tmp_path / "settings.json"
    settings_module.save(Settings(bindings={"dodge": ["c"], "heavy": ["v"]}), path)

    assert settings_module.load(path).bindings == {"dodge": ["c"], "heavy": ["v"]}
    assert '"c"' in path.read_text(encoding="utf-8"), "stored as a keycode"


def test_a_mangled_bindings_block_costs_the_bindings_and_nothing_else(
    tmp_path,
) -> None:
    """The asymmetry this file exists to assert, applied to the newest field.

    Four ways the block can be wrong -- not a mapping, an action from a later
    build, a value that is not a list, a key that is not a string -- and none of
    them may stop the game starting or take the other five preferences with it.
    """
    path = tmp_path / "settings.json"

    path.write_text(json.dumps({"scale": 5, "bindings": "sideways"}), encoding="utf-8")
    read = settings_module.load(path)
    assert read.bindings == {}
    assert read.scale == 5, "a bad bindings block took an unrelated setting with it"

    path.write_text(
        json.dumps(
            {"bindings": {"grapple": ["g"], "dodge": ["c"], "heavy": 7, "sheet": [1]}}
        ),
        encoding="utf-8",
    )
    assert settings_module.load(path).bindings == {"dodge": ["c"]}


def test_a_missing_file_is_not_an_error(tmp_path) -> None:
    assert settings_module.load(tmp_path / "nothing.json") == Settings()


def test_a_corrupt_file_falls_back_rather_than_raising(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ half a fi", encoding="utf-8")
    assert settings_module.load(path) == Settings()


def test_a_field_of_the_wrong_type_is_dropped_and_the_rest_kept(tmp_path) -> None:
    """The specific failure this guards: `scale` reaching `window_size` as a
    string or a bool, where it is multiplied by 384. A hand-edited file is the
    normal way that happens, and the row beside it should still load."""
    path = tmp_path / "settings.json"
    path.write_text('{"scale": "3", "seed": 99, "fullscreen": 1}', encoding="utf-8")

    read = settings_module.load(path)
    assert read.scale == AUTO_SCALE, "a string scale was accepted"
    assert read.fullscreen is False, "an integer was accepted as a boolean"
    assert read.seed == 99, "a good field was thrown away with a bad one"


def test_a_file_from_another_build_loads_what_it_recognises(tmp_path) -> None:
    # Forward and backward: a key this build has never heard of is ignored, and
    # a key it expects and does not find keeps its default.
    path = tmp_path / "settings.json"
    path.write_text('{"seed": 8, "music_volume": 4}', encoding="utf-8")

    read = settings_module.load(path)
    assert read.seed == 8
    assert read.screenshake is True


def test_the_volume_ships_audible_and_survives_a_round_trip(tmp_path) -> None:
    """A fresh install makes noise.

    Worth pinning rather than assuming: the cue layer sat in the tree unwired
    for a while, and a default of 0 would have made the wiring look broken while
    every test still passed.
    """
    assert Settings().volume == DEFAULT_VOLUME
    assert DEFAULT_VOLUME > 0, "the game ships silent"

    path = tmp_path / "settings.json"
    settings_module.save(Settings(volume=3), path)
    assert settings_module.load(path).volume == 3

    # Zero is a real setting and not a sentinel -- the row reads "off" there --
    # so it has to survive the trip rather than being read back as "unset".
    settings_module.save(Settings(volume=0), path)
    assert settings_module.load(path).volume == 0


def test_a_volume_outside_the_dial_is_clamped_not_dropped(tmp_path) -> None:
    """`Cues.level` clamps too, so a wild value could never be *heard*.

    It is clamped here as well because the options screen draws this number back
    to the player, and a row reading "99" that sounds like 10 is a preferences
    file arguing with the screen that edits it.
    """
    path = tmp_path / "settings.json"

    path.write_text('{"volume": 99}', encoding="utf-8")
    assert settings_module.load(path).volume == MAX_VOLUME

    path.write_text('{"volume": -4}', encoding="utf-8")
    assert settings_module.load(path).volume == 0

    # Still an int field, so the coercion above it still applies.
    path.write_text('{"volume": "loud"}', encoding="utf-8")
    assert settings_module.load(path).volume == DEFAULT_VOLUME


def test_the_window_follows_the_scale() -> None:
    from hack_and_slash import config

    assert Settings(scale=AUTO_SCALE).window_size == (config.WINDOW_W, config.WINDOW_H)
    assert Settings(scale=4).window_size == (config.INTERNAL_W * 4, config.INTERNAL_H * 4)


# --- the profile -------------------------------------------------------------
def test_a_machine_that_has_never_played_reads_as_zero(tmp_path) -> None:
    assert profile.load(tmp_path / "nothing.json") == profile.Profile()


def test_a_corrupt_profile_starts_again_rather_than_raising(tmp_path) -> None:
    path = tmp_path / "profile.json"
    path.write_text("not json", encoding="utf-8")
    assert profile.load(path) == profile.Profile()


def test_counters_accumulate_across_runs(tmp_path) -> None:
    path = tmp_path / "profile.json"
    profile.record_start(path)
    profile.record_start(path)
    assert profile.load(path).runs_started == 2


def test_deepest_stage_is_a_high_water_mark(tmp_path) -> None:
    """`max`, not assignment. A later run that died on stage two must not erase
    how far an earlier one got -- which is the whole meaning of "deepest", and
    the obvious thing to get wrong."""
    from hack_and_slash import config
    from hack_and_slash.core import campaign_io
    from hack_and_slash.game.run import Run

    from .helpers import BESTIARY

    campaign = campaign_io.load(config.LEVELS_DIR / "campaign.json")
    path = tmp_path / "profile.json"

    deep = Run.start(campaign, BESTIARY, at_stage=17)
    profile.record_stage(deep, path)

    shallow = Run.start(campaign, BESTIARY, at_stage=1)
    profile.record_stage(shallow, path)

    assert profile.load(path).deepest_stage == 18


def test_resetting_forgets_everything(tmp_path) -> None:
    path = tmp_path / "profile.json"
    profile.save(profile.Profile(runs_started=12, best_gold=9000), path)
    profile.reset(path)
    assert profile.load(path) == profile.Profile()


def test_resetting_a_profile_that_is_not_there_is_not_an_error(tmp_path) -> None:
    profile.reset(tmp_path / "nothing.json")
