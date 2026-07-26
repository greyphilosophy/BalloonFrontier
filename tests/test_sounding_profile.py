from types import SimpleNamespace

import pytest

from balloon_frontier.sounding_profile import record_sounding_profile
from balloon_frontier.weather_column import generate_weather_column
from balloon_frontier.weather_event import WeatherEvent


def _weather():
    return WeatherEvent(1.0, 0.0, 0.0, 0.0, 0.0, "Sounding", "", "normal")


def _point(altitude_m, time_s, vx_mps=0.0):
    return SimpleNamespace(
        altitude_m=altitude_m,
        time_s=time_s,
        vx_mps=vx_mps,
        landed=False,
    )


def test_records_regular_layers_and_exact_ceiling():
    profile = record_sounding_profile(
        (_point(0.0, 0.0), _point(1250.0, 250.0, 7.0)),
        _weather(),
        generate_weather_column(4, "frontal"),
        vertical_resolution_m=500.0,
    )

    assert [layer.altitude_m for layer in profile.layers] == [0.0, 500.0, 1000.0, 1250.0]
    assert profile.wind_measurements_available


def test_profile_samples_the_actual_provider():
    provider = generate_weather_column(8, "jet_stream")
    profile = record_sounding_profile(
        (_point(0.0, 0.0), _point(2000.0, 400.0)),
        _weather(),
        provider,
        vertical_resolution_m=1000.0,
    )

    expected = provider.sample(1000.0)
    middle = profile.layers[1]
    assert middle.temperature_k == pytest.approx(expected.temperature_k, abs=0.01)
    assert middle.pressure_pa == pytest.approx(expected.pressure_pa, abs=0.1)
    assert middle.wind_x_mps == pytest.approx(expected.wind_x_mps, abs=0.01)
    assert middle.wind_y_mps == pytest.approx(expected.wind_y_mps, abs=0.01)


def test_empty_telemetry_produces_empty_replayable_profile():
    profile = record_sounding_profile((), _weather(), generate_weather_column(1, "calm"))

    assert profile.layers == ()
    assert profile.wind_measurements_available


def test_invalid_resolution_is_rejected():
    with pytest.raises(ValueError, match="vertical_resolution_m"):
        record_sounding_profile(
            (_point(0.0, 0.0),),
            _weather(),
            generate_weather_column(1, "calm"),
            vertical_resolution_m=0.0,
        )
