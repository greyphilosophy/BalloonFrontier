import math

import pytest

from balloon_frontier.weather_column import generate_weather_column


def test_column_generation_is_deterministic():
    first = generate_weather_column(42, "frontal")
    second = generate_weather_column(42, "frontal")

    assert first == second
    assert first.sample(5500.0) == second.sample(5500.0)


def test_column_samples_are_physically_valid_and_smooth():
    column = generate_weather_column(7, "atmospheric_river")

    below = column.sample(2999.0)
    above = column.sample(3001.0)

    assert below.temperature_k > 0.0
    assert below.pressure_pa > 0.0
    assert above.temperature_k > 0.0
    assert above.pressure_pa > 0.0
    assert abs(above.wind_x_mps - below.wind_x_mps) < 1.0
    assert abs(above.wind_y_mps - below.wind_y_mps) < 1.0


def test_jet_stream_has_a_stronger_tropopause_core_than_surface_wind():
    column = generate_weather_column(18, "jet_stream")

    surface = column.sample(0.0)
    core = column.sample(12000.0)
    surface_speed = math.hypot(surface.wind_x_mps, surface.wind_y_mps)
    core_speed = math.hypot(core.wind_x_mps, core.wind_y_mps)

    assert core_speed > surface_speed + 20.0


def test_pressure_anomaly_tapers_toward_standard_atmosphere():
    column = generate_weather_column(3, "calm")

    surface_ratio = column.layers[0].pressure_multiplier
    upper_ratio = column.layers[-1].pressure_multiplier

    assert abs(upper_ratio - 1.0) < abs(surface_ratio - 1.0)


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="unknown weather-column scenario"):
        generate_weather_column(1, "tornado_planet")


def test_samples_clamp_to_generated_column_bounds():
    column = generate_weather_column(9, "calm")

    assert column.sample(-100.0).altitude_m == 0.0
    assert column.sample(column.ceiling_m + 1000.0).altitude_m == column.ceiling_m
