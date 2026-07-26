import json
from types import SimpleNamespace

from balloon_frontier.atmosphere_profile import (
    AtmosphereProfileRepository,
    profile_from_telemetry,
)
from balloon_frontier.weather_event import WeatherEvent


def _weather():
    return WeatherEvent(
        wind_gust_factor=1.3,
        temp_anomaly_k=-4.0,
        cloud_density=0.4,
        pressure_offset_pa=-125.0,
        storm_risk=0.1,
        name="Atmospheric River",
        description="Moist air is arriving from the Pacific.",
        flight_modifier="layered winds",
    )


def _point(altitude, *, temp, pressure, horizontal_velocity, landed=False):
    return SimpleNamespace(
        altitude_m=altitude,
        ambient_temperature_k=temp,
        ambient_pressure_pa=pressure,
        vx_mps=horizontal_velocity,
        landed=landed,
    )


def test_profile_samples_vertical_layers_and_round_trips(tmp_path):
    profile = profile_from_telemetry(
        [
            _point(0, temp=288.15, pressure=101325, horizontal_velocity=2),
            _point(1000, temp=281, pressure=90000, horizontal_velocity=5),
            _point(2200, temp=274, pressure=78000, horizontal_velocity=-3),
            _point(4500, temp=259, pressure=57000, horizontal_velocity=12),
        ],
        _weather(),
    )
    assert [layer.altitude_m for layer in profile.layers] == [0.0, 2200.0, 4500.0]
    assert profile.layers[1].horizontal_velocity_mps == -3.0

    repository = AtmosphereProfileRepository(tmp_path)
    repository.save("player", profile)
    restored = repository.get("player")
    assert restored == profile


def test_locked_weather_is_only_consumed_explicitly(tmp_path):
    repository = AtmosphereProfileRepository(tmp_path)
    repository.save(
        "player",
        profile_from_telemetry(
            [_point(0, temp=288, pressure=101325, horizontal_velocity=2)],
            _weather(),
        ),
    )
    assert repository.lock_for_next_flight("player")
    assert repository.get_locked_weather("player") == _weather()
    assert repository.get_locked_weather("player") == _weather()
    assert repository.consume_locked_weather("player") == _weather()
    assert repository.get_locked_weather("player") is None
    assert repository.consume_locked_weather("player") is None
    assert not repository.lock_for_next_flight("missing")


def test_legacy_wind_field_is_migrated_on_read(tmp_path):
    repository = AtmosphereProfileRepository(tmp_path)
    path = repository._path("legacy")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "profile": {
            "layers": [{
                "altitude_m": 1000.0,
                "temperature_k": 281.0,
                "pressure_pa": 90000.0,
                "wind_x_mps": 5.0,
            }],
            "weather": {
                "wind_gust_factor": 1.3,
                "temp_anomaly_k": -4.0,
                "cloud_density": 0.4,
                "pressure_offset_pa": -125.0,
                "storm_risk": 0.1,
                "name": "Atmospheric River",
                "description": "Moist air is arriving from the Pacific.",
                "flight_modifier": "layered winds",
            },
        },
        "locked": False,
    }))

    profile = repository.get("legacy")
    assert profile is not None
    assert profile.layers[0].horizontal_velocity_mps == 5.0
