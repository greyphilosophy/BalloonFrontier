from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Tuple


class WelcomeMode(str, Enum):
    """Game modes exposed by the welcome screen."""

    TUTORIAL = "tutorial"
    STORY = "story"
    SCENARIO = "scenario"
    FREE_PLAY = "free_play"
    WORKSHOP = "workshop"


@dataclass(frozen=True)
class WelcomeOption:
    """A single selectable option on the welcome screen."""

    mode: WelcomeMode
    option_id: str
    title: str
    description: str
    is_default: bool = False

    def to_ui(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "option_id": self.option_id,
            "title": self.title,
            "description": self.description,
            "is_default": self.is_default,
        }


@dataclass(frozen=True)
class WelcomeScreen:
    """Menu UI model that supports new vs returning players."""

    is_returning: bool
    options: Tuple[WelcomeOption, ...]

    @staticmethod
    def _default_for_returning(is_returning: bool) -> WelcomeMode:
        # New players get a guided onboarding first.
        # Returning players can jump straight into open-ended play.
        return WelcomeMode.FREE_PLAY if is_returning else WelcomeMode.TUTORIAL

    @classmethod
    def build(cls, *, is_returning: bool) -> "WelcomeScreen":
        default_mode = cls._default_for_returning(is_returning)

        def opt(mode: WelcomeMode, title: str, description: str) -> WelcomeOption:
            return WelcomeOption(
                mode=mode,
                option_id=mode.value,
                title=title,
                description=description,
                is_default=(mode == default_mode),
            )

        # Always expose all modes for both new and returning players.
        options = (
            opt(
                WelcomeMode.TUTORIAL,
                "Tutorial",
                "Learn the core Balloon Frontier loop step-by-step.",
            ),
            opt(
                WelcomeMode.STORY,
                "Story",
                "Follow guided chapters and unlock narrative objectives.",
            ),
            opt(
                WelcomeMode.SCENARIO,
                "Scenario",
                "Try a defined challenge with curated constraints and scoring.",
            ),
            opt(
                WelcomeMode.FREE_PLAY,
                "Free Play",
                "Explore without gates—choose your own missions and pacing.",
            ),
            opt(
                WelcomeMode.WORKSHOP,
                "Workshop",
                "Build, tweak, and review equipment & mission-ready setups.",
            ),
        )

        return cls(is_returning=is_returning, options=options)

    def get_default_mode(self) -> WelcomeMode:
        for o in self.options:
            if o.is_default:
                return o.mode
        # Should never happen, but keep behavior deterministic.
        return self._default_for_returning(self.is_returning)

    def available_modes(self) -> Tuple[WelcomeMode, ...]:
        return tuple(o.mode for o in self.options)

    def get_option(self, mode: WelcomeMode) -> WelcomeOption:
        for o in self.options:
            if o.mode == mode:
                return o
        raise KeyError(f"No welcome option for mode: {mode}")

    def select(self, selection_id: str) -> WelcomeMode:
        """Map a selection string to a WelcomeMode.

        Accepts:
        - exact option_id (e.g. "free_play")
        - matching enum value (e.g. "scenario")
        - a few user-friendly aliases (e.g. "free play")
        """

        normalized = (selection_id or "").strip().lower().replace(" ", "_")
        # Direct enum/value match.
        for mode in WelcomeMode:
            if normalized == mode.value:
                return mode

        # Title-ish fallback: "free play" -> FREE_PLAY
        aliases = {
            "free-play": WelcomeMode.FREE_PLAY,
            "freeplay": WelcomeMode.FREE_PLAY,
            "free_play": WelcomeMode.FREE_PLAY,
        }
        if normalized in aliases:
            return aliases[normalized]

        # If user passed the exact title, try a crude mapping.
        for o in self.options:
            if normalized == o.title.strip().lower().replace(" ", "_"):
                return o.mode

        raise ValueError(f"Unknown welcome selection: {selection_id!r}")

    def to_ui(self) -> Dict[str, Any]:
        return {
            "type": "welcome",
            "title": "Balloon Frontier — Welcome",
            "is_returning": self.is_returning,
            "default_mode": self.get_default_mode().value,
            "options": [o.to_ui() for o in self.options],
        }


__all__ = [
    "WelcomeMode",
    "WelcomeOption",
    "WelcomeScreen",
]
