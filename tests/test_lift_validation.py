"""Validate lift magnitude with first-principles calculation.

Runs as a pytest test. Independently computes expected buoyancy for a
representative hot-air balloon scenario, then compares against the
implementation output.

SCENARIO:
  - T_gas = 353 K, T_amb = 288 K (delta = +65K)
  - Sea-level pressure = 101325 Pa
  - Gas mass = 10 kg hot_air
  - g = 9.80665 m/s²

APPROACH:
  1. Compute ambient air density from ideal gas law: rho_air = P / (R_air * T_amb)
  2. Compute hot gas density: rho_gas = P / (R_air * T_gas)
  3. Compute gas volume: V = mass * R_air * T_gas / P
  4. Lift force = (rho_air - rho_gas) * g * V
  5. Compare with buoyant_force("hot_air", 10, 353, 0)
"""

import pytest
from balloon_frontier.physics import (
    G, R, R_AIR, SEA_LEVEL_PRESSURE, SEA_LEVEL_TEMPERATURE, MOLAR_MASS,
    buoyant_force, atmosphere_density, gas_density, gas_volume
)


def compute_expected_lift(t_gas, t_amb, gas_mass, pressure):
    """Compute expected buoyant lift from first principles."""
    # Verify hot_air R_specific matches R_AIR
    r_hot = R / MOLAR_MASS["hot_air"]
    rho_air = pressure / (R_AIR * t_amb)
    rho_gas = pressure / (r_hot * t_gas)
    volume = gas_mass * r_hot * t_gas / pressure
    lift = (rho_air - rho_gas) * G * volume
    return {
        "rho_air": rho_air,
        "rho_gas": rho_gas,
        "volume": volume,
        "lift_force": lift,
    }


class TestLiftMagnitudeValidation:
    """Validate that the implementation matches first-principles calculations."""

    def test_hot_air_lift_matches_first_principles_at_plus_65k(self):
        """T_gas = 353K, T_amb = 288.15K => lift ≈ 22.07 N for 10kg hot_air."""
        t_gas = 353.0
        t_amb = SEA_LEVEL_TEMPERATURE
        gas_mass = 10.0

        expected = compute_expected_lift(t_gas, t_amb, gas_mass, SEA_LEVEL_PRESSURE)
        actual = buoyant_force("hot_air", gas_mass, t_gas, 0.0)

        pct_diff = abs(expected["lift_force"] - actual) / actual * 100
        assert pct_diff < 1, f"Difference exceeds 1%: {pct_diff:.4f}%"
        assert actual > 20, f"Lift should be >20 N at +65K, got {actual:.4f} N"

    def test_hot_air_lift_matches_first_principles_at_multiple_deltas(self):
        """Verify lift at multiple temperature deltas matches first principles."""
        gas_mass = 10.0
        for delta in [10, 25, 50, 65, 100, 150]:
            t_gas = SEA_LEVEL_TEMPERATURE + delta
            expected = compute_expected_lift(t_gas, SEA_LEVEL_TEMPERATURE, gas_mass, SEA_LEVEL_PRESSURE)
            actual = buoyant_force("hot_air", gas_mass, t_gas, 0.0)
            pct_diff = abs(expected["lift_force"] - actual) / actual * 100
            assert pct_diff < 1, (
                f"ΔT={delta}K: diff={pct_diff:.4f}%, expected={expected['lift_force']:.4f}, actual={actual:.4f}"
            )

    def test_hot_air_near_zero_lift_at_equal_temps(self):
        """T_gas == T_amb => lift ≈ 0."""
        actual = buoyant_force("hot_air", 10.0, SEA_LEVEL_TEMPERATURE, 0.0)
        assert abs(actual) < 1e-6, f"Should be near zero: {actual}"

    def test_hot_air_r_matches_r_air(self):
        """R/M_hot_air should match R_AIR to within tolerance."""
        r_hot = R / MOLAR_MASS["hot_air"]
        assert abs(r_hot - R_AIR) < 0.1, f"R/M_hot_air={r_hot} vs R_AIR={R_AIR}"

    def test_lift_is_positive_for_t_gas_above_t_amb(self):
        """For T_gas > T_amb, lift should be positive."""
        t_gas = 353.0
        t_amb = SEA_LEVEL_TEMPERATURE
        assert t_gas > t_amb, "Precondition: T_gas > T_amb"
        actual = buoyant_force("hot_air", 10.0, t_gas, 0.0)
        assert actual > 0, f"Lift should be positive: {actual:.4f} N"
