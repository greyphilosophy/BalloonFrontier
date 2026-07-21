"""Comprehensive tests for Balloon Frontier physics engine.

Every physics equation from the GDD has at least one test.
Reference: Balloon Frontier GDD Sections 6, 16, 20.
"""

import math
import pytest
from balloon_frontier.physics import (
    atmosphere_temperature,
    atmosphere_pressure,
    atmosphere_density,
    gas_volume,
    gas_density,
    buoyant_force,
    drag_force,
    spherical_area,
    burst_volume,
    G, R, R_AIR, SEA_LEVEL_PRESSURE, SEA_LEVEL_TEMPERATURE, MOLAR_MASS,
)


# ─── Constants ──────────────────────────────────────────────────────────

def test_g_value():
    assert abs(G - 9.80665) < 0.01

def test_r_universal():
    assert abs(R - 8.314462618) < 0.01

def test_r_air():
    assert abs(R_AIR - 287.05) < 0.01


# ─── Atmosphere Model (Section 6.2) ────────────────────────────────────

class TestAtmosphereModel:
    """Test the US Standard Atmosphere approximation."""

    def test_sea_level_temperature(self):
        assert abs(atmosphere_temperature(0) - 288.15) < 0.01

    def test_sea_level_pressure(self):
        assert abs(atmosphere_pressure(0) - 101325.0) < 0.1

    def test_sea_level_density(self):
        assert abs(atmosphere_density(0) - 1.225) < 0.01

    def test_density_decreases_with_altitude(self):
        d0 = atmosphere_density(0)
        d10 = atmosphere_density(10000)
        d20 = atmosphere_density(20000)
        assert d0 > d10 > d20

    def test_temperature_at_tropopause(self):
        assert abs(atmosphere_temperature(11000) - 216.65) < 0.01

    def test_temperature_stratosphere(self):
        t12 = atmosphere_temperature(12000)
        t15 = atmosphere_temperature(15000)
        t18 = atmosphere_temperature(18000)
        assert abs(t12 - t15) < 0.01
        assert abs(t15 - t18) < 0.01

    def test_density_at_50km_is_reasonable(self):
        d = atmosphere_density(50000)
        # At 50km, density is ~0.0009 kg/m³ for standard atmosphere
        assert 0.0005 < d < 0.01

    def test_ideal_gas_consistency(self):
        for alt in [0, 5000, 10000, 20000, 35000, 50000]:
            P = atmosphere_pressure(alt)
            T = atmosphere_temperature(alt)
            rho = atmosphere_density(alt)
            P_calc = rho * R_AIR * T
            assert abs(P / P_calc - 1.0) < 0.02


# ─── Gas Calculations (Section 6.3) ──────────────────────────────────

class TestGasLaws:
    """Test ideal gas law calculations for lifting gases."""

    def test_helium_volume_at_stp(self):
        """1 kg helium at STP ≈ 11.9 m³."""
        v = gas_volume(1.0, "helium", SEA_LEVEL_TEMPERATURE, SEA_LEVEL_PRESSURE)
        assert 5.5 < v < 12.5

    def test_hydrogen_volume_at_stp(self):
        """1 kg hydrogen at STP ≈ 11.7 m³."""
        v = gas_volume(1.0, "hydrogen", SEA_LEVEL_TEMPERATURE, SEA_LEVEL_PRESSURE)
        assert 11.0 < v < 13.0

    def test_volume_inversely_proportional_to_pressure(self):
        v_low = gas_volume(1.0, "helium", 288.15, 50000.0)
        v_high = gas_volume(1.0, "helium", 288.15, 101325.0)
        ratio = v_low / v_high
        assert 1.8 < ratio < 2.2

    def test_volume_directly_proportional_to_temperature(self):
        v_cold = gas_volume(1.0, "helium", 200.0, 101325.0)
        v_warm = gas_volume(1.0, "helium", 300.0, 101325.0)
        ratio = v_warm / v_cold
        expected_ratio = 300.0 / 200.0
        assert abs(ratio / expected_ratio - 1.0) < 0.01

    def test_hydrogen_less_dense_than_ambient(self):
        rho_h2 = gas_density("hydrogen", 288.15, 101325.0)
        rho_air = atmosphere_density(0)
        assert rho_h2 < rho_air

    def test_molar_masses_defined(self):
        for gas in ["helium", "hydrogen", "hot_air", "methane"]:
            assert gas in MOLAR_MASS
            assert MOLAR_MASS[gas] > 0


# ─── Buoyancy (Section 6.4) ──────────────────────────────────────────

