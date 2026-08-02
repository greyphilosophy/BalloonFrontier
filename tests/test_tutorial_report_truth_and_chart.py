"""Tutorial reports must distinguish observed facts from unmodeled causes."""

from types import SimpleNamespace

from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.tutorial import evaluate_tutorial_outcome


def _request():
    return SimpleNamespace(
        gas_id="helium",
        envelope_id="latex",
        fill_mode=SimpleNamespace(value="heavy"),
        payload_ids=("quadcopter",),
        launch_site_id="field",
        balloon_count=1,
    )


def test_unresolved_quadcopter_flight_does_not_invent_a_control_failure():
    outcome = FlightOutcome(
        result=SimpleNamespace(
            peak_altitude_m=5548.0,
            duration_s=4704.0,
            burst=False,
            landed=False,
            crashed=False,
        )
    )

    mission = evaluate_tutorial_outcome(_request(), outcome).mission_results[0]

    assert not mission.completed
    assert "still airborne" in mission.explanation
    assert "does not yet simulate quadcopter battery endurance" in mission.explanation
    assert "cannot identify a specific control failure" in mission.explanation
    assert "telemetry does not prove which one prevented recovery" in mission.explanation


def test_discord_trajectory_chart_is_wrapped_in_text_code_fence():
    chart = launch_handler.chart_to_string(
        [0.0, 1.0, 2.0],
        [0.0, 10.0, 0.0],
        title="Flight Trajectory",
    )

    assert chart.startswith("```text\n")
    assert chart.endswith("\n```")
    assert "Flight Trajectory" in chart
