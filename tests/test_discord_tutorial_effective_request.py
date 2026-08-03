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
from balloon_frontier.tutorial import evaluate_tutorial_outcome
from balloon_frontier.tutorial_catalog import TUTORIAL_ENVELOPE_ID
from balloon_frontier.tutorial_powered_flight import (
    apply_tutorial_powered_flight,
    assess_tutorial_powered_flight,
    tutorial_photo_captured,
)


class _CaptureService:
    def __init__(self):
        self.request = None

    def run(self, request):
        self.request = request
        point = TelemetryPoint(
            time_s=1.0,
            altitude_m=2.0,
            velocity_mps=1.0,
            gas_volume_m3=0.3,
            ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15,
            net_lift_N=1.0,
            buoyancy_N=3.0,
            weight_N=3.5,
            drag_N=0.0,
            gas_mass_kg=request.gas_mass_kg,
            total_mass_kg=0.36,
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


def _grounded_outcome(request, *, buoyancy_n=3.0, weight_n=3.5, burst=False, crashed=False):
    point = TelemetryPoint(
        time_s=0.0,
        altitude_m=0.0,
        velocity_mps=0.0,
        gas_volume_m3=0.3,
        ambient_pressure_pa=101325.0,
        ambient_temperature_k=288.15,
        net_lift_N=buoyancy_n - weight_n,
        buoyancy_N=buoyancy_n,
        weight_N=weight_n,
        drag_N=0.0,
        gas_mass_kg=request.gas_mass_kg,
        total_mass_kg=weight_n / 9.80665,
        burst=burst,
        landed=not crashed,
        crashed=crashed,
    )
    return FlightOutcome(result=FlightResult(telemetry=(point,), launch_request=request))


def _recommended_request():
    return LaunchRequest(
        gas_id="helium",
        envelope_id=TUTORIAL_ENVELOPE_ID,
        payload_ids=("quadcopter",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
    )


def test_recommended_assist_envelope_completes_powered_photo_sortie():
    request = _recommended_request()
    outcome = evaluate_tutorial_outcome(request, _grounded_outcome(request))

    assert outcome.result.duration_s > 0.0
    assert outcome.result.peak_altitude_m >= 30.0
    assert outcome.result.landed
    assert tutorial_photo_captured(outcome.result)
    assert outcome.mission_results[0].completed
    assert "yearbook shots" in outcome.mission_results[0].explanation
    assert "rotors carried" in outcome.mission_results[0].explanation


def test_powered_fallback_never_erases_burst_or_crash():
    request = _recommended_request()
    for original in (
        _grounded_outcome(request, burst=True),
        _grounded_outcome(request, crashed=True),
    ):
        assessment = assess_tutorial_powered_flight(request, original)
        powered = apply_tutorial_powered_flight(request, original, assessment)
        assert not assessment.eligible
        assert powered is original
        assert powered.result.burst or powered.result.crashed


def test_inadequate_buoyancy_fails_battery_budget_without_fabricated_flight():
    request = _recommended_request()
    original = _grounded_outcome(request, buoyancy_n=0.1, weight_n=4.0)
    assessment = assess_tutorial_powered_flight(request, original)
    powered = apply_tutorial_powered_flight(request, original, assessment)

    assert assessment.eligible
    assert not assessment.can_complete_route
    assert assessment.estimated_endurance_s < assessment.route_time_s
    assert powered is original

    evaluated = evaluate_tutorial_outcome(request, original)
    assert not evaluated.mission_results[0].completed
    assert "battery endurance was not sufficient" in evaluated.mission_results[0].explanation


def test_photo_altitude_hold_is_required_even_after_safe_landing():
    request = _recommended_request()
    points = (
        TelemetryPoint(
            time_s=0.0,
            altitude_m=0.0,
            velocity_mps=1.0,
            gas_volume_m3=0.3,
            ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15,
            net_lift_N=0.0,
            buoyancy_N=3.0,
            weight_N=3.5,
            drag_N=0.0,
            gas_mass_kg=request.gas_mass_kg,
            total_mass_kg=0.36,
        ),
        TelemetryPoint(
            time_s=60.0,
            altitude_m=20.0,
            velocity_mps=0.0,
            gas_volume_m3=0.3,
            ambient_pressure_pa=101100.0,
            ambient_temperature_k=288.0,
            net_lift_N=0.0,
            buoyancy_N=3.0,
            weight_N=3.5,
            drag_N=0.0,
            gas_mass_kg=request.gas_mass_kg,
            total_mass_kg=0.36,
        ),
        TelemetryPoint(
            time_s=120.0,
            altitude_m=0.0,
            velocity_mps=-0.2,
            gas_volume_m3=0.3,
            ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15,
            net_lift_N=0.0,
            buoyancy_N=3.0,
            weight_N=3.5,
            drag_N=0.0,
            gas_mass_kg=request.gas_mass_kg,
            total_mass_kg=0.36,
            landed=True,
        ),
    )
    outcome = FlightOutcome(result=FlightResult(telemetry=points, launch_request=request))
    evaluated = evaluate_tutorial_outcome(request, outcome)

    assert not tutorial_photo_captured(outcome.result)
    assert not evaluated.mission_results[0].completed
    assert evaluated.mission_results[0].reward == 0


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
