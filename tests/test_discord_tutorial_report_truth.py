"""Tutorial reports must distinguish observed facts from unmodeled causes."""

from types import SimpleNamespace

from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.tutorial import evaluate_tutorial_outcome
from balloon_frontier.tutorial_report_guard import _safe_discord_content


def _request(*, gas="helium", envelope="latex", fill="heavy"):
    return SimpleNamespace(
        gas_id=gas,
        envelope_id=envelope,
        fill_mode=SimpleNamespace(value=fill),
        payload_ids=("quadcopter",),
        launch_site_id="field",
        balloon_count=1,
    )


def _outcome(
    *,
    burst=False,
    landed=False,
    crashed=False,
    final_velocity=-2.0,
):
    return FlightOutcome(
        result=SimpleNamespace(
            peak_altitude_m=5548.0,
            duration_s=4704.0,
            burst=burst,
            landed=landed,
            crashed=crashed,
            telemetry=(
                SimpleNamespace(altitude_m=0.0, velocity_mps=3.0),
                SimpleNamespace(altitude_m=5548.0, velocity_mps=0.0),
                SimpleNamespace(altitude_m=4300.0, velocity_mps=final_velocity),
            ),
        )
    )


def test_unresolved_quadcopter_flight_does_not_invent_a_control_failure():
    mission = evaluate_tutorial_outcome(_request(), _outcome()).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "still airborne" in mission.explanation
    assert "does not yet simulate quadcopter battery endurance" in mission.explanation
    assert "cannot identify a specific control failure" in mission.explanation
    assert "telemetry does not prove which one prevented recovery" in mission.explanation


def test_recommended_configuration_cannot_pass_without_confirmed_recovery():
    mission = evaluate_tutorial_outcome(
        _request(envelope="mylar", fill="auto"),
        _outcome(),
    ).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "did not complete a confirmed recovery" in mission.explanation
    assert "completed the endurance course under control" not in mission.explanation


def test_confirmed_recovery_can_still_complete_recommended_route():
    mission = evaluate_tutorial_outcome(
        _request(envelope="mylar", fill="auto"),
        _outcome(landed=True),
    ).mission_results[0]

    assert mission.completed
    assert mission.reward == 500
    assert "landed successfully" in mission.explanation


def test_recommended_design_cannot_pass_after_burst_even_if_it_lands():
    mission = evaluate_tutorial_outcome(
        _request(envelope="mylar", fill="auto"),
        _outcome(burst=True, landed=True),
    ).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "The balloon burst" in mission.explanation
    assert "The aircraft landed successfully" in mission.explanation


def test_safe_hot_air_flight_reports_tradeoff_without_inventing_events():
    mission = evaluate_tutorial_outcome(
        _request(gas="hot_air", envelope="mylar", fill="auto"),
        _outcome(landed=True),
    ).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "The aircraft landed successfully" in mission.explanation
    assert "Hot air offers less lift and endurance" in mission.explanation
    assert "crashed" not in mission.explanation.lower()
    assert "burst" not in mission.explanation.lower()


def test_discord_trajectory_chart_is_wrapped_in_text_code_fence():
    chart = launch_handler.chart_to_string(
        [0.0, 1.0, 2.0],
        [0.0, 10.0, 0.0],
        title="Flight Trajectory",
    )

    assert chart.startswith("```text\n")
    assert chart.endswith("\n```")
    assert "Flight Trajectory" in chart


def test_long_truncated_report_never_leaves_an_open_code_fence():
    content = "Mission details\n" + "x" * 1950 + "\n```text\nchart without room"

    safe = _safe_discord_content(content)

    assert len(safe) <= 2000
    assert safe.count("```") % 2 == 0
    assert "Trajectory omitted" in safe


def test_descending_unresolved_flight_is_not_described_as_still_climbing():
    report = launch_handler.format_discord_results(
        peak_altitude=5548.0,
        burst=False,
        landed=False,
        crashed=False,
        time_of_flight=4704.0,
        telemetry=[
            {"time": 0.0, "alt": 0.0, "vel": 3.0},
            {"time": 2000.0, "alt": 5548.0, "vel": 0.0},
            {"time": 4704.0, "alt": 4300.0, "vel": -2.0},
        ],
        gas_name="Helium",
        gas_mass=2.031,
        env_name="Latex Weather Balloon",
        payload_names="Small Quadcopter",
        site_name="Open Field",
    )

    assert "Recovery not completed" in report
    assert "passed peak altitude and was descending" in report
    assert "Still climbing slowly" not in report