class TestBuoyancy:
    """Test buoyant force calculations."""

    def test_helium_lift_positive(self):
        assert buoyant_force("helium", 1.0, 288.15, 0) > 0

    def test_hydrogen_lift_greater_than_helium(self):
        assert buoyant_force("hydrogen", 1.0, 288.15, 0) > buoyant_force("helium", 1.0, 288.15, 0)

    def test_hot_air_less_dense_when_warm(self):
        rho_hot = gas_density("hot_air", 350.0, 101325.0)
        rho_cold = atmosphere_density(0)
        assert rho_hot < rho_cold

    def test_hot_air_matches_ambient_density_at_same_temperature(self):
        """If the envelope gas temperature equals ambient, hot-air density should match
        ambient air density at the same pressure, so buoyancy approaches zero."""
        T_amb = 288.15
        P_amb = 101325.0

        rho_gas = gas_density("hot_air", T_amb, P_amb)
        rho_air = atmosphere_density(0)
        assert abs(rho_gas - rho_air) < 1e-6

        # Using 10kg is arbitrary; any nonzero difference should be very small.
        F_buoy = buoyant_force("hot_air", 10.0, T_amb, 0.0)
        assert abs(F_buoy) < 1e-6

    def test_zero_mass_zero_lift(self):
        assert abs(buoyant_force("helium", 0.0, 288.15, 0)) < 0.001

    def test_lift_proportional_to_mass(self):
        l1 = buoyant_force("helium", 1.0, 288.15, 0)
        l2 = buoyant_force("helium", 2.0, 288.15, 0)
        assert abs(l2 / l1 - 2.0) < 0.01


# ─── Drag (Section 6.6) ──────────────────────────────────────────

class TestDrag:
    """Test aerodynamic drag calculations."""

    def test_zero_velocity_zero_drag(self):
        assert drag_force(0.0, 0, 0.47, 1.0) == 0.0

    def test_drag_scales_with_velocity_squared(self):
        d1 = drag_force(1.0, 0, 0.47, 1.0)
        d2 = drag_force(2.0, 0, 0.47, 1.0)
        assert abs(d2 / d1 - 4.0) < 0.02

    def test_drag_decreases_with_altitude(self):
        d_sl = drag_force(10.0, 0, 0.47, 1.0)
        d_10k = drag_force(10.0, 10000, 0.47, 1.0)
        assert d_sl > d_10k

    def test_drag_proportional_to_coefficient(self):
        d1 = drag_force(5.0, 0, 0.47, 1.0)
        d2 = drag_force(5.0, 0, 0.94, 1.0)
        assert abs(d2 / d1 - 2.0) < 0.01

    def test_drag_proportional_to_area(self):
        d1 = drag_force(5.0, 0, 0.47, 1.0)
        d2 = drag_force(5.0, 0, 0.47, 2.0)
        assert abs(d2 / d1 - 2.0) < 0.01

    def test_negative_velocity_same_drag(self):
        assert abs(drag_force(5.0, 0, 0.47, 1.0) - drag_force(-5.0, 0, 0.47, 1.0)) < 0.001


# ─── Geometry (Sections 6.5, 7) ──────────────────────────────────

class TestGeometry:
    """Test balloon geometry calculations."""

    def test_sphere_area_matches_formula(self):
        a = spherical_area(1.0)
        expected = math.pi * ((3 / (4 * math.pi)) ** (2/3))
        assert abs(a - expected) < 0.01

    def test_area_scales_with_volume(self):
        a1 = spherical_area(1.0)
        a8 = spherical_area(8.0)
        assert abs(a8 / a1 - 4.0) < 0.02

    def test_burst_volume(self):
        assert burst_volume(2.5, 10.0) == 25.0
        assert burst_volume(1.0, 10.0) == 10.0


# ─── Deterministic Simulation (Section 16) ───────────────────────

class TestDeterminism:
    """Test that simulation is deterministic for replay."""

    def test_atmosphere_deterministic(self):
        for alt in [0, 5000, 10000, 20000, 50000]:
            assert atmosphere_temperature(alt) == atmosphere_temperature(alt)
            assert atmosphere_pressure(alt) == atmosphere_pressure(alt)

    def test_gas_volume_deterministic(self):
        for _ in range(5):
            v1 = gas_volume(1.0, "helium", 288.15, 101325.0)
            v2 = gas_volume(1.0, "helium", 288.15, 101325.0)
            assert v1 == v2

    def test_drag_deterministic(self):
        for _ in range(5):
            d1 = drag_force(5.0, 1000, 0.47, 1.0)
            d2 = drag_force(5.0, 1000, 0.47, 1.0)
            assert d1 == d2


# ─── Edge Cases ───────────────────────────────────────────────

class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    def test_negative_altitude(self):
        t = atmosphere_temperature(-100)
        assert t > 0

    def test_extreme_altitude(self):
        assert atmosphere_temperature(50000) > 0
        assert atmosphere_pressure(50000) > 0
        assert atmosphere_density(50000) > 0

    def test_small_gas_mass(self):
        v = gas_volume(0.001, "helium", 288.15, 101325.0)
        assert v > 0
