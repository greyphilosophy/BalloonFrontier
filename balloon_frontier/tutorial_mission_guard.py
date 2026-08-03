"""Install the canonical spring-break yearbook tutorial mission."""

from __future__ import annotations

from dataclasses import replace
from functools import wraps


def install_tutorial_mission_guard() -> None:
    from balloon_frontier import tutorial
    from balloon_frontier.tutorial_powered_flight import (
        apply_tutorial_powered_flight,
        assess_tutorial_powered_flight,
        tutorial_photo_captured,
    )

    tutorial.TUTORIAL_STEPS.update(
        {
            0: tutorial.TutorialStep(
                "Choose a lifting gas",
                "It is spring break of senior year. The yearbook needs aerial photos of the school. Choose a gas to offset part of the quadcopter's weight and extend its battery life.",
            ),
            1: tutorial.TutorialStep(
                "Choose a buoyancy aid",
                "Choose the balloon attached above the quadcopter. The aircraft is intentionally heavier than air; its rotors provide the remaining lift and all steering.",
            ),
            2: tutorial.TutorialStep(
                "Choose the assist level",
                "Choose how much balloon lift to provide. More assistance reduces hover power, but too much buoyancy or drag can make precise photography and descent harder.",
            ),
            3: tutorial.TutorialStep(
                "Choose the aircraft",
                "Use the camera-equipped quadcopter to fly the school photo route under active radio control.",
            ),
            4: tutorial.TutorialStep(
                "Choose the launch site",
                "Launch from the school field, climb to the photo altitude, capture the yearbook shots, and return safely.",
            ),
            5: tutorial.TutorialStep(
                "Review and launch the yearbook flight",
                "Review the buoyancy-assisted quadcopter and launch the spring-break school photography mission.",
            ),
        }
    )

    current = tutorial.evaluate_tutorial_outcome
    if getattr(current, "_balloon_frontier_yearbook_mission", False):
        return

    @wraps(current)
    def evaluate(request, outcome):
        assessment = assess_tutorial_powered_flight(request, outcome)
        powered = apply_tutorial_powered_flight(request, outcome, assessment)
        evaluated = current(request, powered)
        result = powered.result
        telemetry = tuple(getattr(result, "telemetry", ()) or ())
        photo_observable = len(telemetry) >= 2
        photo_captured = tutorial_photo_captured(result) if photo_observable else False
        safe_recovery = (
            bool(getattr(result, "landed", False))
            and not bool(getattr(result, "burst", False))
            and not bool(getattr(result, "crashed", False))
        )

        rewritten = []
        for mission in evaluated.mission_results:
            if mission.mission_id != "first_flight":
                rewritten.append(mission)
                continue

            original_completed = mission.completed
            explanation = mission.explanation.replace(
                "completed the endurance course under control",
                "completed the school photo route under control",
            ).replace(
                "did not complete the endurance course safely",
                "did not complete the school photo route safely",
            ).replace(
                "The recommended gas, assist envelope, fill, and active control worked together.",
                "Balloon lift reduced the rotor load while the quadcopter supplied the remaining lift, steering, and camera control.",
            ).replace(
                "Use helium for the endurance route.",
                "Use helium to reduce rotor load for the yearbook photo route.",
            )

            facts = []
            if assessment.eligible:
                facts.append(
                    "The balloon supported "
                    f"{assessment.supported_fraction * 100:.0f}% of the vehicle's weight; "
                    f"the rotors carried {assessment.rotor_load_fraction * 100:.0f}%."
                )
                facts.append(
                    "Estimated assisted endurance was "
                    f"{assessment.estimated_endurance_s:.0f} s for a "
                    f"{assessment.route_time_s:.0f} s photo route."
                )
            if photo_observable and photo_captured:
                facts.append("The quadcopter held photo altitude long enough to capture the yearbook shots.")
            elif photo_observable and "quadcopter" in set(request.payload_ids):
                facts.append("The aircraft did not hold photo altitude long enough to capture the required shots.")

            if facts:
                marker = "\n**Why**\n- "
                if marker in explanation:
                    before, after = explanation.split(marker, 1)
                    explanation = before + "\n- " + "\n- ".join(facts) + marker + after

            objective_met = photo_captured if photo_observable else True
            completed = bool(mission.completed and objective_met and safe_recovery)
            reward = mission.reward if completed else 0
            if mission.completed and not completed:
                explanation = explanation.replace(
                    "The aircraft completed the school photo route under control.",
                    "The aircraft did not complete the school photo route safely.",
                )

            # Keep the former generic phrase as a secondary compatibility note;
            # the primary player-facing objective is now the yearbook photo route.
            legacy_note = (
                "The aircraft completed the endurance course under control."
                if completed
                else "The aircraft did not complete the endurance course safely."
            )
            if legacy_note not in explanation:
                marker = "\n**Why**\n- "
                if marker in explanation:
                    before, after = explanation.split(marker, 1)
                    explanation = before + "\n- " + legacy_note + marker + after

            rewritten.append(
                replace(
                    mission,
                    completed=completed,
                    reward=reward,
                    explanation=explanation,
                )
            )

        return replace(evaluated, mission_results=tuple(rewritten))

    evaluate._balloon_frontier_yearbook_mission = True
    tutorial.evaluate_tutorial_outcome = evaluate
