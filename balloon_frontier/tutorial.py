"""Shared guidance and Discord UI for the Your First Flight tutorial."""

from __future__ import annotations

from dataclasses import dataclass

from balloon_frontier.game_modes import GameMode


@dataclass(frozen=True)
class TutorialStep:
    title: str
    lesson: str
    recommendation: str


TUTORIAL_STEPS = {
    0: TutorialStep(
        "Choose a lifting gas",
        "A lifting gas is less dense than the surrounding air, so buoyancy can overcome the vehicle's weight.",
        "Helium is recommended for this first flight because it is non-flammable and easy to handle.",
    ),
    1: TutorialStep(
        "Choose an envelope",
        "The envelope contains the lifting gas. Latex weather balloons expand as outside pressure falls.",
        "Use the standard latex weather balloon for this training flight.",
    ),
    2: TutorialStep(
        "Choose a fill",
        "More gas increases free lift and ascent rate, but excessive fill can make the balloon burst earlier.",
        "Auto fill calculates a safe introductory amount.",
    ),
    3: TutorialStep(
        "Choose a payload",
        "Every payload adds useful capability and additional mass. More mass requires more lift.",
        "Carry the camera so the flight produces its first useful observation.",
    ),
    4: TutorialStep(
        "Choose a launch site",
        "Altitude, temperature, and wind at the launch site change the balloon's initial conditions.",
        "The open field is the safest and simplest place to begin.",
    ),
    5: TutorialStep(
        "Review and launch",
        "The normal simulator, scoring system, weather, and mission evaluator will judge this flight.",
        "Check the configuration, then launch when ready.",
    ),
}


def tutorial_guidance(step: int) -> str:
    info = TUTORIAL_STEPS[step]
    return f"🎓 **{info.title}**\n{info.lesson}\n\n💡 {info.recommendation}"


def tutorial_result_summary(outcome) -> str:
    """Explain the important results of a completed tutorial flight."""
    result = outcome.result
    mission_passed = any(
        item.mission_id == "first_flight" and item.completed
        for item in outcome.mission_results
    )
    status = "Tutorial complete!" if mission_passed else "Good first attempt — adjust the design and try again."
    return (
        f"🎓 **{status}**\n"
        f"Peak altitude: {result.peak_altitude_m:.0f} m\n"
        f"Flight time: {result.duration_s:.0f} s\n"
        f"Score: {outcome.score:.0f}\n\n"
        "Peak altitude shows how high the design climbed. Flight time shows how long it remained airborne. "
        "The mission result confirms whether the camera flight met the training objectives."
    )


def is_tutorial_mode(mode) -> bool:
    return mode is GameMode.TUTORIAL or mode == GameMode.TUTORIAL.value
