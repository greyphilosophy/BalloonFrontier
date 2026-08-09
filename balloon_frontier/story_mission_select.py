"""Story mission availability, replay, and explicit mission resolution."""

from __future__ import annotations

from dataclasses import dataclass

from balloon_frontier.atmosphere_profile import atmosphere_profiles
from balloon_frontier.progression import PlayerRegistry
from balloon_frontier.story import (
    COLLEGE_METEOROLOGY_CHAPTER,
    FIRST_FLIGHT_CHAPTER,
    STORY_DISCLAIMER,
    SUMMER_HOBBYIST_CHAPTER,
    StoryChapter,
    _LockAtmosphereButton,
    format_atmosphere_profile,
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


def story_chapter_for_mission(mission_id: str) -> StoryChapter:
    for chapter in STORY_CHAPTERS:
        if chapter.mission_id == mission_id:
            return chapter
    raise ValueError(f"Unknown Story mission: {mission_id!r}")


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


def selected_story_intro(
    chapter: StoryChapter,
    *,
    player_id: str | None = None,
    atmosphere_locked: bool = False,
    include_disclaimer: bool = True,
) -> str:
    """Render a briefing for the selected chapter rather than progression's next one."""

    bonuses = "\n".join(f"• {item}" for item in chapter.bonus_challenges)
    text = (
        f"📖 **{chapter.title}**\n"
        f"*{chapter.season}*\n\n"
        f"{chapter.introduction}\n\n"
        "**Primary objective**\n"
        f"{chapter.primary_objective}"
    )
    if bonuses:
        text += f"\n\n**Bonus challenges**\n{bonuses}"
    if chapter.future_challenges:
        future = "\n".join(f"• {item}" for item in chapter.future_challenges)
        text += f"\n\n**Future cinematic challenges**\n{future}"
    if atmosphere_locked:
        text += (
            "\n\n🔒 **Measured conditions selected.** "
            "This recorded atmosphere will drive the next launch."
        )
    elif player_id and atmosphere_profiles.get(str(player_id)) is not None:
        text += "\n\n📡 A recorded atmosphere profile is available below."
    if include_disclaimer and chapter is not FIRST_FLIGHT_CHAPTER:
        text += f"\n\n*{STORY_DISCLAIMER}*"
    return text


class SelectedStoryConfiguratorMixin:
    """Story briefing/atmosphere UI bound to the explicitly selected mission."""

    def __init__(self, *args, **kwargs):
        self._atmosphere_locked = False
        super().__init__(*args, **kwargs)

    def _selected_story_chapter(self) -> StoryChapter:
        mission_id = getattr(self._service, "story_mission_id", None)
        return story_chapter_for_mission(str(mission_id))

    def _step_content(self) -> str:
        player_id = getattr(self._service, "story_player_id", None)
        text = selected_story_intro(
            self._selected_story_chapter(),
            player_id=player_id,
            atmosphere_locked=self._atmosphere_locked,
            include_disclaimer=self._current_step == 0,
        )
        if player_id:
            profile = atmosphere_profiles.get(str(player_id))
            if profile is not None:
                text += "\n\n" + format_atmosphere_profile(profile)
        return text + "\n\n" + super()._step_content()

    def build_buttons(self):
        super().build_buttons()
        player_id = getattr(self._service, "story_player_id", None)
        has_profile = bool(player_id) and atmosphere_profiles.get(
            str(player_id)
        ) is not None
        if self._current_step == 5 and has_profile and not self._atmosphere_locked:
            self.add_item(_LockAtmosphereButton(self))
