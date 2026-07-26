"""Story-mode content and telemetry-backed bonus challenges."""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import pstdev

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import MissionResult


EDGE_OF_SPACE_MISSION_ID = "edge_of_space"


@dataclass(frozen=True, slots=True)
class StoryChapter:
    id: str
    title: str
    season: str
    introduction: str
    mission_id: str
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
    future_challenges=(
        "Capture Earth and the Moon in the same video.",
        "Record the longest sunset.",
    ),
)


def story_intro() -> str:
    chapter = SUMMER_HOBBYIST_CHAPTER
    future = "\n".join(f"• {item}" for item in chapter.future_challenges)
    return (
        f"📖 **{chapter.title}**\n"
        f"*{chapter.season}*\n\n"
        f"{chapter.introduction}\n\n"
        "**Primary objective**\n"
        "Send a camera to at least 30 km and return usable footage of Earth's curvature.\n\n"
        "**Bonus challenges tracked now**\n"
        "• Stable footage\n"
        "• Controlled recovery\n\n"
        "**Future cinematic challenges**\n"
        f"{future}"
    )


def _stable_footage(outcome: FlightOutcome) -> bool:
    telemetry = tuple(outcome.result.telemetry)
    velocities = [point.velocity_mps for point in telemetry if not point.landed]
    if len(velocities) < 2:
        return False
    return pstdev(velocities) <= 8.0


def _controlled_recovery(outcome: FlightOutcome) -> bool:
    telemetry = tuple(outcome.result.telemetry)
    return any(point.landed for point in telemetry) and not any(
        point.crashed for point in telemetry
    )


def add_story_bonus_results(outcome: FlightOutcome) -> FlightOutcome:
    """Append zero-credit Story bonus results judged from real telemetry."""

    existing = tuple(outcome.mission_results)
    if not any(item.mission_id == EDGE_OF_SPACE_MISSION_ID for item in existing):
        return outcome

    stable = _stable_footage(outcome)
    recovered = _controlled_recovery(outcome)
    bonuses = (
        MissionResult(
            mission_id="bonus_stable_footage",
            completed=stable,
            reward=0,
            explanation=(
                "The camera returned steady, watchable footage."
                if stable
                else "The footage was too unstable to earn the stable-flight bonus."
            ),
        ),
        MissionResult(
            mission_id="bonus_controlled_recovery",
            completed=recovered,
            reward=0,
            explanation=(
                "The payload completed a controlled recovery."
                if recovered
                else "The payload was not recovered under control."
            ),
        ),
    )
    return replace(outcome, mission_results=existing + bonuses)


class StoryConfiguratorMixin:
    """Add the current Story chapter briefing above the shared configurator."""

    def _step_content(self) -> str:
        return story_intro() + "\n\n" + super()._step_content()
