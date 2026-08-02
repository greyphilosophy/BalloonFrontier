"""Discord tutorial launches must simulate and report one coherent request."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.flight_service import FlightOutcome, FlightService
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import (
    FillMode,
    FlightResult,
    LaunchRequest,
    MissionResult,
    TelemetryPoint,
)
from balloon_frontier.reward_service import RewardService
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.tutorial_catalog import TUTORIAL_ENVELOPE_ID


class _CaptureService:
    def __init__(self):
        self.request = None

    def run(self, request):
        self.request = request
        point = TelemetryPoint(
            time_s=1.0,
            altitude_m=2.0,
            velocity_mps=1.0,
            gas_volume_m3=0.4,
            ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15,
            net_lift_N=1.0,
            buoyancy_N=4.0,
            weight_N=3.0,
            drag_N=0.0,
            gas_mass_kg=request.gas_mass_kg,
            total_mass_kg=0.37,
            landed=True,
        )
        return FlightOutcome(
            result=FlightResult(telemetry=(point,), launch_request=request),
            mission_results=(
                MissionResult(
                    mission_id="first_flight",
                    completed=True,
                    reward=500,
                    explanation="The aircraft landed successfully.",
                ),
            ),
        )


def test_discord_launch_uses_and_reports_the_effective_tutorial_envelope():
    service = _CaptureService()
    configurator = SimpleNamespace(
        state={
            "gas": "helium",
            "envelope": "mylar",
            "fill_mode": "auto",
            "payloads": ["quadcopter"],
            "site": "field",
            "manual_gas_mass": None,
            "gas_mass": 33.856,
        },
        _game_entry_context={"mode": GameMode.TUTORIAL},
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id="tutorial-player"),
        response=SimpleNamespace(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
    )

    asyncio.run(launch_handler.run_launch(configurator, interaction, service))

    assert service.request is not None
    assert service.request.envelope_id == TUTORIAL_ENVELOPE_ID
    assert service.request.gas_mass_kg < 0.1
    assert configurator.state["envelope"] == "mylar"
    assert configurator.state["gas_mass"] == service.request.gas_mass_kg

    rendered = interaction.edit_original_response.await_args.kwargs["content"]
    assert "Envelope: Foil Party Balloon" in rendered
    assert "Scientific Film Balloon" not in rendered
    assert "Mass: 33.856kg" not in rendered


def test_recommended_assist_envelope_does_not_end_at_zero_seconds():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id=TUTORIAL_ENVELOPE_ID,
        payload_ids=("quadcopter",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
    )
    service = SessionAwareFlightService(
        FlightService(
            default_sim_time=30.0,
            mission_sim_time=30.0,
            mission_step_interval=1.0,
        ),
        mode=GameMode.TUTORIAL,
        ui="discord",
    )

    outcome = service.run(request)

    assert outcome.result.duration_s > 0.0
    assert outcome.result.peak_altitude_m > 0.0
    assert outcome.result.launch_request.envelope_id == TUTORIAL_ENVELOPE_ID


class _Repository:
    def __init__(self):
        self.player = SimpleNamespace(
            budget=0,
            reputation=0,
            missions_completed=["first_flight"],
        )

    def get(self, player_id):
        return self.player

    def save(self, player):
        raise AssertionError("A replay must not persist another reward")


def test_replay_keeps_real_debrief_and_appends_no_reward_notice():
    mission = MissionResult(
        mission_id="first_flight",
        completed=True,
        reward=500,
        explanation="**What happened**\n- The aircraft landed successfully.",
    )

    result = RewardService(_Repository()).apply("player", (mission,))[0]

    assert result.completed
    assert result.reward == 0
    assert "The aircraft landed successfully" in result.explanation
    assert "Mission completed previously" in result.explanation
