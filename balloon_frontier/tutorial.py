"""Shared content and outcome rules for the Balloon Frontier tutorial."""

from __future__ import annotations

from dataclasses import dataclass, replace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult


TUTORIAL_MISSION_ID = "first_flight"


@dataclass(frozen=True)
class TutorialStep:
    title: str
    prompt: str


TUTORIAL_STEPS = {
    0: TutorialStep(
        "Choose a lifting gas",
        "Select a gas. The menu includes each gas's density so you can compare the available lift.",
    ),
    1: TutorialStep(
        "Choose a balloon",
        "Select the envelope that will support the aircraft.",
    ),
    2: TutorialStep(
        "Choose a fill",
        "Select how much free lift the balloon should provide.",
    ),
    3: TutorialStep(
        "Choose the aircraft",
        "Select the vehicle that will steer and remain aloft.",
    ),
    4: TutorialStep(
        "Choose a test site",
        "Select where to perform the radio-control endurance test.",
    ),
    5: TutorialStep(
        "Review and launch",
        "Review the design and launch it. The flight result will show whether it remained controllable and in communications range.",
    ),
}


def tutorial_guidance(step: int) -> str:
    info = TUTORIAL_STEPS[step]
    return f"🎓 **{info.title}**\n{info.prompt}"


def is_tutorial_mode(mode) -> bool:
    return mode is GameMode.TUTORIAL or mode == GameMode.TUTORIAL.value


def evaluate_tutorial_outcome(request, outcome: FlightOutcome) -> FlightOutcome:
    """Apply the UI tutorial's simple, deterministic success condition.

    Choices are never blocked or explained in advance. The mission succeeds only
    for the intentionally modest balloon-assisted aircraft configuration.
    """

    payloads = set(request.payload_ids)
    success = (
        request.envelope_id == "mylar"
        and request.gas_id == "helium"
        and "quadcopter" in payloads
        and request.launch_site_id == "field"
    )

    if success:
        explanation = "The balloon-assisted quadcopter remained controllable and completed the endurance flight."
        reward = 500
    elif request.gas_id == "hydrogen":
        explanation = "The aircraft left communications range and was lost."
        reward = 0
    elif request.envelope_id != "mylar":
        explanation = "The aircraft could not be steered through the test course."
        reward = 0
    elif "quadcopter" not in payloads:
        explanation = "The vehicle could not maintain controlled flight."
        reward = 0
    else:
        explanation = "The endurance flight was not completed."
        reward = 0

    mission_result = MissionResult(
        mission_id=TUTORIAL_MISSION_ID,
        completed=success,
        reward=reward,
        explanation=explanation,
    )
    return replace(outcome, mission_results=(mission_result,))


def tutorial_result_summary(outcome: FlightOutcome) -> str:
    mission = next(
        (item for item in outcome.mission_results if item.mission_id == TUTORIAL_MISSION_ID),
        None,
    )
    if mission is None:
        return "🎓 The tutorial flight produced no mission result."
    status = "Tutorial complete" if mission.completed else "Tutorial flight failed"
    return f"🎓 **{status}**\n{mission.explanation}"


class TutorialConfiguratorMixin:
    """Add tutorial prompts while leaving every normal UI choice available."""

    def _step_content(self) -> str:
        return tutorial_guidance(self._current_step) + "\n\n" + super()._step_content()
