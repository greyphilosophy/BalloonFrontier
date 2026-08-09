"""First-flight reports use observed simulation facts and standard mission rules."""

from types import SimpleNamespace

from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.launch_result import (
    FillMode,
    LaunchRequest,
    MissionAssignment,
    TelemetryPoint,
)
from balloon_frontier.mission_evaluator import MissionEvaluator
from balloon_frontier.tutorial_report_guard import _safe_discord_content


def _mission_catalog():
    return {
        "first_flight": SimpleNamespace(
            title="Your First Flight",
            required_payloads=("camera",),
            launch_site="field",
            budget=500,
            objectives=(
                SimpleNamespace(type="recover_data", params={}),
            ),
        )
    }


def _request(*, gas="helium", payloads=("camera",)):
    return LaunchRequest(
        gas_id=gas,
        envelope_id="latex",
        fill_mode=FillMode.AUTO,
        payload_ids=payloads,
        launch_site_id="field",
    )


def _point(*, landed=False, crashed=False):
    return TelemetryPoint(
        time_s=120.0,
        altitude_m=0.0 if landed else 4300.0,
        velocity_mps=-0.2 if landed else -2.0,
        gas_volume_m3=1.0,
        ambient_pressure_pa=101325.0,
        ambient_temperature_k=288.15,
        net_lift_N=0.0,
        buoyancy_N=10.0,
        weight_N=10.0,
        drag_N=0.0,
        gas_mass_kg=1.0,
        total_mass_kg=2.0,
        landed=landed,
        crashed=crashed,
    )


def _evaluate(request, points):
    return MissionEvaluator(_mission_catalog()).evaluate(
        request,
        tuple(points),
        MissionAssignment(("first_flight",), seed=1),
    )[0]


def test_first_flight_requires_confirmed_recovery():
    mission = _evaluate(_request(), (_point(),))

    assert not mission.completed
    assert mission.reward == 0


def test_confirmed_recovery_completes_first_flight():
    mission = _evaluate(_request(), (_point(landed=True),))

    assert mission.completed
    assert mission.reward == 500


def test_crash_does_not_pass_even_if_landing_flag_is_present():
    mission = _evaluate(_request(), (_point(landed=True, crashed=True),))

    assert not mission.completed
    assert mission.reward == 0


def test_first_flight_does_not_prescribe_a_special_lifting_gas():
    mission = _evaluate(_request(gas="hot_air"), (_point(landed=True),))

    assert mission.completed
    assert mission.reward == 500


def test_missing_camera_fails_standard_required_payload_check():
    mission = _evaluate(_request(payloads=("none",)), (_point(landed=True),))

    assert not mission.completed
    assert mission.reward == 0
    assert "missing required payloads" in mission.explanation


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
        payload_names="Camera",
        site_name="Open Field",
    )

    assert "Recovery not completed" in report
    assert "passed peak altitude and was descending" in report
    assert "Still climbing slowly" not in report
