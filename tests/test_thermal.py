"""Tests for the thermal model (GDD §6.7)."""

import pytest
from balloon_frontier.thermal import (
    solar_flux_at_altitude, solar_absorbed, ir_radiated,
    convective_heat_transfer, thermal_node_update,
    calculate_balloon_heat_flows, gas_temperature_update,
    STEFAN_BOLTZMANN, SOLAR_CONSTANT,
)


class TestSolarFlux:
    def test_flux_at_sea_level_is_partial(self):
        flux = solar_flux_at_altitude(0)
        # Sea level ≈ 75% of solar constant
        assert abs(flux - 0.75 * SOLAR_CONSTANT) < SOLAR_CONSTANT * 0.01

    def test_flux_increases_with_altitude(self):
        flux_0 = solar_flux_at_altitude(0)
        flux_10k = solar_flux_at_altitude(10000)
        assert flux_10k > flux_0

    def test_flux_approaches_solar_constant(self):
        flux_high = solar_flux_at_altitude(50000)
        assert abs(flux_high - SOLAR_CONSTANT) < SOLAR_CONSTANT * 0.1

    def test_flux_is_non_negative(self):
        for alt in [0, 5000, 11000, 20000, 50000]:
            assert solar_flux_at_altitude(alt) >= 0


class TestSolarAbsorbed:
    def test_absorption_scales_with_area(self):
        q1 = solar_absorbed(1000, 0.5, 1.0)
        q2 = solar_absorbed(1000, 0.5, 2.0)
        assert abs(q2 / q1 - 2.0) < 0.01

    def test_absorption_scales_with_absorptivity(self):
        q1 = solar_absorbed(1000, 0.2, 1.0)
        q2 = solar_absorbed(1000, 0.5, 1.0)
        assert abs(q2 / q1 - 2.5) < 0.01

    def test_absorption_scales_with_flux(self):
        q1 = solar_absorbed(500, 0.5, 1.0)
        q2 = solar_absorbed(1000, 0.5, 1.0)
        assert abs(q2 / q1 - 2.0) < 0.01

    def test_zero_absorptivity(self):
        assert solar_absorbed(1000, 0.0, 1.0) == 0.0

    def test_zero_flux(self):
        assert solar_absorbed(0.0, 0.5, 1.0) == 0.0


class TestIRRadiated:
    def test_radiation_is_positive_when_hot(self):
        q = ir_radiated(0.8, 10.0, 300.0, 250.0)
        assert q > 0

    def test_radiation_is_negative_when_cold(self):
        q = ir_radiated(0.8, 10.0, 250.0, 300.0)
        assert q < 0

    def test_radiation_is_zero_at_equilibrium(self):
        q = ir_radiated(0.8, 10.0, 288.15, 288.15)
        assert abs(q) < 0.01

    def test_radiation_scales_with_emissivity(self):
        q1 = ir_radiated(0.4, 10.0, 300.0, 250.0)
        q2 = ir_radiated(0.8, 10.0, 300.0, 250.0)
        assert abs(q2 / q1 - 2.0) < 0.01

    def test_radiation_scales_with_area(self):
        q1 = ir_radiated(0.8, 5.0, 300.0, 250.0)
        q2 = ir_radiated(0.8, 10.0, 300.0, 250.0)
        assert abs(q2 / q1 - 2.0) < 0.01


class TestConvectiveHeat:
    def test_convection_is_positive_when_hot(self):
        q = convective_heat_transfer(1.0, 10.0, 300.0, 250.0)
        assert q > 0

    def test_convection_is_negative_when_cold(self):
        q = convective_heat_transfer(1.0, 10.0, 250.0, 300.0)
        assert q < 0

    def test_convection_is_zero_at_equilibrium(self):
        q = convective_heat_transfer(1.0, 10.0, 288.15, 288.15)
        assert abs(q) < 0.01

    def test_convection_scales_with_coefficient(self):
        q1 = convective_heat_transfer(1.0, 10.0, 300.0, 250.0)
        q2 = convective_heat_transfer(2.0, 10.0, 300.0, 250.0)
        assert abs(q2 / q1 - 2.0) < 0.01

    def test_convection_scales_with_area(self):
        q1 = convective_heat_transfer(1.0, 5.0, 300.0, 250.0)
        q2 = convective_heat_transfer(1.0, 10.0, 300.0, 250.0)
        assert abs(q2 / q1 - 2.0) < 0.01


