"""First-flight Story onboarding must not inject training-only weather."""

from types import SimpleNamespace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.session_adapters import SessionAwareFlightService, _PlannedFlightService


class _RewardService:
    def apply(self, *, player_id, mission_results):
        return mission_results


class _SourceService:
    default_sim_time = 1.0
    mission_sim_time = 1.0
    mission_step_interval = 1.0
    mission_evaluator = SimpleNamespace()
    reward_service = _RewardService()


def _request():
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
        player_id=None,
    )


def _capture_planned_run(monkeypatch):
    captured = {}

    def run_planned(self, request):
        captured["weather_override"] = self._weather_override
        captured["atmosphere_provider"] = self.atmosphere_provider
        return FlightOutcome(
            result=SimpleNamespace(
                telemetry=(),
                peak_altitude_m=10.0,
                duration_s=10.0,
                burst=False,
                landed=True,
                crashed=False,
            ),
            mission_results=(),
        )

    monkeypatch.setattr(_PlannedFlightService, "run", run_planned)
    return captured


def test_first_flight_story_does_not_inject_fixed_weather(monkeypatch):
    captured = _capture_planned_run(monkeypatch)
    service = SessionAwareFlightService(
        _SourceService(),
        mode=GameMode.STORY,
        ui="discord",
    )

    service.run(_request())

    assert service.last_plan is not None
    assert service.last_plan.session.mode is GameMode.STORY
    assert service.last_plan.missions == ("first_flight",)
    assert captured["weather_override"] is None
    assert captured["atmosphere_provider"] is None


def test_legacy_tutorial_alias_uses_the_same_story_weather_path(monkeypatch):
    captured = _capture_planned_run(monkeypatch)
    service = SessionAwareFlightService(
        _SourceService(),
        mode=GameMode.TUTORIAL,
        ui="discord",
    )

    service.run(_request())

    assert service.last_plan is not None
    assert service.last_plan.session.mode is GameMode.STORY
    assert captured["weather_override"] is None
    assert captured["atmosphere_provider"] is None
