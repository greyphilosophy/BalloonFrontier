"""Photo objectives can require staying near the target area."""

from balloon_frontier.launch_result import LaunchRequest, MissionAssignment, TelemetryPoint
from balloon_frontier.mission_evaluator import MissionEvaluator
from balloon_frontier.missions import Mission, Objective


def _point(time_s: float, altitude_m: float, x_m: float, *, landed: bool = False):
    return TelemetryPoint(
        time_s=time_s,
        altitude_m=altitude_m,
        velocity_mps=0.0,
        gas_volume_m3=1.0,
        ambient_pressure_pa=101325.0,
        ambient_temperature_k=288.15,
        net_lift_N=0.0,
        buoyancy_N=1.0,
        weight_N=1.0,
        drag_N=0.0,
        gas_mass_kg=0.1,
        total_mass_kg=1.0,
        landed=landed,
        x_m=x_m,
    )


def _evaluate(telemetry, params):
    mission = Mission(
        id="target_photo",
        title="Target Photo",
        launch_site="field",
        required_payloads=["camera", "quadcopter"],
        objectives=[Objective("capture_photo", params)],
    )
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera", "quadcopter"),
        launch_site_id="field",
    )
    evaluator = MissionEvaluator({"target_photo": mission})
    return evaluator.evaluate(
        request,
        tuple(telemetry),
        MissionAssignment(mission_ids=("target_photo",), seed=1),
    )[0]


def test_photo_succeeds_when_useful_altitude_is_reached_near_target():
    result = _evaluate(
        (
            _point(0.0, 0.0, 0.0),
            _point(10.0, 20.0, 40.0),
            _point(20.0, 0.0, 40.0, landed=True),
        ),
        {"minimum_quality": 0.0002, "max_horizontal_distance_m": 150.0},
    )

    assert result.completed is True


def test_photo_fails_when_only_useful_altitude_is_outside_target_radius():
    result = _evaluate(
        (
            _point(0.0, 0.0, 0.0),
            _point(10.0, 5.0, 40.0),
            _point(20.0, 100.0, 200.0),
            _point(30.0, 0.0, 200.0, landed=True),
        ),
        {"minimum_quality": 0.0002, "max_horizontal_distance_m": 150.0},
    )

    assert result.completed is False


def test_photo_without_radius_keeps_legacy_peak_altitude_behavior():
    result = _evaluate(
        (
            _point(0.0, 0.0, 0.0),
            _point(10.0, 100.0, 500.0),
        ),
        {"minimum_quality": 0.0002},
    )

    assert result.completed is True
