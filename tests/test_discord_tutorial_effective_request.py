"""First-flight Story onboarding must use the ordinary flight pipeline unchanged."""

from types import SimpleNamespace

from balloon_frontier.flight_service import FlightService
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import FillMode, LaunchRequest, MissionResult
from balloon_frontier.reward_service import RewardService
from balloon_frontier.session_adapters import _PlannedFlightService
from balloon_frontier.session_controller import plan_session


def _request(*, player_id=None):
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
        player_id=player_id,
    )


def test_first_flight_preparation_passes_the_standard_request_through_unchanged():
    request = _request()
    plan = plan_session(
        GameMode.STORY,
        {
            "gas": request.gas_id,
            "envelope": request.envelope_id,
            "payloads": request.payload_ids,
            "site": request.launch_site_id,
            "fill_mode": request.fill_mode.value,
        },
        player_id="first-flight-player",
        context={"ui": "discord"},
    )

    service = _PlannedFlightService(FlightService(), plan)
    preparation = service.prepare(request)

    assert plan.session.mode is GameMode.STORY
    assert plan.missions == ("first_flight",)
    assert preparation.request is request
    assert preparation.request.envelope_id == "latex"
    assert preparation.sim_state.envelope.max_volume_m3 == request.to_simulation_state().envelope.max_volume_m3
    assert preparation.mission_assignment["mission_ids"] == ["first_flight"]


def test_legacy_tutorial_mode_uses_the_same_story_plan():
    request = _request()
    story = plan_session(
        GameMode.STORY,
        {
            "gas": request.gas_id,
            "envelope": request.envelope_id,
            "payloads": request.payload_ids,
            "site": request.launch_site_id,
            "fill_mode": request.fill_mode.value,
        },
        player_id="player",
        context={"ui": "discord"},
    )
    legacy = plan_session(
        GameMode.TUTORIAL,
        {
            "gas": request.gas_id,
            "envelope": request.envelope_id,
            "payloads": request.payload_ids,
            "site": request.launch_site_id,
            "fill_mode": request.fill_mode.value,
        },
        player_id="player",
        context={"ui": "discord"},
    )

    assert legacy.session.mode is GameMode.STORY
    assert legacy.policy == story.policy
    assert legacy.missions == story.missions == ("first_flight",)


def test_first_flight_uses_standard_reward_idempotency():
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
            raise AssertionError("A completed Story mission must not reward twice")

    mission = MissionResult(
        mission_id="first_flight",
        completed=True,
        reward=500,
        explanation="Mission Your First Flight completed!",
    )

    result = RewardService(_Repository()).apply("player", (mission,))[0]

    assert result.completed
    assert result.reward == 0
    assert "Mission Your First Flight completed" in result.explanation
    assert "Mission completed previously" in result.explanation
