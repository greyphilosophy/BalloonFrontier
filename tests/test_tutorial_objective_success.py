"""The tutorial succeeds by completing the school-photo objective, not by matching presets."""

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import (
    FillMode,
    FlightResult,
    LaunchRequest,
    TelemetryPoint,
)
from balloon_frontier.tutorial import evaluate_tutorial_outcome
from balloon_frontier.tutorial_catalog import TUTORIAL_ENVELOPE_ID


def _photo_route(request):
    common = dict(
        gas_volume_m3=0.30,
        ambient_pressure_pa=101325.0,
        ambient_temperature_k=288.15,
        net_lift_N=0.0,
        buoyancy_N=3.0,
        weight_N=3.5,
        drag_N=0.0,
        gas_mass_kg=request.gas_mass_kg,
        total_mass_kg=0.36,
    )
    points = (
        TelemetryPoint(time_s=0.0, altitude_m=0.0, velocity_mps=0.0, **common),
        TelemetryPoint(time_s=45.0, altitude_m=32.0, velocity_mps=0.5, **common),
        TelemetryPoint(time_s=105.0, altitude_m=35.0, velocity_mps=0.0, **common),
        TelemetryPoint(
            time_s=190.0,
            altitude_m=0.0,
            velocity_mps=-0.3,
            landed=True,
            **common,
        ),
    )
    return FlightOutcome(result=FlightResult(telemetry=points, launch_request=request))


def test_alternative_configuration_can_succeed_when_it_takes_photos_and_recovers():
    request = LaunchRequest(
        gas_id="hot_air",
        envelope_id=TUTORIAL_ENVELOPE_ID,
        payload_ids=("quadcopter",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
    )

    mission = evaluate_tutorial_outcome(request, _photo_route(request)).mission_results[0]

    assert mission.completed
    assert mission.reward == 500
    assert "captured the yearbook shots" in mission.explanation
    assert "completed the school photo route" in mission.explanation


def test_photo_altitude_without_camera_quadcopter_does_not_complete_mission():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id=TUTORIAL_ENVELOPE_ID,
        payload_ids=("none",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
    )

    mission = evaluate_tutorial_outcome(request, _photo_route(request)).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
