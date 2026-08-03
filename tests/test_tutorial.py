from types import SimpleNamespace

import discord

from balloon_frontier.catalog import CATALOG
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.session_adapters import (
    SessionAwareFlightService,
    _NoOpRewardService,
    _PlannedFlightService,
)
from balloon_frontier.tutorial import (
    TutorialConfiguratorMixin,
    evaluate_tutorial_outcome,
    tutorial_guidance,
)
from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options


def _outcome(*, landed=False):
    return FlightOutcome(
        result=SimpleNamespace(
            peak_altitude_m=0.0,
            duration_s=0.0,
            burst=False,
            landed=landed,
            crashed=False,
            telemetry=(),
            launch_request=None,
        )
    )


def _request(
    *,
    gas="helium",
    envelope="mylar",
    payloads=("quadcopter",),
    site="field",
    player_id=None,
):
    return LaunchRequest(
        gas_id=gas,
        envelope_id=envelope,
        payload_ids=payloads,
        launch_site_id=site,
        fill_mode=FillMode.AUTO,
        player_id=player_id,
    )


def test_quadcopter_is_the_powered_camera_aircraft():
    quadcopter = CATALOG.payload("quadcopter")
    assert quadcopter.name == "Small Quadcopter"
    assert "powered_flight" in quadcopter.capabilities
    assert "radio_control" in quadcopter.capabilities
    assert "camera" in quadcopter.capabilities


def test_discord_tutorial_exposes_quadcopter_option():
    ensure_discord_tutorial_options()
    from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS

    assert PAYLOAD_OPTIONS["quadcopter"][0] == "Small Quadcopter"


def test_party_balloon_helium_quadcopter_completes_school_photo_route():
    mission = evaluate_tutorial_outcome(_request(), _outcome()).mission_results[0]

    assert mission.completed
    assert mission.reward == 500
    assert "completed the school photo route under control" in mission.explanation
    assert "landed successfully" in mission.explanation
    assert "quadcopter supplied the remaining lift" in mission.explanation


def test_unavailable_hydrogen_route_receives_failure_debrief():
    mission = evaluate_tutorial_outcome(
        _request(gas="hydrogen"), _outcome()
    ).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "school photo route" in mission.explanation
    assert "What happened" in mission.explanation


def test_tutorial_prompts_explain_spring_break_yearbook_mission():
    gas_prompt = tutorial_guidance(0)
    aircraft_prompt = tutorial_guidance(3)
    site_prompt = tutorial_guidance(4)

    assert "spring break of senior year" in gas_prompt.lower()
    assert "yearbook" in gas_prompt.lower()
    assert "aerial photos of the school" in gas_prompt.lower()
    assert "camera-equipped quadcopter" in aircraft_prompt.lower()
    assert "school photo route" in aircraft_prompt.lower()
    assert "return safely" in site_prompt.lower()


def test_tutorial_recommended_button_is_green_and_alternatives_remain_available():
    ensure_discord_tutorial_options()
    from balloon_frontier.discord_ui.configurator import BalloonConfigurator
    from balloon_frontier.discord_ui.views import _OptionButton

    tutorial_type = type(
        "TutorialBalloonConfigurator",
        (TutorialConfiguratorMixin, BalloonConfigurator),
        {},
    )
    configurator = tutorial_type(service=SimpleNamespace())
    option_buttons = [
        item for item in configurator.children if isinstance(item, _OptionButton)
    ]

    assert len(option_buttons) > 1
    assert option_buttons[0].style is discord.ButtonStyle.success
    assert all(
        button.style is discord.ButtonStyle.primary for button in option_buttons[1:]
    )


class _RewardSpy:
    def __init__(self):
        self.calls = []

    def apply(self, *, player_id, mission_results):
        self.calls.append((player_id, mission_results))
        return mission_results


class _SourceService:
    default_sim_time = 1.0
    mission_sim_time = 1.0
    mission_step_interval = 1
    mission_evaluator = SimpleNamespace()

    def __init__(self):
        self.reward_service = _RewardSpy()


def test_planned_tutorial_flight_suppresses_premature_rewards():
    source = _SourceService()
    plan = SimpleNamespace(missions=("first_flight",))

    planned = _PlannedFlightService(source, plan, apply_rewards=False)

    assert isinstance(planned.reward_service, _NoOpRewardService)


def test_tutorial_applies_final_reward_exactly_once(monkeypatch):
    source = _SourceService()
    request = _request(player_id="player-1")

    monkeypatch.setattr(
        _PlannedFlightService,
        "run",
        lambda self, launch_request: _outcome(),
    )

    outcome = SessionAwareFlightService(
        source,
        mode=GameMode.TUTORIAL,
        ui="discord",
    ).run(request)

    assert len(source.reward_service.calls) == 1
    player_id, mission_results = source.reward_service.calls[0]
    assert player_id == "player-1"
    assert mission_results[0].completed
    assert mission_results[0].reward == 500
    assert outcome.mission_results == mission_results
