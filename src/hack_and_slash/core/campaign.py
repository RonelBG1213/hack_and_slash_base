"""An ordered sequence of stages, and the rules for one being playable at all.

A `Level` is one arena. A `Campaign` is the arenas in the order you fight them.
It is immutable and never mutated by a run, which is what lets a run restart from
the top without reloading anything from disk.

Validation is the whole reason this is a type rather than a list. A campaign
whose third stage spawns an enemy inside a pillar should refuse to start, not
fail two minutes into a run when the player finally reaches it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .level import Level


@dataclass(frozen=True)
class Campaign:
    name: str
    stages: tuple[Level, ...]

    def __len__(self) -> int:
        return len(self.stages)

    def __getitem__(self, index: int) -> Level:
        return self.stages[index]

    @property
    def length(self) -> int:
        return len(self.stages)

    def is_final(self, index: int) -> bool:
        return index >= len(self.stages) - 1

    def stage_number(self, index: int) -> int:
        """1-based, for anything a player reads."""
        return index + 1

    def problems(self) -> list[str]:
        """Everything wrong with this campaign, in plain words.

        Returned rather than raised so a tool can report every fault at once,
        matching `Level.problems()`. Each stage's own problems are included,
        prefixed with which stage they came from -- "the hero spawns inside a
        wall" is a great deal more useful with a stage number on it.
        """
        if not self.stages:
            return ["the campaign has no stages"]

        issues: list[str] = []
        for index, stage in enumerate(self.stages):
            for problem in stage.problems():
                issues.append(f"stage {self.stage_number(index)} ({stage.name}): {problem}")
        return issues

    @property
    def is_playable(self) -> bool:
        return not self.problems()
