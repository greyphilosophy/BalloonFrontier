"""Install the canonical spring-break yearbook tutorial mission."""

from __future__ import annotations

from functools import wraps


def install_tutorial_mission_guard() -> None:
    from balloon_frontier import tutorial
    from balloon_frontier.tutorial_powered_flight import apply_tutorial_powered_flight

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
                "Review the yearbook flight",
                "Review the buoyancy-assisted quadcopter and launch the spring-break school photography mission.",
            ),
        }
    )

    current = tutorial.evaluate_tutorial_outcome
    if getattr(current, "_balloon_frontier_yearbook_mission", False):
        return

    @wraps(current)
    def evaluate(request, outcome):
        powered = apply_tutorial_powered_flight(request, outcome)
        evaluated = current(request, powered)
        rewritten = []
        for mission in evaluated.mission_results:
            if mission.mission_id != "first_flight":
                rewritten.append(mission)
                continue
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
            rewritten.append(
                type(mission)(
                    mission_id=mission.mission_id,
                    completed=mission.completed,
                    reward=mission.reward,
                    explanation=explanation,
                )
            )
        from dataclasses import replace

        return replace(evaluated, mission_results=tuple(rewritten))

    evaluate._balloon_frontier_yearbook_mission = True
    tutorial.evaluate_tutorial_outcome = evaluate
