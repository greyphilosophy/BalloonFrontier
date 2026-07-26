import pytest

from balloon_frontier.atmosphere_profile import (
    AtmosphereLayer,
    AtmosphereProfile,
    AtmosphereProfileRepository,
)
from balloon_frontier.catalog import FillMode
from balloon_frontier.flight_service import FlightService
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.weather_event import WeatherEvent


def _weather():
    return WeatherEvent(
        wind_gust_factor=1.0,
        temp_anomaly_k=0.0,
        cloud_density=0.0,
        pressure_offset_pa=0.0,
        storm_risk=0.0,
        name="Recorded",
        description="A saved sounding.",
        flight_modifier="normal conditions",
    )


def test_locked_profile_drives_flight_physics_and_is_consumed(monkeypatch, tmp_path):
    repository = AtmosphereProfileRepository(tmp_path)
    profile = AtmosphereProfile(
        layers=(
            AtmosphereLayer(
                altitude_m=0.0,
                temperature_k=250.0,
                pressure_pa=70000.0,
                wind_x_mps=18.0,
                wind_y_mps=2.0,
            ),
            AtmosphereLayer(
                altitude_m=2000.0,
                temperature_k=240.0,
                pressure_pa=50000.0,
                wind_x_mps=22.0,
                wind_y_mps=4.0,
            ),
        ),
        weather=_weather(),
    )
    repository.save("player", profile)
    assert repository.lock_for_next_flight("player")
    monkeypatch.setattr(
        "balloon_frontier.atmosphere_profile.atmosphere_profiles",
        repository,
    )

    service = SessionAwareFlightService(
        FlightService(default_sim_time=0.3),
        mode=GameMode.FREE_PLAY,
        ui="cli",
    )
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=(),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
        player_id="player",
    )

    outcome = service.run(request)

    assert outcome.result.telemetry
    first = outcome.result.telemetry[0]
    assert first.ambient_temperature_k == pytest.approx(250.0, abs=0.1)
    assert first.ambient_pressure_pa == pytest.approx(70000.0, abs=50.0)
    assert first.vx_mps > 0.0
    assert repository.get_locked_profile("player") is None


def test_failed_replay_keeps_profile_locked(monkeypatch, tmp_path):
    repository = AtmosphereProfileRepository(tmp_path)
    profile = AtmosphereProfile(
        layers=(AtmosphereLayer(0.0, 250.0, 70000.0, wind_x_mps=10.0),),
        weather=_weather(),
    )
    repository.save("player", profile)
    repository.lock_for_next_flight("player")
    monkeypatch.setattr(
        "balloon_frontier.atmosphere_profile.atmosphere_profiles",
        repository,
    )

    class FailingService(FlightService):
        def prepare(self, launch_request):
            raise RuntimeError("launch failed")

    service = SessionAwareFlightService(
        FailingService(),
        mode=GameMode.FREE_PLAY,
        ui="cli",
    )
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        launch_site_id="field",
        player_id="player",
    )

    with pytest.raises(Exception, match="launch failed"):
        service.run(request)

    assert repository.get_locked_profile("player") == profile
