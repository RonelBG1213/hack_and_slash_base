"""Reading `levels/campaign.json` -- the manifest naming the stages, in order.

A manifest rather than a naming convention (`stage1.json`, `stage2.json`, ...)
because the order is a design decision worth writing down, and because reordering
or dropping a stage should be an edit to one file rather than a rename of several.

Stage files are ordinary levels, loaded through `level_io`. Nothing about a level
changes because it is part of a campaign.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import level_io
from .campaign import Campaign
from .level_io import LevelFormatError

SCHEMA_VERSION = 1


class CampaignFormatError(ValueError):
    """A manifest that cannot be turned into a Campaign at all.

    Distinct from `Campaign.problems()`, which is about a campaign that loads
    fine but would not be fair to play.
    """


def to_dict(campaign: Campaign, stage_files: list[str]) -> dict[str, Any]:
    if len(stage_files) != len(campaign.stages):
        raise CampaignFormatError(
            f"{len(stage_files)} filenames for {len(campaign.stages)} stages"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "name": campaign.name,
        "stages": stage_files,
    }


def load(path: Path) -> Campaign:
    """Read a manifest and every stage it names.

    Stage paths are resolved relative to the manifest, so a campaign directory
    can be moved or copied without editing it.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CampaignFormatError(
            f"no campaign at {path} -- run `python tools/make_level.py` to build it"
        ) from None
    except json.JSONDecodeError as exc:
        raise CampaignFormatError(f"{path.name} is not valid JSON: {exc}") from exc

    version = payload.get("schema_version", SCHEMA_VERSION)
    if version > SCHEMA_VERSION:
        raise CampaignFormatError(
            f"{path.name} was written by a newer build (schema {version}, this build "
            f"reads {SCHEMA_VERSION})"
        )

    names = payload.get("stages")
    if not isinstance(names, list) or not names:
        raise CampaignFormatError(f"{path.name}: 'stages' must be a non-empty list")

    stages = []
    for position, filename in enumerate(names, start=1):
        stage_path = path.parent / filename
        try:
            stages.append(level_io.load(stage_path))
        except FileNotFoundError:
            # Naming the stage *and* the file is the difference between a
            # useful error and a bare traceback about a missing path.
            raise CampaignFormatError(
                f"{path.name} lists stage {position} as '{filename}', which does not exist"
            ) from None
        except LevelFormatError as exc:
            raise CampaignFormatError(f"stage {position} ('{filename}'): {exc}") from exc

    return Campaign(name=payload.get("name", "unnamed"), stages=tuple(stages))


def save(campaign: Campaign, path: Path, stage_files: list[str]) -> None:
    """Write the manifest only. The stage files are written by `level_io.save`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = to_dict(campaign, stage_files)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
