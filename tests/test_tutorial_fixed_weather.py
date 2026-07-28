"""Regression tests for deterministic, surprise-free tutorial weather."""

from types import SimpleNamespace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.session_adapters import (
    SessionAwareFlightService,
    TUTORIAL_WEATHER,
    _PlannedFlightService,
)
from balloon_frontier.weather_event import weather_impact_on_flight


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
        envelope_id="mylar",
        payload_ids=("quadcopter",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
        player_id="tutorial-weather-player",
    )


def test_tutorial_weather_is_calm_and_has_no_storm_risk():
    assert TUTORIAL_WEATHER.name == "Calm Tutorial Conditions"
    assert TUTORIAL_WEATHER.wind_gust_factor == 0.7
    assert TUTORIAL_WEATHER.temp_anomaly_k == 0.0
    assert TUTORIAL_WEATHER.cloud_density == 0.0
    assert TUTORIAL_WEATHER.pressure_offset_pa == 0.0
    assert TUTORIAL_WEATHER.storm_risk == 0.0

    impacts = weather_impact_on_flight(TUTORIAL_WEATHER)
    assert impacts["burst_risk"] == 1.0
    assert impacts["thermal_efficiency"] == 1.0
    assert impacts["pressure_modifier"] == 1.0


def test_tutorial_session_always_injects_fixed_weather(monkeypatch):
    captured = {}

    def run_planned(self, request):
        captured["weather"] = self._weather_override
        captured["impacts"] = weather_impact_on_flight(self._weather_override)
        return FlightOutcome(
            result=SimpleNamespace(
                peak_altitude_m=10.0,
                duration_s=10.0,
                burst=False,
                landed=True,
                crashed=False,
            )
        )

    monkeypatch.setattr(_PlannedFlightService, "run", run_planned)

    service = SessionAwareFlightService(
        _SourceService(),
        mode=GameMode.TUTORIAL,
        ui="discord",
    )
    service.run(_request())

    assert captured["weather"] is TUTORIAL_WEATHER
    assert captured["impacts"]["burst_risk"] == 1.0
    assert captured["impacts"]["pressure_modifier"] == 1.0
