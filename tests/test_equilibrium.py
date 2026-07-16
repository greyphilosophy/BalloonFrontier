"""Tests for Balloon Frontier equilibrium altitude calculator.

Reference: GDD Section 6.8 (Equilibrium/floating altitude).
"""

import pytest
from balloon_frontier.equilibrium import (
    equilibrium_altitude,
    equilibrium_altitude_with_leakage,
)
from balloon_frontier.physics import (
    atmosphere_density,
    atmosphere_pressure,
    gas_density,
    gas_volume,
    G,
)


# ─── Equilibrium Altitude ─────────────────────────────────────

class TestEquilibriumAltitude:
    """Test equilibrium altitude calculations."""

    def test_equilibrium_exists_for_balanced_balloon(self):
        """A well-designed helium balloon should have a realistic equilibrium."""
        # 10 kg helium, total vehicle mass ~15 kg
        # This should float somewhere reasonable
        alt = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=15.0,
            envelope_max_volume=500.0,
            contained_gas=False,
        )
        assert alt >= 0
        # Should be a reasonable altitude for a light balloon
        assert alt < 50000

    def test_heavier_balloon_floats_lower(self):
        """Heavier vehicle mass should result in lower equilibrium."""
        alt_light = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=12.0,
            envelope_max_volume=500.0,
        )
        alt_heavy = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=18.0,
            envelope_max_volume=500.0,
        )
        assert alt_light > alt_heavy

    def test_more_gas_mass_raises_equilibrium(self):
        """More lifting gas should raise the equilibrium altitude."""
        alt_few = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=5.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=12.0,
            envelope_max_volume=200.0,
        )
        alt_more = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=15.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=22.0,
            envelope_max_volume=500.0,
        )
        assert alt_more > alt_few

    def test_hydrogen_equilibrium_higher_than_helium(self):
        """Same mass of hydrogen should float higher than helium."""
        alt_He = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=5.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=8.0,
            envelope_max_volume=200.0,
        )
        alt_H2 = equilibrium_altitude(
            gas_type="hydrogen",
            gas_mass_kg=5.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=8.0,
            envelope_max_volume=200.0,
        )
        # Hydrogen should reach higher for the same mass
        assert alt_H2 > alt_He

    def test_zero_pressure_limits_volume(self):
        """Zero-pressure envelopes clamp displaced volume, affecting equilibrium."""
        # Large gas mass in small envelope - volume gets clamped
        alt_zp = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=50.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=55.0,
            envelope_max_volume=100.0,
            contained_gas=False,
        )
        # Same gas mass but larger envelope
        alt_big = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=50.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=55.0,
            envelope_max_volume=500.0,
            contained_gas=False,
        )
        assert alt_big > alt_zp

    def test_perpetually_ascending_returns_negative(self):
        """If a balloon has too much lift, it floats above our search range."""
        alt = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=100.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=10.0,
            envelope_max_volume=2000.0,
            contained_gas=True,
        )
        assert alt == -1  # No equilibrium within 50km

    def test_ground_sitting_balloon(self):
        """If the balloon is so heavy it barely lifts, equilibrium is near 0."""
        alt = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=1.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=100.0,
            envelope_max_volume=50.0,
        )
        # This balloon is mostly sitting on the ground
        assert alt >= 0

    def test_equilibrium_is_self_consistent(self):
        """Verify that at the returned altitude, net lift is approximately zero."""
        gas_mass = 8.0
        total_mass = 12.0
        alt = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=gas_mass,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=total_mass,
            envelope_max_volume=200.0,
        )
        if alt >= 0:
            P = atmosphere_pressure(alt)
            vol = gas_volume(gas_mass, "helium", 288.15, P)
            vol = min(vol, 200.0)
            rho_air = atmosphere_density(alt)
            rho_gas = gas_density("helium", 288.15, P)
            net_lift = (rho_air - rho_gas) * G * vol - total_mass * G
            # Should be close to zero (within a few Newtons)
            assert abs(net_lift) < 1.0

    def test_equilibrium_is_deterministic(self):
        """Same inputs should always return the same altitude."""
        alt1 = equilibrium_altitude(
            gas_type="helium", gas_mass_kg=7.0, gas_temperature_k=288.15,
            total_vehicle_mass_kg=10.0, envelope_max_volume=150.0,
        )
        alt2 = equilibrium_altitude(
            gas_type="helium", gas_mass_kg=7.0, gas_temperature_k=288.15,
            total_vehicle_mass_kg=10.0, envelope_max_volume=150.0,
        )
        assert alt1 == alt2


class TestEquilibriumWithLeakage:
    """Test equilibrium calculations that account for gas leakage."""

    def test_leakage_lowers_equilibrium(self):
        """Over time, gas leakage should lower the equilibrium altitude."""
        alt_initial = equilibrium_altitude_with_leakage(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=15.0,
            envelope_max_volume=200.0,
            permeability=0.01,
            simulation_time_s=0.0,
        )
        alt_later = equilibrium_altitude_with_leakage(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=15.0,
            envelope_max_volume=200.0,
            permeability=0.01,
            simulation_time_s=100.0,
        )
        assert alt_later <= alt_initial

    def test_no_leakage_equals_basic_equilibrium(self):
        """Zero permeability should match the basic equilibrium function."""
        alt_basic = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=15.0,
            envelope_max_volume=200.0,
        )
        alt_leak = equilibrium_altitude_with_leakage(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=288.15,
            total_vehicle_mass_kg=15.0,
            envelope_max_volume=200.0,
            permeability=0.0,
            simulation_time_s=50.0,
        )
        assert abs(alt_basic - alt_leak) < 0.1

    def test_high_leakage_significantly_lowers_altitude(self):
        """High permeability over time reduces effective gas mass."""
        alt_low_leak = equilibrium_altitude_with_leakage(
            gas_type="helium", gas_mass_kg=10.0, gas_temperature_k=288.15,
            total_vehicle_mass_kg=15.0, envelope_max_volume=200.0,
            permeability=0.001, simulation_time_s=500.0,
        )
        alt_high_leak = equilibrium_altitude_with_leakage(
            gas_type="helium", gas_mass_kg=10.0, gas_temperature_k=288.15,
            total_vehicle_mass_kg=15.0, envelope_max_volume=200.0,
            permeability=0.01, simulation_time_s=500.0,
        )
        assert alt_high_leak < alt_low_leak
