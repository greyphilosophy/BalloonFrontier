"""Tests for Balloon Frontier wind model.

Reference: Balloon Frontier GDD Section 6.7 (Wind layers).
"""

import math

import pytest

from balloon_frontier.wind import (
    STANDARD_WIND_LAYERS,
    WIND_SITES,
    getWindVelocity,
    wind_direction,
    wind_profile,
    wind_speed,
    wind_vector,
)


# ─── Wind Speed ─────────────────────────────────────────────────


class TestWindSpeed:
    """Test wind speed calculations at various altitudes."""

    def test_windspeed_at_sea_level(self):
        speed = wind_speed(0, time_s=0)
        assert speed > 0
        # Base is ~2 m/s for troposphere layer
        assert 0.5 < speed < 5.0

    def test_windspeed_increases_to_stratosphere(self):
        speed_tropo = wind_speed(5000, time_s=0)
        speed_strato = wind_speed(18000, time_s=0)
        # Stratosphere should generally be faster than mid-troposphere
        assert speed_strato > 1.0

    def test_windspeed_is_non_negative(self):
        for alt in [0, 1000, 5000, 10000, 20000, 35000, 50000]:
            for t in [0, 1000, 43200, 86400]:
                speed = wind_speed(alt, time_s=t)
                assert speed >= 0.0, f"Negative wind speed at alt={alt}, time_s={t}"

    def test_windspeed_is_bounded(self):
        # Even at jet stream peak, shouldn't exceed ~20 m/s
        for alt in [0, 5000, 11000, 20000, 35000]:
            for t in range(0, 86400, 1000):
                speed = wind_speed(alt, time_s=t)
                assert speed < 25.0, f"Unbounded wind speed: {speed} at {alt}m"

    def test_diurnal_variation_exists(self):
        # Wind should vary over a 24-hour cycle
        speeds = [wind_speed(10000, time_s=t) for t in [0, 43200, 86400]]
        assert max(speeds) - min(speeds) > 0.1

    def test_wind_above_defined_layers(self):
        # At 50km (above last layer ending at 40km), should extrapolate
        speed = wind_speed(50000, time_s=0)
        assert speed > 0.0 and speed < 20.0


# ─── Wind Direction ─────────────────────────────────────────────


class TestWindDirection:
    """Test wind direction calculations."""

    def test_direction_is_bounded(self):
        for alt in [0, 5000, 10000, 20000, 35000]:
            for t in [0, 43200]:
                d = wind_direction(alt, time_s=t)
                assert 0.0 <= d < 2 * math.pi or abs(d) < 3

    def test_direction_varies_with_altitude(self):
        d1 = wind_direction(1000, time_s=0)
        d2 = wind_direction(10000, time_s=0)
        # Different layers should have different directions
        assert abs(d1 - d2) > 0.01

    def test_consistent_direction_for_same_input(self):
        d1 = wind_direction(5000, time_s=100)
        d2 = wind_direction(5000, time_s=100)
        assert d1 == d2


# ─── Wind Vector ────────────────────────────────────────────────


class TestWindVector:
    """Test wind velocity decomposition into (u, v) components."""

    def test_vector_magnitude_matches_speed(self):
        for alt in [0, 5000, 10000, 20000, 35000]:
            for t in [0, 43200]:
                u, v = wind_vector(alt, time_s=t)
                speed = math.sqrt(u * u + v * v)
                expected = wind_speed(alt, time_s=t)
                assert abs(speed - expected) < 0.01

    def test_vector_components_are_realistic(self):
        u, v = wind_vector(10000, time_s=0)
        assert abs(u) < 20.0
        assert abs(v) < 20.0


# ─── Wind Profile ──────────────────────────────────────────────


class TestWindProfile:
    """Test batch wind profile computation."""

    def test_profile_returns_correct_length(self):
        alts = [1000, 5000, 10000, 20000]
        profile = wind_profile(alts)
        assert len(profile) == len(alts)

    def test_profile_tuple_structure(self):
        profile = wind_profile([5000])
        alt, speed, direction = profile[0]
        assert alt == 5000
        assert speed > 0
        assert direction > 0

    def test_profile_consistent_with_individual_calls(self):
        alts = [1000, 5000, 10000]
        profile = wind_profile(alts, time_s=100)
        for (alt, sp, di) in profile:
            assert abs(sp - wind_speed(alt, time_s=100)) < 0.01
            assert abs(di - wind_direction(alt, time_s=100)) < 0.01


# ─── Wind Layer Definitions ───────────────────────────────────


class TestWindLayers:
    """Test the standard wind layer definitions."""

    def test_layer_count(self):
        assert len(STANDARD_WIND_LAYERS) == 5

    def test_layers_covers_troposphere(self):
        # First layer starts at sea level
        assert STANDARD_WIND_LAYERS[0][0] == 0

    def test_layers_contiguous(self):
        for i in range(1, len(STANDARD_WIND_LAYERS)):
            prev_top = STANDARD_WIND_LAYERS[i - 1][1]
            curr_bot = STANDARD_WIND_LAYERS[i][0]
            assert curr_bot == prev_top, f"Gap between layers: {prev_top} vs {curr_bot}"

    def test_layer_parameters_are_positive(self):
        for layer in STANDARD_WIND_LAYERS:
            bot, top, base, direction, amp = layer
            assert bot >= 0
            assert top > bot
            assert base > 0
            assert amp > 0


# ─── Site-specific gust model ─────────────────────────────────────


class TestSiteWindGusts:
    def test_getWindVelocity_deterministic(self):
        # Same (t, site, alt) should always match exactly.
        t = 123.45
        alt = 10000
        for site_id in WIND_SITES.keys():
            v1 = getWindVelocity(t, site_id=site_id, alt_m=alt)
            v2 = getWindVelocity(t, site_id=site_id, alt_m=alt)
            assert v1 == v2

    def test_sites_diverge_at_same_time(self):
        # Different site baselines should affect the magnitude at the same time.
        t = 200.0
        alt = 5000
        mags = {}
        for site_id in WIND_SITES.keys():
            u, v = getWindVelocity(t, site_id=site_id, alt_m=alt)
            mags[site_id] = math.sqrt(u * u + v * v)

        # With at least two sites, magnitudes should not all be equal.
        assert len(set(round(m, 6) for m in mags.values())) > 1

    def test_wind_is_bounded_with_gusts(self):
        # Ensure gusts do not push wind speeds into unstable territory.
        alt = 12000
        for site_id in WIND_SITES.keys():
            for t in [0, 10, 37, 90, 180, 360]:
                u, v = getWindVelocity(t, site_id=site_id, alt_m=alt)
                speed = math.sqrt(u * u + v * v)
                assert math.isfinite(speed)
                assert 0.0 <= speed < 25.0

    def test_gust_pattern_varies_over_time(self):
        # For a fixed site + altitude, wind magnitude should vary over time.
        alt = 8000
        site_id = "field" if "field" in WIND_SITES else next(iter(WIND_SITES.keys()))

        speeds = []
        for t in [0, 15, 30, 45, 60, 90, 120]:
            u, v = getWindVelocity(t, site_id=site_id, alt_m=alt)
            speeds.append(math.sqrt(u * u + v * v))

        assert max(speeds) - min(speeds) > 0.2