class TestThermalNodeUpdate:
    def test_heating_increases_temperature(self):
        t_new = thermal_node_update(300.0, 1.0, 1000.0, 500.0, 1.0)
        assert t_new > 300.0

    def test_cooling_decreases_temperature(self):
        t_new = thermal_node_update(300.0, 1.0, 1000.0, -500.0, 1.0)
        assert t_new < 300.0

    def test_zero_heat_flow(self):
        t_new = thermal_node_update(300.0, 1.0, 1000.0, 0.0, 1.0)
        assert t_new == 300.0

    def test_delta_t_scaling(self):
        t1 = thermal_node_update(300.0, 1.0, 1000.0, 500.0, 1.0)
        t2 = thermal_node_update(300.0, 1.0, 1000.0, 500.0, 2.0)
        assert abs(t2 - 300.0) > abs(t1 - 300.0)

    def test_mass_scaling(self):
        t1 = thermal_node_update(300.0, 1.0, 1000.0, 500.0, 1.0)
        t2 = thermal_node_update(300.0, 2.0, 1000.0, 500.0, 1.0)
        assert t2 < t1


class TestHeatFlowIntegration:
    def test_calculate_returns_all_fields(self):
        flows = calculate_balloon_heat_flows(
            altitude_m=0, gas_temp_K=288.15, gas_mass_kg=1.0,
            gas_type="helium", envelope_absorptivity=0.5,
            envelope_emissivity=0.8, envelope_area_m2=10.0,
            envelope_mass_kg=1.0, heater_power_watts=100.0,
            equipment_heat_watts=50.0
        )
        for key in ["Q_solar", "Q_convection", "Q_radiation", "Q_heater",
                     "Q_equipment", "Q_total", "ambient_temperature"]:
            assert key in flows

    def test_heater_contributes_to_total(self):
        flows_base = calculate_balloon_heat_flows(
            0, 288.15, 1.0, "helium", 0.5, 0.8, 10.0, 1.0, 0.0, 50.0
        )
        flows_heated = calculate_balloon_heat_flows(
            0, 288.15, 1.0, "helium", 0.5, 0.8, 10.0, 1.0, 100.0, 50.0
        )
        assert flows_heated["Q_total"] > flows_base["Q_total"]

    def test_solar_flux_increases_with_altitude(self):
        flows_0 = calculate_balloon_heat_flows(
            0, 288.15, 1.0, "helium", 0.5, 0.8, 10.0, 1.0, 0.0, 50.0
        )
        flows_10k = calculate_balloon_heat_flows(
            10000, 288.15, 1.0, "helium", 0.5, 0.8, 10.0, 1.0, 0.0, 50.0
        )
        assert flows_10k["Q_solar"] > flows_0["Q_solar"]


class TestGasTemperatureUpdate:
    def test_helium_temps_update(self):
        flows = {"Q_total": 100.0}
        t_new = gas_temperature_update("helium", 1.0, 288.15, flows, 1.0)
        assert t_new > 288.15

    def test_hydrogen_temps_update(self):
        flows = {"Q_total": 100.0}
        t_new = gas_temperature_update("hydrogen", 1.0, 288.15, flows, 1.0)
        assert t_new > 288.15

    def test_hot_air_temps_update(self):
        flows = {"Q_total": 100.0}
        t_new = gas_temperature_update("hot_air", 1.0, 288.15, flows, 1.0)
        assert t_new > 288.15

    def test_methane_temps_update(self):
        flows = {"Q_total": 100.0}
        t_new = gas_temperature_update("methane", 1.0, 288.15, flows, 1.0)
        assert t_new > 288.15

    def test_negative_heat_cools_gas(self):
        flows = {"Q_total": -100.0}
        t_new = gas_temperature_update("helium", 1.0, 288.15, flows, 1.0)
        assert t_new < 288.15

    def test_specific_heat_affects_rate(self):
        flows = {"Q_total": -100.0}
        t_he = gas_temperature_update("helium", 1.0, 288.15, flows, 1.0)
        t_h2 = gas_temperature_update("hydrogen", 1.0, 288.15, flows, 1.0)
        assert (288.15 - t_h2) < (288.15 - t_he)


