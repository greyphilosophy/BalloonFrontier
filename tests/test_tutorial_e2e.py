"""End-to-end coverage for the guided Discord tutorial journey."""

import asyncio
from itertools import product
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui.configurator import BalloonConfigurator, _Step
from balloon_frontier.discord_ui.modals import _LaunchButton
from balloon_frontier.discord_ui.views import _OptionButton
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import (
    FillMode,
    FlightResult,
    LaunchRequest,
    TelemetryPoint,
)
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.session_adapters import (
    SessionAwareFlightService,
    _PlannedFlightService,
)
from balloon_frontier.tutorial import (
    TUTORIAL_OPTION_KEYS,
    TutorialConfiguratorMixin,
    evaluate_tutorial_outcome,
)
from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options


class _Interaction:
    def __init__(self, user_id="tutorial-player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(author=self.user)
        self.response = SimpleNamespace(
            defer=AsyncMock(),
            edit_message=AsyncMock(),
            send_message=AsyncMock(),
        )
        self.edit_original_response = AsyncMock()


def _tutorial_configurator(service=None):
    ensure_discord_tutorial_options()
    tutorial_type = type(
        "TutorialBalloonConfigurator",
        (TutorialConfiguratorMixin, BalloonConfigurator),
        {},
    )
    return tutorial_type(service=service or SimpleNamespace())


def _outcome(*, burst=False, landed=False, crashed=False):
    return FlightOutcome(
        result=SimpleNamespace(
            peak_altitude_m=125.0,
            duration_s=60.0,
            burst=burst,
            landed=landed,
            crashed=crashed,
        )
    )


def _request_from(configurator, player_id="tutorial-player"):
    state = configurator.state
    return LaunchRequest(
        gas_id=state["gas"],
        envelope_id=state["envelope"],
        payload_ids=tuple(state["payloads"]),
        launch_site_id=state["site"],
        fill_mode=FillMode(state["fill_mode"]),
        manual_gas_mass_kg=state["manual_gas_mass"],
        player_id=player_id,
    )


async def _drive_tutorial_route(configurator, interaction, *, gas_index):
    await configurator._on_gas(interaction, gas_index)
    await configurator._on_envelope(interaction, 1)
    await configurator._on_fill(interaction, 1)
    await configurator._on_payload(interaction, 1)
    await configurator._advance(interaction)
    await configurator._on_site(interaction, 1)


def _option_buttons(configurator):
    return [
        item for item in configurator.children if isinstance(item, _OptionButton)
    ]


def test_tutorial_hides_unavailable_choices(monkeypatch):
    new_player = PlayerState("tutorial-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: new_player),
    )
    configurator = _tutorial_configurator()

    gas_content = configurator._step_content()
    assert "Helium" in gas_content
    assert "Hot Air" in gas_content
    assert "Hydrogen" not in gas_content
    assert "Methane" not in gas_content
    assert len(_option_buttons(configurator)) == 2

    configurator._current_step = _Step.CHOOSE_ENVELOPE
    configurator.build_buttons()
    envelope_content = configurator._step_content()
    assert "Foil Party Balloon" in envelope_content
    assert "Scientific Film Balloon" not in envelope_content
    assert "Latex Weather Balloon" in envelope_content
    assert "Zero-Pressure" not in envelope_content
    assert "Blimp" not in envelope_content
    assert len(_option_buttons(configurator)) == 2

    configurator._current_step = _Step.CHOOSE_PAYLOADS
    configurator.build_buttons()
    payload_content = configurator._step_content()
    assert "Small Quadcopter" in payload_content
    assert "None" in payload_content
    assert "Camera" not in payload_content
    assert "Pressure Valve" not in payload_content
    assert len(_option_buttons(configurator)) == 2

    configurator._current_step = _Step.CHOOSE_SITE
    configurator.build_buttons()
    site_content = configurator._step_content()
    assert "Open Field" in site_content
    assert "Mountain Ridge" not in site_content
    assert "Urban Rooftop" not in site_content
    assert len(_option_buttons(configurator)) == 1


def test_every_visible_tutorial_configuration_has_an_educational_debrief():
    gases = TUTORIAL_OPTION_KEYS[_Step.CHOOSE_GAS]
    envelopes = TUTORIAL_OPTION_KEYS[_Step.CHOOSE_ENVELOPE]
    fills = TUTORIAL_OPTION_KEYS[_Step.CHOOSE_FILL]
    payloads = TUTORIAL_OPTION_KEYS[_Step.CHOOSE_PAYLOADS]
    sites = TUTORIAL_OPTION_KEYS[_Step.CHOOSE_SITE]

    combinations = list(product(gases, envelopes, fills, payloads, sites))
    assert len(combinations) == 40

    for gas, envelope, fill, payload, site in combinations:
        request = SimpleNamespace(
            gas_id=gas,
            envelope_id=envelope,
            fill_mode=SimpleNamespace(value=fill),
            payload_ids=(payload,),
            launch_site_id=site,
            balloon_count=1,
        )
        mission = evaluate_tutorial_outcome(
            request,
            _outcome(landed=True),
        ).mission_results[0]
        assert "**What happened**" in mission.explanation
        assert "**Why**" in mission.explanation
        assert "**Try next**" in mission.explanation
        assert "Peak altitude 125 m" in mission.explanation
        assert "landed successfully" in mission.explanation
        assert mission.completed == (
            gas == "helium"
            and envelope == "mylar"
            and fill in {"auto", "normal"}
            and payload == "quadcopter"
            and site == "field"
        )


def test_recommended_design_fails_if_observed_flight_bursts_or_crashes():
    request = SimpleNamespace(
        gas_id="helium",
        envelope_id="mylar",
        fill_mode=SimpleNamespace(value="auto"),
        payload_ids=("quadcopter",),
        launch_site_id="field",
        balloon_count=1,
    )

    for outcome in (
        _outcome(burst=True, landed=True),
        _outcome(crashed=True),
    ):
        mission = evaluate_tutorial_outcome(request, outcome).mission_results[0]
        assert not mission.completed
        assert mission.reward == 0
        assert "did not complete the endurance course safely" in mission.explanation


def test_debrief_reports_observed_events_and_all_design_risks():
    request = SimpleNamespace(
        gas_id="hot_air",
        envelope_id="latex",
        fill_mode=SimpleNamespace(value="heavy"),
        payload_ids=("none",),
        launch_site_id="field",
        balloon_count=4,
    )
    mission = evaluate_tutorial_outcome(
        request,
        _outcome(burst=True, crashed=True),
    ).mission_results[0]
    text = mission.explanation
    assert "The balloon burst" in text
    assert "aircraft crashed" in text
    assert "Hot air offers less lift" in text
    assert "Latex is flexible" in text
    assert "Without the quadcopter" in text
    assert "Heavy fill" in text
    assert "More than three balloons" in text
    assert len(text) < 1200


def test_new_player_can_complete_recommended_tutorial_route(monkeypatch):
    new_player = PlayerState("tutorial-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: new_player),
    )
    configurator = _tutorial_configurator()
    interaction = _Interaction()

    assert configurator._current_step == _Step.CHOOSE_GAS
    asyncio.run(_drive_tutorial_route(configurator, interaction, gas_index=1))
    assert configurator._current_step == _Step.REVIEW_LAUNCH
    assert configurator.state["gas"] == "helium"
    assert configurator.state["envelope"] == "mylar"
    assert configurator.state["payloads"] == ["quadcopter"]
    assert configurator.state["site"] == "field"
    assert "Review and launch" in configurator._step_content()

    mission = evaluate_tutorial_outcome(
        _request_from(configurator),
        _outcome(landed=True),
    ).mission_results[0]
    assert mission.completed
    assert mission.reward == 500
    assert "completed the endurance course under control" in mission.explanation
    assert "**What happened**" in mission.explanation
    interaction.response.send_message.assert_not_awaited()


def test_tutorial_alternative_route_explains_hot_air_risk(monkeypatch):
    new_player = PlayerState("tutorial-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: new_player),
    )
    configurator = _tutorial_configurator()
    interaction = _Interaction()
    asyncio.run(_drive_tutorial_route(configurator, interaction, gas_index=2))

    mission = evaluate_tutorial_outcome(
        _request_from(configurator),
        _outcome(),
    ).mission_results[0]
    assert configurator.state["gas"] == "hot_air"
    assert not mission.completed
    assert mission.reward == 0
    assert "Hot air offers less lift and endurance" in mission.explanation
    assert "Use helium" in mission.explanation


class _RewardSpy:
    def __init__(self):
        self.calls = []

    def apply(self, *, player_id, mission_results):
        self.calls.append((player_id, mission_results))
        return mission_results


class _SourceService:
    default_sim_time = 1.0
    mission_sim_time = 1.0
    mission_step_interval = 1.0
    mission_evaluator = SimpleNamespace()

    def __init__(self):
        self.reward_service = _RewardSpy()


def _flight_outcome(request):
    telemetry = (
        TelemetryPoint(
            time_s=1.0,
            altitude_m=25.0,
            velocity_mps=1.0,
            gas_volume_m3=1.0,
            ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15,
            net_lift_N=1.0,
            buoyancy_N=10.0,
            weight_N=9.0,
            drag_N=0.0,
            gas_mass_kg=request.gas_mass_kg,
            total_mass_kg=1.0,
            landed=True,
        ),
    )
    return FlightOutcome(
        result=FlightResult(telemetry=telemetry, launch_request=request),
        score=75.0,
        medal_name="NONE",
        medal_emoji="⚪",
    )


def test_recommended_route_launch_button_applies_reward_and_renders(monkeypatch):
    new_player = PlayerState("launch-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: new_player),
    )
    captured = {}

    def run_planned(service, request):
        captured["request"] = request
        return _flight_outcome(request)

    monkeypatch.setattr(_PlannedFlightService, "run", run_planned)
    source = _SourceService()
    service = SessionAwareFlightService(
        source,
        mode=GameMode.TUTORIAL,
        ui="discord",
    )
    configurator = _tutorial_configurator(service=service)
    interaction = _Interaction(user_id="launch-player")
    asyncio.run(_drive_tutorial_route(configurator, interaction, gas_index=1))

    launch_buttons = [
        item for item in configurator.children if isinstance(item, _LaunchButton)
    ]
    assert len(launch_buttons) == 1
    asyncio.run(launch_buttons[0].callback(interaction))

    request = captured["request"]
    assert request.gas_id == "helium"
    assert request.envelope_id == "mylar"
    assert request.payload_ids == ("quadcopter",)
    assert request.launch_site_id == "field"
    assert request.player_id == "launch-player"

    assert len(source.reward_service.calls) == 1
    rewarded_player, mission_results = source.reward_service.calls[0]
    assert rewarded_player == "launch-player"
    assert mission_results[0].completed
    assert mission_results[0].reward == 500

    interaction.response.defer.assert_awaited_once_with(
        thinking=True,
        ephemeral=False,
    )
    interaction.edit_original_response.assert_awaited_once()
    rendered = interaction.edit_original_response.await_args.kwargs
    content = rendered["content"]
    assert rendered["view"] is None
    assert len(content) <= 2000
    assert "Mission Results" in content
    assert "first_flight" in content
    assert "+500 credits" in content
    assert "What happened" in content
    assert "Why" in content
    assert "Try next" in content
