import json
from types import SimpleNamespace

import pytest

from balloon_frontier.atmosphere_profile import (
    AtmosphereLayer,
    AtmosphereProfile,
    AtmosphereProfileRepository,
    RecordedAtmosphereProvider,
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


def _point(
    altitude,
    *,
    temp,
    pressure,
    horizontal_velocity,
    wind_x=0.0,
    wind_y=0.0,
    landed=False,
):
    return SimpleNamespace(
        altitude_m=altitude,
        ambient_temperature_k=temp,
        ambient_pressure_pa=pressure,
        ambient_wind_x_mps=wind_x,
        ambient_wind_y_mps=wind_y,
        vx_mps=horizontal_velocity,
        landed=landed,
    )


def test_profile_samples_vertical_layers_and_round_trips(tmp_path):
    profile = profile_from_telemetry(
        [
            _point(0, temp=288.15, pressure=101325, horizontal_velocity=2, wind_x=1, wind_y=2),
            _point(1000, temp=281, pressure=90000, horizontal_velocity=5, wind_x=3, wind_y=4),
            _point(2200, temp=274, pressure=78000, horizontal_velocity=-3, wind_x=-5, wind_y=6),
            _point(4500, temp=259, pressure=57000, horizontal_velocity=12, wind_x=7, wind_y=-8),
        ],
        _weather(),
    )
    assert [layer.altitude_m for layer in profile.layers] == [0.0, 2200.0, 4500.0]
    assert profile.layers[1].horizontal_velocity_mps == -3.0
    assert profile.layers[1].wind_x_mps == -5.0
    assert profile.layers[1].wind_y_mps == 6.0

    repository = AtmosphereProfileRepository(tmp_path)
    repository.save("player", profile)
    restored = repository.get("player")
    assert restored == profile


def test_recorded_provider_interpolates_between_layers_and_clamps_edges():
    profile = AtmosphereProfile(
        layers=(
            AtmosphereLayer(0.0, 288.0, 100000.0, wind_x_mps=2.0, wind_y_mps=-2.0),
            AtmosphereLayer(2000.0, 268.0, 80000.0, wind_x_mps=10.0, wind_y_mps=6.0),
        ),
        weather=_weather(),
    )
    provider = RecordedAtmosphereProvider(profile)

    midpoint = provider.sample(1000.0)
    assert midpoint.temperature_k == 278.0
    assert midpoint.pressure_pa == 90000.0
    assert midpoint.wind_x_mps == 6.0
    assert midpoint.wind_y_mps == 2.0

    below = provider.sample(-100.0)
    above = provider.sample(5000.0)
    assert below.altitude_m == 0.0
    assert below.temperature_k == 288.0
    assert above.altitude_m == 5000.0
    assert above.temperature_k == 268.0
    assert above.wind_x_mps == 10.0


def test_recorded_provider_rejects_empty_and_profile_rejects_duplicate_altitudes():
    empty = AtmosphereProfile((), _weather())
    with pytest.raises(ValueError, match="at least one layer"):
        RecordedAtmosphereProvider(empty)

    with pytest.raises(ValueError, match="strictly ascending"):
        AtmosphereProfile(
            (
                AtmosphereLayer(1000.0, 280.0, 90000.0),
                AtmosphereLayer(1000.0, 279.0, 89000.0),
            ),
            _weather(),
        )


def test_locked_profile_is_only_consumed_explicitly(tmp_path):
    repository = AtmosphereProfileRepository(tmp_path)
    profile = profile_from_telemetry(
        [_point(0, temp=288, pressure=101325, horizontal_velocity=2, wind_x=3)],
        _weather(),
    )
    repository.save("player", profile)

    assert repository.lock_for_next_flight("player")
    assert repository.get_locked_profile("player") == profile
    assert repository.get_locked_weather("player") == _weather()
    assert repository.get_locked_profile("player") == profile
    assert repository.consume_locked_profile("player") == profile
    assert repository.get_locked_profile("player") is None
    assert repository.consume_locked_weather("player") is None
    assert not repository.lock_for_next_flight("missing")


def test_legacy_wind_field_is_preserved_as_vehicle_motion_not_ambient_wind(tmp_path):
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
    assert profile.layers[0].wind_x_mps == 0.0
