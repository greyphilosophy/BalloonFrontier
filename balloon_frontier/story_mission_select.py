"""Story mission availability, replay, and explicit mission resolution."""

from __future__ import annotations

from dataclasses import dataclass

from balloon_frontier.progression import PlayerRegistry
from balloon_frontier.story import (
    COLLEGE_METEOROLOGY_CHAPTER,
    FIRST_FLIGHT_CHAPTER,
    SUMMER_HOBBYIST_CHAPTER,
    StoryChapter,
)


STORY_CHAPTERS: tuple[StoryChapter, ...] = (
    FIRST_FLIGHT_CHAPTER,
    SUMMER_HOBBYIST_CHAPTER,
    COLLEGE_METEOROLOGY_CHAPTER,
)


@dataclass(frozen=True, slots=True)
class StoryMissionChoice:
    """One mission visible on Story Mission Select."""

    chapter: StoryChapter
    completed: bool
    is_next: bool

    @property
    def mission_id(self) -> str:
        return self.chapter.mission_id


def story_mission_choices(player_id: str | int | None = None) -> tuple[StoryMissionChoice, ...]:
    """Return completed missions plus exactly the next incomplete mission.

    Completed missions stay visible for replay. Story missions after the first
    incomplete chapter remain hidden until progression reaches them.
    """

    completed: set[str] = set()
    if player_id is not None:
        player = PlayerRegistry.get_or_create(str(player_id))
        completed = set(player.missions_completed)

    choices: list[StoryMissionChoice] = []
    for chapter in STORY_CHAPTERS:
        if chapter.mission_id in completed:
            choices.append(
                StoryMissionChoice(chapter=chapter, completed=True, is_next=False)
            )
            continue

        choices.append(
            StoryMissionChoice(chapter=chapter, completed=False, is_next=True)
        )
        break

    return tuple(choices)


def resolve_story_mission(
    player_id: str | int | None = None,
    requested_mission_id: str | None = None,
) -> str:
    """Resolve the active Story mission, validating explicit replay requests."""

    choices = story_mission_choices(player_id)
    visible_ids = {choice.mission_id for choice in choices}

    if requested_mission_id is not None:
        if requested_mission_id not in visible_ids:
            raise ValueError(
                f"Story mission {requested_mission_id!r} is not unlocked for this player"
            )
        return requested_mission_id

    next_choice = next((choice for choice in choices if choice.is_next), None)
    if next_choice is not None:
        return next_choice.mission_id

    if choices:
        return choices[-1].mission_id

    # STORY_CHAPTERS always contains the first flight, but keep the fallback
    # explicit so this helper remains total if the chapter list is refactored.
    return FIRST_FLIGHT_CHAPTER.mission_id