class TestHotAirHeaterTracking:
    """Hot air gas temperature tracks a heater target temperature."""

    def test_hot_air_tracks_heater_target(self):
        """Hot air with a heater target should approach the target temperature."""
        t_new = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=290.0,
            heat_flows={},
            dt=1.0,
            target_heater_temp_K=350.0,
        )
        # Should move toward 350K
        assert t_new > 290.0
        assert t_new < 350.0  # Shouldn't overshoot

    def test_hot_air_heater_warms_cold_gas(self):
        """When gas is well below target, it should heat up significantly."""
        t_new = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=290.0,
            heat_flows={},
            dt=30.0,
            target_heater_temp_K=350.0,
        )
        # After 30s (one time constant), should cover ~63% of the delta
        delta = 350.0 - 290.0
        expected_min = 290.0 + delta * 0.6
        assert t_new >= expected_min

    def test_hot_air_heater_does_not_overshoot(self):
        """Heater tracking should not overshoot the target."""
        t_new = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=340.0,
            heat_flows={},
            dt=10.0,
            target_heater_temp_K=350.0,
        )
        assert t_new < 350.0

    def test_hot_air_cools_when_above_target(self):
        """When gas is hotter than target, it should cool toward the target."""
        t_new = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=360.0,
            heat_flows={},
            dt=1.0,
            target_heater_temp_K=350.0,
        )
        assert t_new < 360.0
        assert t_new > 350.0  # Shouldn't undershoot

    def test_hot_air_without_heater_uses_natural_model(self):
        """Without a heater target, hot air falls back to natural thermal model."""
        flows = {"Q_total": 100.0}
        t_new = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=288.15,
            heat_flows=flows,
            dt=1.0,
        )
        # Should heat up (Q_total = 100W, c=1005, m=1kg)
        expected = 288.15 + (100.0 / (1.0 * 1005.0)) * 1.0
        assert abs(t_new - expected) < 0.01

    def test_hot_air_stays_at_target(self):
        """When gas temperature equals the heater target, it stays there."""
        t_new = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=350.0,
            heat_flows={},
            dt=1.0,
            target_heater_temp_K=350.0,
        )
        assert abs(t_new - 350.0) < 0.01

    def test_hot_air_multiple_steps_approach_target(self):
        """Repeated heating steps should converge on the target."""
        temp = 290.0
        for _ in range(10):
            temp = gas_temperature_update(
                gas_type="hot_air",
                gas_mass_kg=1.0,
                gas_temp_K=temp,
                heat_flows={},
                dt=5.0,
                target_heater_temp_K=350.0,
            )
        assert temp > 330.0  # After ~50s, should be close to 350K
        assert temp < 350.0

    def test_hot_air_heater_respects_higher_target(self):
        """A higher target heater temperature yields more heating."""
        t_low = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=290.0,
            heat_flows={},
            dt=10.0,
            target_heater_temp_K=320.0,
        )
        t_high = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=290.0,
            heat_flows={},
            dt=10.0,
            target_heater_temp_K=380.0,
        )
        assert t_high > t_low


class TestGasTypeDifferentiation:
    """Verify that each gas type behaves differently in thermal updates."""

    def test_helium_uses_natural_model(self):
        """Helium temperature follows natural thermal equilibrium."""
        flows = {"Q_total": -50.0}
        t_cold = gas_temperature_update(
            gas_type="helium",
            gas_mass_kg=1.0,
            gas_temp_K=300.0,
            heat_flows=flows,
            dt=1.0,
        )
        # Negative Q_total should cool the gas
        assert t_cold < 300.0

    def test_hydrogen_uses_natural_model(self):
        """Hydrogen temperature follows natural thermal equilibrium."""
        flows = {"Q_total": -50.0}
        t_cold = gas_temperature_update(
            gas_type="hydrogen",
            gas_mass_kg=1.0,
            gas_temp_K=300.0,
            heat_flows=flows,
            dt=1.0,
        )
        # Negative Q_total should cool the gas
        assert t_cold < 300.0

    def test_methane_uses_natural_model(self):
        """Methane temperature follows natural thermal equilibrium."""
        flows = {"Q_total": -50.0}
        t_cold = gas_temperature_update(
            gas_type="methane",
            gas_mass_kg=1.0,
            gas_temp_K=300.0,
            heat_flows=flows,
            dt=1.0,
        )
        assert t_cold < 300.0

    def test_hot_air_with_heater_differs_from_helium(self):
        """Hot air with a heater target tracks temperature differently than helium."""
        # Hot air with heater: approaches target
        t_hot = gas_temperature_update(
            gas_type="hot_air",
            gas_mass_kg=1.0,
            gas_temp_K=300.0,
            heat_flows={"Q_total": 0.0},
            dt=1.0,
            target_heater_temp_K=350.0,
        )
        # Helium with zero heat flow: stays the same
        t_He = gas_temperature_update(
            gas_type="helium",
            gas_mass_kg=1.0,
            gas_temp_K=300.0,
            heat_flows={"Q_total": 0.0},
            dt=1.0,
        )
        assert t_hot > 300.0  # Heating toward target
        assert abs(t_He - 300.0) < 0.01  # No change with zero heat
