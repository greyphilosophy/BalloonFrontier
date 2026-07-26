"""Story-mode chapters, progression, and telemetry-backed challenges."""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import pstdev

from balloon_frontier.atmosphere_profile import atmosphere_profiles, profile_from_telemetry
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.progression import PlayerRegistry


EDGE_OF_SPACE_MISSION_ID = "edge_of_space"
ATMOSPHERIC_RIVER_MISSION_ID = "atmospheric_river_sounding"


@dataclass(frozen=True, slots=True)
class StoryChapter:
    id: str
    title: str
    season: str
    introduction: str
    mission_id: str
    primary_objective: str
    bonus_challenges: tuple[str, ...] = ()
    future_challenges: tuple[str, ...] = ()


SUMMER_HOBBYIST_CHAPTER = StoryChapter(
    id="summer_hobbyist",
    title="Summer Project: Edge of Space",
    season="Summer after senior year",
    introduction=(
        "Your last balloon video finally got some views and earned a little revenue. "
        "Now everyone is waiting for the maiden flight of your newest design. "
        "Show them something spectacular—without spending money you do not have."
    ),
    mission_id=EDGE_OF_SPACE_MISSION_ID,
    primary_objective="Send a camera to at least 30 km and return usable footage of Earth's curvature.",
    bonus_challenges=("Stable footage", "Controlled recovery"),
    future_challenges=(
        "Capture Earth and the Moon in the same video.",
        "Record the longest sunset.",
    ),
)

COLLEGE_METEOROLOGY_CHAPTER = StoryChapter(
    id="college_meteorology",
    title="Atmospheric River",
    season="Freshman fall",
    introduction=(
        "A meteorology professor has taken an interest in your balloon work. "
        "'We're launching several soundings over the next few days to track an "
        "atmospheric river. Want to do some real work?' she asks, already knowing "
        "you cannot refuse."
    ),
    mission_id=ATMOSPHERIC_RIVER_MISSION_ID,
    primary_objective=(
        "Carry weather instruments through the troposphere and recover a vertical "
        "profile of wind, temperature, and pressure."
    ),
    bonus_challenges=("Reach 18 km", "Recover the instruments"),
)


def current_story_chapter(player_id: str | None = None) -> StoryChapter:
    if not player_id:
        return SUMMER_HOBBYIST_CHAPTER
    player = PlayerRegistry.get_or_create(str(player_id))
    if EDGE_OF_SPACE_MISSION_ID in player.missions_completed:
        return COLLEGE_METEOROLOGY_CHAPTER
    return SUMMER_HOBBYIST_CHAPTER


def story_intro(player_id: str | None = None) -> str:
    chapter = current_story_chapter(player_id)
    bonuses = "\n".join(f"• {item}" for item in chapter.bonus_challenges)
    text = (
        f"📖 **{chapter.title}**\n"
        f"*{chapter.season}*\n\n"
        f"{chapter.introduction}\n\n"
        "**Primary objective**\n"
        f"{chapter.primary_objective}\n\n"
        "**Bonus challenges**\n"
        f"{bonuses}"
    )
    if chapter.future_challenges:
        future = "\n".join(f"• {item}" for item in chapter.future_challenges)
        text += f"\n\n**Future cinematic challenges**\n{future}"
    if player_id and atmosphere_profiles.get(str(player_id)) is not None:
        text += "\n\n📡 A recorded atmosphere profile is available to lock for one future flight."
    return text


def story_mission_for_player(player_id: str | None = None) -> str:
    return current_story_chapter(player_id).mission_id


def _stable_footage(outcome: FlightOutcome) -> bool:
    telemetry = tuple(outcome.result.telemetry)
    velocities = [point.velocity_mps for point in telemetry if not point.landed]
    return len(velocities) >= 2 and pstdev(velocities) <= 8.0


def _controlled_recovery(outcome: FlightOutcome) -> bool:
    telemetry = tuple(outcome.result.telemetry)
    return any(point.landed for point in telemetry) and not any(point.crashed for point in telemetry)


def add_story_results(outcome: FlightOutcome, player_id: str | None = None) -> FlightOutcome:
    """Add chapter bonuses and save sounding data from successful weather missions."""

    existing = tuple(outcome.mission_results)
    mission_ids = {item.mission_id for item in existing}
    if EDGE_OF_SPACE_MISSION_ID in mission_ids:
        stable = _stable_footage(outcome)
        recovered = _controlled_recovery(outcome)
        bonuses = (
            MissionResult(
                mission_id="bonus_stable_footage",
                completed=stable,
                reward=0,
                explanation=(
                    "The camera returned steady, watchable footage."
                    if stable else "The footage was too unstable to earn the stable-flight bonus."
                ),
            ),
            MissionResult(
                mission_id="bonus_controlled_recovery",
                completed=recovered,
                reward=0,
                explanation=(
                    "The payload completed a controlled recovery."
                    if recovered else "The payload was not recovered under control."
                ),
            ),
        )
        return replace(outcome, mission_results=existing + bonuses)

    sounding = next((item for item in existing if item.mission_id == ATMOSPHERIC_RIVER_MISSION_ID), None)
    if sounding and sounding.completed and player_id and outcome.weather is not None:
        profile = profile_from_telemetry(outcome.result.telemetry, outcome.weather)
        atmosphere_profiles.save(str(player_id), profile)
        recorded = MissionResult(
            mission_id="bonus_atmosphere_profile",
            completed=bool(profile.layers),
            reward=0,
            explanation=f"Recorded {len(profile.layers)} atmospheric layers for future launches.",
        )
        return replace(outcome, mission_results=existing + (recorded,))
    return outcome


# Compatibility name retained for callers added by the first Story chapter.
def add_story_bonus_results(outcome: FlightOutcome) -> FlightOutcome:
    return add_story_results(outcome)


class StoryConfiguratorMixin:
    """Add the current player's Story chapter briefing above the configurator."""

    def _step_content(self) -> str:
        player_id = getattr(self._service, "story_player_id", None)
        return story_intro(player_id) + "\n\n" + super()._step_content()
