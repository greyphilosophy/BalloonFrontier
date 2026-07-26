"""Balloon Frontier — Game mode selection.

This module is the shared, UI-agnostic controller layer for deciding:
- which high-level game mode a player is in (Tutorial / Story / Scenario / Free Play)
- how to parse/normalize that selection across Discord + CLI

It intentionally does *not* embed mission planning or simulation-duration
policy. Those belong in later scenario/story/tutorial/free-play controllers
once mode-specific context exists.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Sequence


class GameMode(str, Enum):
    """High-level game mode selection."""

    TUTORIAL = "tutorial"
    STORY = "story"
    SCENARIO = "scenario"
    FREE_PLAY = "free_play"

    @property
    def label(self) -> str:
        return {
            GameMode.TUTORIAL: "Tutorial",
            GameMode.STORY: "Story",
            GameMode.SCENARIO: "Scenario",
            GameMode.FREE_PLAY: "Free Play",
        }[self]

    @property
    def description(self) -> str:
        return {
            GameMode.TUTORIAL: "A short, low-stakes first flight.",
            GameMode.STORY: "A narrative run with mission objectives.",
            GameMode.SCENARIO: "A mission run with a themed objective set.",
            GameMode.FREE_PLAY: "Sandbox flight — no mission commitments.",
        }[self]


_GAME_MODE_ORDER: Sequence[GameMode] = (
    GameMode.TUTORIAL,
    GameMode.STORY,
    GameMode.SCENARIO,
    GameMode.FREE_PLAY,
)


def list_game_modes() -> List[GameMode]:
    """Return modes in the canonical display order."""

    return list(_GAME_MODE_ORDER)


def select_game_mode(value: str | int) -> GameMode:
    """Coerce a CLI/Discord selection into a :class:`GameMode`.

    Accepted inputs:
    - integer indices 1..4 (Tutorial..Free Play)
    - case-insensitive strings: tutorial/story/scenario/free_play
    - case-insensitive strings: "free play" / "free-play"

    Raises:
        ValueError: if the input can't be mapped.
    """

    if isinstance(value, int):
        idx = value
        if 1 <= idx <= len(_GAME_MODE_ORDER):
            return _GAME_MODE_ORDER[idx - 1]
        raise ValueError(f"Invalid game mode index: {value}")

    s = str(value).strip().lower()
    s = s.replace("-", "_").replace(" ", "_")

    if s in {"tutorial"}:
        return GameMode.TUTORIAL
    if s in {"story"}:
        return GameMode.STORY
    if s in {"scenario"}:
        return GameMode.SCENARIO
    if s in {"free_play", "freeplay", "free_play_mode", "freeplay_mode"}:
        return GameMode.FREE_PLAY
    if s in {"free", "sandbox"}:
        return GameMode.FREE_PLAY

    raise ValueError(f"Invalid game mode selection: {value!r}")
