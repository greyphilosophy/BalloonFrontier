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
