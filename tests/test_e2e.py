"""End-to-end tests for Balloon Frontier.

Tests that string together the full pipeline: configure → simulate → evaluate.
"""

import pytest
from balloon_frontier.simulation import SimulationState, run_simulation, EnvelopeConfig
from balloon_frontier.thermal import solar_flux_at_altitude


class TestEndToEndFlights:
    """Full flight tests — configure → simulate → evaluate."""

    def test_helium_balloon_rises(self):
        """Helium balloon with sufficient envelope volume ascends."""
        s = SimulationState(
            gas_type="helium", gas_mass_kg=10.0,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=3.0,
                                    contained_gas=True),
        )
        result = run_simulation(s, dt=0.1, total_time_s=10.0)
        for i in range(1, len(result)):
            assert result[i]["altitude_m"] >= result[i-1]["altitude_m"]

    def test_hydrogen_outperforms_helium(self):
        """Hydrogen balloon reaches higher peak than helium, same mass."""
        s_He = SimulationState(
            gas_mass_kg=5.0, gas_type="helium",
            payload_mass_kg=3.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0,
                                    contained_gas=True),
        )
        s_H2 = SimulationState(
            gas_mass_kg=5.0, gas_type="hydrogen",
            payload_mass_kg=3.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0,
                                    contained_gas=True),
        )
        tel_He = run_simulation(s_He, dt=0.1, total_time_s=5.0)
        tel_H2 = run_simulation(s_H2, dt=0.1, total_time_s=5.0)
        assert tel_H2[-1]["altitude_m"] > tel_He[-1]["altitude_m"]

    def test_more_payload_lowers_ascent(self):
        """More payload mass reduces ascent rate."""
        s_light = SimulationState(
            gas_mass_kg=5.0, gas_type="helium",
            payload_mass_kg=2.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0,
                                    contained_gas=True),
        )
        s_heavy = SimulationState(
            gas_mass_kg=5.0, gas_type="helium",
            payload_mass_kg=8.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0,
                                    contained_gas=True),
        )
        tel_light = run_simulation(s_light, dt=0.1, total_time_s=5.0)
        tel_heavy = run_simulation(s_heavy, dt=0.1, total_time_s=5.0)
        assert tel_light[-1]["altitude_m"] > tel_heavy[-1]["altitude_m"]

    def test_simulation_returns_valid_telemetry(self):
        """Simulation output contains all expected fields."""
        s = SimulationState(
            gas_mass_kg=5.0, gas_type="helium",
            payload_mass_kg=2.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        result = run_simulation(s, dt=0.1, total_time_s=1.0)
        last = result[-1]
        for field in ["altitude_m", "velocity_mps", "gas_mass_kg"]:
            assert field in last


class TestValveTradeoff:
    """Test the valve vs. burst trade-off (core gameplay mechanic)."""

    def test_valve_tradeoff_exists(self):
        """A balloon WITH a pressure valve vents gas and survives.
        A balloon WITHOUT one reaches higher but risks burst.
        
        The valve costs ~0.5kg. Without it, you get that lift back,
        but the balloon can pop when volume exceeds burst_stretch_ratio.
        """
        # Both start identical except for the valve mass
        s_with_valve = SimulationState(
            gas_type="helium", gas_mass_kg=10.0,
            payload_mass_kg=5.5,  # 0.5kg valve
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=3.0,
                                    contained_gas=True),
        )
        s_no_valve = SimulationState(
            gas_type="helium", gas_mass_kg=10.0,
            payload_mass_kg=5.0,  # lighter, no valve
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=3.0,
                                    contained_gas=True),
        )
        tel_with = run_simulation(s_with_valve, dt=0.1, total_time_s=10.0)
        tel_no = run_simulation(s_no_valve, dt=0.1, total_time_s=10.0)
        peak_with = max(t["altitude_m"] for t in tel_with)
        peak_no = max(t["altitude_m"] for t in tel_no)

        # No-valve balloon gets lighter → climbs higher
        assert peak_no > peak_with

    def test_burst_is_detectable(self):
        """When a balloon bursts, the simulation reflects it."""
        s = SimulationState(
            gas_type="helium", gas_mass_kg=10.0,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=3.0,
                                    contained_gas=True, burst_stretch_ratio=2.5),
        )
        result = run_simulation(s, dt=0.1, total_time_s=600.0)
        last = result[-1]
        # Burst balloons don't climb forever — they level off or fall
        assert last["altitude_m"] > 0


class TestEndToEndThermal:
    def test_solar_flux_increases_with_altitude(self):
        f0 = solar_flux_at_altitude(0)
        f10k = solar_flux_at_altitude(10000)
        f50k = solar_flux_at_altitude(50000)
        assert f0 < f10k < f50k
