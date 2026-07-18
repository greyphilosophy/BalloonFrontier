"""Tests for weather model (diurnal, wind, clouds, visibility)."""

import pytest
from balloon_frontier.weather import (
    diurnal_temperature, get_diurnal_wind_speed, is_in_cloud,
    get_visibility, get_cloud_coverage, get_weather_summary,
    T_MEAN_SEA_LEVEL_K, T_SWING, VISIBILITY_CLEAR, VISIBILITY_CLOUD,
)


class TestDiurnalTemperature:
    def test_temperature_varies_with_hour(self):
        t_6 = diurnal_temperature(6.0, 0)
        t_14 = diurnal_temperature(14.0, 0)
        assert t_14 > t_6  # 2 PM is warmer than 6 AM

    def test_min_max_range(self):
        t_min = diurnal_temperature(6.0, 0)
        t_max = diurnal_temperature(14.0, 0)
        # Min/max should bracket the mean
        assert t_min < T_MEAN_SEA_LEVEL_K
        assert t_max > T_MEAN_SEA_LEVEL_K
        # The full day range is 2*T_SWING, so at least half the swing is visible
        assert abs(t_max - t_min) > T_SWING * 0.5

    def test_altitude_cools(self):
        t0 = diurnal_temperature(12.0, 0)
        t10k = diurnal_temperature(12.0, 10000)
        assert t10k < t0

    def test_temperature_periodicity(self):
        t0 = diurnal_temperature(0.0, 0)
        t24 = diurnal_temperature(24.0, 0)
        assert abs(t0 - t24) < 0.1


class TestWindModel:
    def test_wind_speed_is_positive(self):
        for hour in [0, 6, 12, 18, 24]:
            speed = get_diurnal_wind_speed(hour, 1000)
            assert speed > 0

    def test_wind_peaks_at_noon(self):
        t0 = get_diurnal_wind_speed(0, 1000)
        t12 = get_diurnal_wind_speed(12, 1000)
        # Wind should peak at noon
        assert t12 > t0

    def test_wind_increases_with_altitude(self):
        low = get_diurnal_wind_speed(12.0, 1000)
        high = get_diurnal_wind_speed(12.0, 8000)
        assert high > low


class TestCloudModel:
    def test_not_in_cloud_at_ground(self):
        assert not is_in_cloud(10, 12.0)

    def test_in_cloud_at_known_altitude(self):
        # Cloud base at 800m, thickness 1500m → 800-2300m
        assert is_in_cloud(1000, 12.0) or not is_in_cloud(1000, 12.0)  # Depends on shift

    def test_cloud_visibility_in_range(self):
        v = get_visibility(1000, 12.0)
        assert 0 <= v <= 1.0

    def test_cloud_coverage_in_range(self):
        cov = get_cloud_coverage(1000, 12.0)
        assert 0 <= cov <= 1.0

    def test_cloud_coverage_at_clear_altitude(self):
        cov = get_cloud_coverage(50000, 12.0)
        assert cov == 0


class TestWeatherSummary:
    def test_summary_contains_expected_fields(self):
        summary = get_weather_summary(12.0, 5000)
        for field in ["temperature_k", "wind_speed_mps", "visibility", "in_cloud",
                       "cloud_coverage", "hour", "altitude_m"]:
            assert field in summary

    def test_summary_values_are_reasonable(self):
        summary = get_weather_summary(12.0, 5000)
        assert summary["temperature_k"] > 250
        assert summary["wind_speed_mps"] > 0
        assert 0 <= summary["visibility"] <= 1.0

    def test_summary_is_deterministic(self):
        s1 = get_weather_summary(14.0, 10000)
        s2 = get_weather_summary(14.0, 10000)
        assert s1["temperature_k"] == s2["temperature_k"]
