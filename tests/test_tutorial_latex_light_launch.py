"""Regression coverage for the Discord tutorial latex/light launch."""

from balloon_frontier.flight_service import FlightService
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.session_adapters import SessionAwareFlightService


def test_tutorial_latex_light_quadcopter_launch_returns_outcome():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("quadcopter",),
        launch_site_id="field",
        fill_mode=FillMode.LIGHT,
        player_id=None,
    )
    service = SessionAwareFlightService(
        FlightService(
            default_sim_time=150.0,
            mission_sim_time=43200.0,
            mission_step_interval=1.0,
        ),
        mode=GameMode.TUTORIAL,
        ui="discord",
    )

    outcome = service.run(request)

    assert outcome.result.telemetry
    assert outcome.result.launch_request is request
    assert any(result.mission_id == "first_flight" for result in outcome.mission_results)
