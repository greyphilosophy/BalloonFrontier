"""Tests for fuel consumption, landing, and descent mechanics."""

import pytest
from balloon_frontier.fuel import (
    calculate_fuel_consumption,
    has_fuel_for_safe_landing,
    calculate_landing_score,
    simulate_landing_sequence,
    HOT_AIR_DESCENT_RATE_MPS,
    SAFE_LANDING_VELOCITY_MPS,
    CRASH_VELOCITY_MPS,
)


class TestFuelConsumption:
    """Test fuel consumption calculations."""

    def test_no_consumption_when_still(self):
        result = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=False, heater_power_fraction=1.0,
            battery_on=False, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.0, elapsed_time_s=60.0,
        )
        assert result["fuel_total_consumed_kg"] == 0.0
        assert result["fuel_mass_remaining_kg"] == 10.0

    def test_permeability_reduces_fuel(self):
        result = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=False, heater_power_fraction=1.0,
            battery_on=False, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.001, elapsed_time_s=60.0,
        )
        assert result["fuel_consumed_by_permeability_kg"] > 0
        assert result["fuel_mass_remaining_kg"] < 10.0

    def test_heater_consumes_fuel(self):
        result = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=True, heater_power_fraction=1.0,
            battery_on=False, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.0, elapsed_time_s=60.0,
        )
        assert result["fuel_consumed_by_heater_kg"] > 0
        assert result["fuel_total_consumed_kg"] > 0

    def test_battery_drain_independent_of_fuel(self):
        result = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=False, heater_power_fraction=1.0,
            battery_on=True, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.0, elapsed_time_s=60.0,
        )
        assert result["battery_remaining_wh"] < 100.0
        assert result["battery_percentage"] < 100

    def test_fuel_capped_at_zero(self):
        result = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=True, heater_power_fraction=1.0,
            battery_on=False, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.0, elapsed_time_s=10000.0,
        )
        assert result["fuel_mass_remaining_kg"] == 0.0

    def test_battery_capped_at_zero(self):
        result = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=False, heater_power_fraction=1.0,
            battery_on=True, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.0, elapsed_time_s=100000.0,
        )
        assert result["battery_remaining_wh"] == 0.0
        assert result["battery_percentage"] == 0.0

    def test_heater_power_fraction_is_inverted(self):
        """Higher fraction = more fuel consumed."""
        result_full = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=True, heater_power_fraction=1.0,
            battery_on=False, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.0, elapsed_time_s=60.0,
        )
        result_half = calculate_fuel_consumption(
            fuel_type="helium", fuel_mass_kg=10.0,
            heater_on=True, heater_power_fraction=0.5,
            battery_on=False, battery_capacity_wh=100.0,
            battery_drain_rate_watts=10.0,
            permeability=0.0, elapsed_time_s=60.0,
        )
        # Higher fraction consumes more
        assert result_full["fuel_consumed_by_heater_kg"] > result_half["fuel_consumed_by_heater_kg"]


class TestSafeLanding:
    """Test safe landing detection."""

    def test_sufficient_fuel_for_safe_landing(self):
        assert has_fuel_for_safe_landing(5.0, 10.0)

    def test_insufficient_fuel_for_safe_landing(self):
        assert not has_fuel_for_safe_landing(0.1, 10.0)

    def test_heavy_payload_needs_more_fuel(self):
        assert not has_fuel_for_safe_landing(1.0, 20.0)

    def test_light_payload_needs_less_fuel(self):
        assert has_fuel_for_safe_landing(1.0, 5.0)


class TestLandingScore:
    """Test landing quality scoring with safe velocities."""

    def test_ideal_landing_scores_high(self):
        result = calculate_landing_score(
            "controlled_hot_air", 0, 0.5)
        assert result["score"] >= 90
        assert result["is_safe"]

    def test_crash_scores_low(self):
        result = calculate_landing_score(
            "free_fall", 0, 10.0)
        assert result["is_crash"]
        assert result["score"] < 80

    def test_dangerous_landing_score_low(self):
        dangerous = calculate_landing_score(
            "free_fall", 0, 15.0)
        assert dangerous["is_crash"]
        assert dangerous["score"] < 50


class TestLandingSequence:
    """Test full landing sequence simulation."""

    def test_hot_air_with_fuel_descends(self):
        result = simulate_landing_sequence(
            start_altitude_m=1000.0, start_velocity_mps=0.0,
            fuel_remaining_kg=10.0, has_parachute=False,
            has_hot_air=True, payload_mass_kg=10.0,
        )
        assert result["landing_method"] == "controlled_hot_air"

    def test_no_fuel_no_parachute_falls(self):
        result = simulate_landing_sequence(
            start_altitude_m=1000.0, start_velocity_mps=0.0,
            fuel_remaining_kg=0.0, has_parachute=False,
            has_hot_air=False, payload_mass_kg=10.0,
        )
        assert result["landing_method"] == "free_fall"

    def test_parachute_deployment(self):
        result = simulate_landing_sequence(
            start_altitude_m=1000.0, start_velocity_mps=0.0,
            fuel_remaining_kg=0.0, has_parachute=True,
            has_hot_air=False, payload_mass_kg=10.0,
        )
        assert result["landing_method"] == "parachute"

    def test_landing_score_is_reasonable(self):
        result = simulate_landing_sequence(
            start_altitude_m=100.0, start_velocity_mps=0.0,
            fuel_remaining_kg=10.0, has_parachute=False,
            has_hot_air=True, payload_mass_kg=10.0,
        )
        assert 0 <= result["score"] <= 100
