"""Balloon Frontier — playable game mode selection.

How-to-play guidance is presentation, not a simulation mode. Story owns the
first-flight onboarding experience and uses the same physics path as every
other Story flight.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Sequence


class GameMode(str, Enum):
    """High-level simulation modes.

    ``TUTORIAL`` remains as a compatibility value for older callers and saved
    references. New UI must not present it; session planning normalizes it to
    Story so there is no separate tutorial simulation path.
    """

    TUTORIAL = "tutorial"
    STORY = "story"
    SCENARIO = "scenario"
    FREE_PLAY = "free_play"

    @property
    def label(self) -> str:
        return {
            GameMode.TUTORIAL: "Story",
            GameMode.STORY: "Story",
            GameMode.SCENARIO: "Scenario",
            GameMode.FREE_PLAY: "Free Play",
        }[self]

    @property
    def description(self) -> str:
        return {
            GameMode.TUTORIAL: "Legacy alias for Story onboarding.",
            GameMode.STORY: "A narrative campaign whose available choices grow with the story.",
            GameMode.SCENARIO: "A mission run with a themed objective set.",
            GameMode.FREE_PLAY: "Sandbox flight — no mission commitments.",
        }[self]


_GAME_MODE_ORDER: Sequence[GameMode] = (
    GameMode.STORY,
    GameMode.SCENARIO,
    GameMode.FREE_PLAY,
)


def list_game_modes() -> List[GameMode]:
    """Return player-selectable simulation modes in display order."""

    return list(_GAME_MODE_ORDER)


def select_game_mode(value: str | int) -> GameMode:
    """Coerce a CLI/Discord selection into a playable game mode.

    Integer selections address only the visible modes. The old ``tutorial``
    string is accepted as a compatibility alias for Story.
    """

    if isinstance(value, int):
        idx = value
        if 1 <= idx <= len(_GAME_MODE_ORDER):
            return _GAME_MODE_ORDER[idx - 1]
        raise ValueError(f"Invalid game mode index: {value}")

    s = str(value).strip().lower()
    s = s.replace("-", "_").replace(" ", "_")

    if s in {"tutorial", "story"}:
        return GameMode.STORY
    if s in {"scenario"}:
        return GameMode.SCENARIO
    if s in {"free_play", "freeplay", "free_play_mode", "freeplay_mode"}:
        return GameMode.FREE_PLAY
    if s in {"free", "sandbox"}:
        return GameMode.FREE_PLAY

    raise ValueError(f"Invalid game mode selection: {value!r}")
