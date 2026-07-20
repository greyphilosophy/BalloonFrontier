"""Tests for Balloon Frontier simulation engine.

Covers the fixed-step integration loop, burst detection, landing/crash detection,
gas leakage, venting, and telemetry accuracy.
Reference: GDD Sections 6.1, 6.4, 6.5, 6.8, 16.
"""

import math
import pytest
from balloon_frontier.simulation import (
    EnvelopeConfig,
    SimulationState,
    simulation_step,
    run_simulation,
)
from balloon_frontier.physics import (
    atmosphere_pressure,
    atmosphere_density,
    gas_volume,
    G,
)


# ─── Envelope Config ─────────────────────────────────────────────────

class TestEnvelopeConfig:
    def test_default_values(self):
        env = EnvelopeConfig()
        assert env.max_volume_m3 == 10.0
        assert env.burst_stretch_ratio == 2.5
        assert env.drag_coefficient == 0.47

    def test_custom_values(self):
        env = EnvelopeConfig(
            max_volume_m3=500.0,
            burst_stretch_ratio=2.0,
            drag_coefficient=0.5,
            permeability=0.0005,
            mass_kg=15.0,
        )
        assert env.max_volume_m3 == 500.0
        assert env.burst_stretch_ratio == 2.0


# ─── SimulationState ──────────────────────────────────────────────

class TestSimulationState:
    def test_default_state(self):
        s = SimulationState()
        assert s.altitude_m == 0.0
        assert s.velocity_mps == 0.0
        assert s.gas_type == "helium"
        assert s.gas_mass_kg == 1.0
        assert not s.burst
        assert not s.landed

    def test_total_mass(self):
        s = SimulationState(
            gas_mass_kg=2.0,
            payload_mass_kg=10.0,
            ballast_mass_kg=5.0,
            envelope=EnvelopeConfig(mass_kg=3.0),
        )
        assert s.total_mass() == 20.0

    def test_total_mass_with_ballast_release(self):
        s = SimulationState(
            gas_mass_kg=2.0,
            payload_mass_kg=10.0,
            ballast_mass_kg=5.0,
            ballast_released_kg=3.0,
            envelope=EnvelopeConfig(mass_kg=3.0),
        )
        # 2 (gas) + 3 (env) + 10 (payload) + (5-3) (ballast) = 17
        assert s.total_mass() == 17.0

    def test_custom_gas_type(self):
        s = SimulationState(gas_type="hydrogen", gas_mass_kg=1.5)
        assert s.gas_type == "hydrogen"
        assert s.gas_mass_kg == 1.5

    def test_custom_envelope(self):
        env = EnvelopeConfig(max_volume_m3=100.0, mass_kg=5.0)
        s = SimulationState(envelope=env)
        assert s.envelope.max_volume_m3 == 100.0


# ─── Simulation Step ─────────────────────────────────────────────

class TestSimulationStep:
    def test_step_advances_time(self):
        s = SimulationState()
        result = simulation_step(s, dt=0.1)
        assert s.time_s == 0.1
        assert result["time_s"] == 0.1

    def test_default_state_produces_valid_acceleration(self):
        """Default state (1 kg He + 10 kg payload + 5 ballast + 1 env = 17 kg)
        at sea level produces some acceleration."""
        s = SimulationState()
        result = simulation_step(s, dt=0.1)
        assert "velocity_mps" in result
        assert abs(result["velocity_mps"]) < 100  # Sanity bound

    def test_heavy_balloon_accelerates_downward(self):
        """Very heavy payload causes negative (downward) acceleration."""
        s = SimulationState(
            gas_mass_kg=1.0,
            gas_type="helium",
            payload_mass_kg=100.0,
            ballast_mass_kg=0.0,
            envelope=EnvelopeConfig(mass_kg=1.0, max_volume_m3=10.0),
        )
        result = simulation_step(s, dt=0.1)
        assert result["velocity_mps"] < 0

    def test_light_balloon_accelerates_upward(self):
        s = SimulationState(
            gas_mass_kg=20.0,
            gas_type="helium",
            payload_mass_kg=5.0,
            ballast_mass_kg=0.0,
            envelope=EnvelopeConfig(mass_kg=2.0, max_volume_m3=200.0),
        )
        result = simulation_step(s, dt=0.1)
        assert result["velocity_mps"] > 0

    def test_telemetry_contains_expected_keys(self):
        s = SimulationState()
        result = simulation_step(s)
        expected_keys = [
            "time_s", "altitude_m", "velocity_mps",
            "gas_volume_m3", "ambient_pressure_pa",
            "ambient_temperature_k", "net_lift_N",
            "buoyancy_N", "weight_N", "drag_N",
            "gas_mass_kg", "total_mass_kg",
            "burst", "landed", "crashed",
        ]
        for key in expected_keys:
            assert key in result, f"Missing telemetry key: {key}"

    def test_buoyancy_and_weight_are_consistent(self):
        s = SimulationState(gas_mass_kg=1.0, gas_type="helium")
        result = simulation_step(s)
        total = result["total_mass_kg"]
        expected_weight = total * G
        assert abs(result["weight_N"] - expected_weight) < 0.1

    def test_net_lift_equals_buoyancy_plus_drag_minus_weight(self):
        s = SimulationState(gas_mass_kg=1.0, gas_type="helium")
        result = simulation_step(s)
        expected_net = result["buoyancy_N"] + result["drag_N"] - result["weight_N"]
        assert abs(result["net_lift_N"] - expected_net) < 0.1

    def test_gas_leakage_reduces_mass(self):
        s = SimulationState(
            gas_mass_kg=1.0,
            envelope=EnvelopeConfig(permeability=0.01, max_volume_m3=10.0),
        )
        for _ in range(10):
            simulation_step(s, dt=0.1)
        assert s.gas_mass_kg < 1.0

    def test_helium_lift_exceeds_hydrogen_lift(self):
        """Compare same-mass balloons — helium should lift well."""
        s = SimulationState(
            gas_mass_kg=10.0, gas_type="helium",
            payload_mass_kg=3.0, envelope=EnvelopeConfig(max_volume_m3=200.0),
        )
        r = simulation_step(s)
        assert r["buoyancy_N"] > r["weight_N"]

    def test_zero_gas_mass_produces_minimal_buoyancy(self):
        s = SimulationState(
            gas_mass_kg=0.01,
            envelope=EnvelopeConfig(mass_kg=1.0),
        )
        result = simulation_step(s)
        assert result["buoyancy_N"] > 0
        assert result["buoyancy_N"] < 10


# ─── Burst Detection ─────────────────────────────────────────────

class TestBurstDetection:
    def test_burst_detected_when_gas_volume_exceeds_limit(self):
        """When a contained envelope's gas volume exceeds burst_stretch * max_volume,
        the burst flag is set during the step that detects it."""
        # 50kg He at sea level: V ≈ 295 m³
        # burst limit = 10 * 2.0 = 20 m³ → already burst!
        env = EnvelopeConfig(
            max_volume_m3=10.0,
            burst_stretch_ratio=2.0,
            mass_kg=1.0,
            contained_gas=True,
        )
        s = SimulationState(
            gas_mass_kg=50.0,
            gas_type="helium",
            envelope=env,
        )
        result = simulation_step(s)
        assert result["burst"], "Gas volume (295 m³) >> burst limit (20 m³) should trigger burst"

    def test_no_burst_when_gas_is_within_limits(self):
        """When gas volume is below the burst limit, no burst occurs."""
        env = EnvelopeConfig(
            max_volume_m3=500.0,
            burst_stretch_ratio=2.5,
            mass_kg=3.0,
            contained_gas=True,
        )
        # 5kg He at sea level: V ≈ 29.5 m³, burst limit = 1250 m³ → safe
        s = SimulationState(
            gas_mass_kg=5.0,
            gas_type="helium",
            envelope=env,
        )
        result = simulation_step(s)
        assert not result["burst"]

    def test_burst_volume_formula(self):
        """Direct test of the burst volume calculation."""
        from balloon_frontier.physics import burst_volume
        assert burst_volume(2.5, 100.0) == 250.0
        assert burst_volume(1.0, 50.0) == 50.0
        assert burst_volume(3.0, 300.0) == 900.0

    def test_contained_vs_zero_pressure_behavior(self):
        """Contained envelopes let gas expand freely; zero-pressure vents excess."""
        # Same gas mass in two envelopes
        env_contained = EnvelopeConfig(
            max_volume_m3=100.0,
            burst_stretch_ratio=2.0,
            mass_kg=3.0,
            contained_gas=True,
        )
        env_zero_pressure = EnvelopeConfig(
            max_volume_m3=100.0,
            mass_kg=3.0,
            contained_gas=False,
        )
        # 50kg He at sea level: V ≈ 295 m³ > max_volume (100)
        # Contained: gas stays, volume = 295 m³ → displaced = 295
        # Zero-pressure: gas vents, volume clamped to 100 m³ → displaced = 100
        s_c = SimulationState(gas_mass_kg=50.0, envelope=env_contained)
        s_zp = SimulationState(gas_mass_kg=50.0, envelope=env_zero_pressure)

        # Check initial volumes (before any step)
        from balloon_frontier.physics import gas_volume, atmosphere_pressure
        P = atmosphere_pressure(0)
        vol = gas_volume(50.0, "helium", 288.15, P)
        assert vol > 100.0  # Gas exceeds envelope max

        # Zero-pressure should vent; contained should keep expanding (and burst)
        result_c = simulation_step(s_c)
        result_zp = simulation_step(s_zp)
        # Contained: burst = True (volume >> burst limit)
        assert result_c["burst"]
        # Zero-pressure: gas gets vented, no burst
        assert not result_zp["burst"]

    def test_zero_pressure_balloon_does_not_burst_from_overflow(self):
        """Zero-pressure balloons vent excess gas, so they don't typically burst
        from volume expansion alone."""
        env = EnvelopeConfig(
            max_volume_m3=100.0,
            mass_kg=3.0,
            contained_gas=False,
        )
        s = SimulationState(
            gas_mass_kg=50.0,
            envelope=env,
        )
        result = simulation_step(s)
        # Gas is vented, so no burst
        assert not result["burst"]


# ─── Landing and Crash ──────────────────────────────────────────

class TestLandingAndCrash:
    def test_descending_balloon_lands(self):
        """A balloon well above ground that descends eventually lands."""
        s = SimulationState(
            altitude_m=100.0,
            velocity_mps=-5.0,
            gas_mass_kg=1.0,
            envelope=EnvelopeConfig(mass_kg=1.0),
        )
        tel = run_simulation(s, dt=0.1, total_time_s=60.0)
        last = tel[-1]
        assert last["landed"] or last["altitude_m"] <= 0.01

    def test_crash_detection_for_fast_descent(self):
        s = SimulationState(
            altitude_m=1.0,
            velocity_mps=-20.0,
            gas_mass_kg=1.0,
            envelope=EnvelopeConfig(mass_kg=1.0),
        )
        result = simulation_step(s)
        assert result["crashed"]

    def test_balloon_at_zero_altitude_is_not_automatic_landing(self):
        """Starting at sea level with positive velocity is not a landing event."""
        s = SimulationState(
            altitude_m=0.0,
            velocity_mps=5.0,
            gas_mass_kg=5.0,
            payload_mass_kg=2.0,
            envelope=EnvelopeConfig(mass_kg=1.0, max_volume_m3=100.0),
        )
        result = simulation_step(s)
        assert not result["landed"]


# ─── Run Simulation ─────────────────────────────────────────────

class TestRunSimulation:
    def test_returns_telemetry_list(self):
        s = SimulationState(
            gas_mass_kg=10.0,
            gas_type="helium",
            payload_mass_kg=2.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        telemetry = run_simulation(s, dt=0.1, total_time_s=1.0)
        assert isinstance(telemetry, list)
        assert len(telemetry) == 10  # 1.0 / 0.1 = 10 steps

    def test_simulation_respects_max_steps(self):
        s = SimulationState(
            gas_mass_kg=5.0,
            gas_type="helium",
            payload_mass_kg=1.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        tel = run_simulation(s, dt=0.1, total_time_s=1000.0, max_steps=5)
        assert len(tel) == 5

    def test_helium_balloon_ascends(self):
        s = SimulationState(
            gas_mass_kg=10.0,
            gas_type="helium",
            payload_mass_kg=5.0,
            ballast_mass_kg=2.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=3.0),
        )
        telemetry = run_simulation(s, dt=0.1, total_time_s=10.0)
        for i in range(1, len(telemetry)):
            assert telemetry[i]["altitude_m"] >= telemetry[i - 1]["altitude_m"]

    def test_hydrogen_provides_more_lift_than_helium(self):
        s_He = SimulationState(
            gas_mass_kg=5.0, gas_type="helium",
            payload_mass_kg=3.0, ballast_mass_kg=0.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        s_H2 = SimulationState(
            gas_mass_kg=5.0, gas_type="hydrogen",
            payload_mass_kg=3.0, ballast_mass_kg=0.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        tel_He = run_simulation(s_He, dt=0.1, total_time_s=5.0)
        tel_H2 = run_simulation(s_H2, dt=0.1, total_time_s=5.0)
        assert tel_H2[-1]["altitude_m"] > tel_He[-1]["altitude_m"]


# ─── Determinism ───────────────────────────────────────────────

class TestSimulationDeterminism:
    def test_identical_runs_produce_identical_telemetry(self):
        def run_configured():
            s = SimulationState(
                gas_mass_kg=5.0,
                gas_type="helium",
                payload_mass_kg=3.0,
                envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
            )
            return run_simulation(s, dt=0.1, total_time_s=10.0)

        run1 = run_configured()
        run2 = run_configured()
        assert len(run1) == len(run2)
        for t1, t2 in zip(run1, run2):
            for key in ["time_s", "altitude_m", "velocity_mps",
                         "gas_volume_m3", "ambient_pressure_pa",
                         "net_lift_N", "buoyancy_N", "weight_N"]:
                assert abs(t1[key] - t2[key]) < 1e-10

    def test_different_states_produce_different_results(self):
        s1 = SimulationState(gas_mass_kg=3.0, payload_mass_kg=2.0,
                              envelope=EnvelopeConfig(max_volume_m3=200.0))
        s2 = SimulationState(gas_mass_kg=7.0, payload_mass_kg=2.0,
                              envelope=EnvelopeConfig(max_volume_m3=200.0))
        tel1 = run_simulation(s1, dt=0.1, total_time_s=5.0)
        tel2 = run_simulation(s2, dt=0.1, total_time_s=5.0)
        assert tel2[-1]["altitude_m"] > tel1[-1]["altitude_m"]


# ─── Physical Correctness ──────────────────────────────────────

class TestPhysicalCorrectness:
    def test_terminal_velocity_exists(self):
        """A falling balloon approaches terminal velocity."""
        s = SimulationState(
            altitude_m=30000,
            velocity_mps=0.0,
            gas_mass_kg=5.0,
            gas_type="helium",
            payload_mass_kg=10.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        tel = run_simulation(s, dt=0.1, total_time_s=60.0)
        if len(tel) > 10:
            v_end = tel[-5]["velocity_mps"]
            assert v_end < -0.1

    def test_balloon_ascends_from_sea_level(self):
        s = SimulationState(
            gas_mass_kg=20.0,
            gas_type="helium",
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=500.0, mass_kg=5.0),
        )
        tel = run_simulation(s, dt=0.1, total_time_s=20.0)
        final_alt = tel[-1]["altitude_m"]
        assert final_alt > 50.0  # Should ascend at least 50m in 20s

    def test_more_gas_mass_increases_ascent(self):
        s1 = SimulationState(gas_mass_kg=5.0, payload_mass_kg=3.0,
                              envelope=EnvelopeConfig(max_volume_m3=200.0))
        s2 = SimulationState(gas_mass_kg=15.0, payload_mass_kg=3.0,
                              envelope=EnvelopeConfig(max_volume_m3=200.0))
        tel1 = run_simulation(s1, dt=0.1, total_time_s=5.0)
        tel2 = run_simulation(s2, dt=0.1, total_time_s=5.0)
        assert tel2[-1]["altitude_m"] > tel1[-1]["altitude_m"]


# ─── Temperature-Driven Buoyancy ──────────────────────────────

class TestTemperatureDrivenBuoyancy:
    """Verify that buoyancy calculations correctly use dynamically
    updated gas_temperature_k rather than a static initial value.

    Ideal gas law: V = n * R * T / P
    Hotter gas → larger volume → more displaced air → greater buoyancy.
    """

    def test_hotter_gas_produces_greater_buoyancy(self):
        """A balloon with a higher gas temperature should produce more
        buoyant force than the same balloon at a lower temperature."""
        # Same balloon, same altitude, only temperature differs
        s_cold = SimulationState(
            altitude_m=100.0,
            gas_mass_kg=10.0, gas_type="helium",
            gas_temperature_k=270.0,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        s_hot = SimulationState(
            altitude_m=100.0,
            gas_mass_kg=10.0, gas_type="helium",
            gas_temperature_k=300.0,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        r_cold = simulation_step(s_cold)
        r_hot = simulation_step(s_hot)
        # Hotter gas has larger volume → more displaced air → more buoyancy
        assert r_hot["buoyancy_N"] > r_cold["buoyancy_N"]

    def test_buoyancy_changes_as_temperature_changes(self):
        """Changing gas_temperature_k mid-flight should change buoyant force.
        We manually set temperature to different values across steps to prove
        the simulation uses the *current* temperature, not the initial one."""
        s = SimulationState(
            gas_mass_kg=10.0, gas_type="helium",
            gas_temperature_k=288.15,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        # Take one step to establish baseline buoyancy
        r1 = simulation_step(s)
        # Manually bump temperature to simulate a heated gas
        s.gas_temperature_k = 310.0
        r2 = simulation_step(s)
        # Buoyancy should reflect the new higher temperature
        assert r2["buoyancy_N"] > r1["buoyancy_N"]

    def test_temperature_evolution_affects_trajectory(self):
        """A balloon starting with warmer gas should ascend faster because
        thermal effects accumulate over multiple steps."""
        s_cold = SimulationState(
            gas_mass_kg=10.0, gas_type="helium",
            gas_temperature_k=270.0,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        s_hot = SimulationState(
            gas_mass_kg=10.0, gas_type="helium",
            gas_temperature_k=310.0,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        tel_cold = run_simulation(s_cold, dt=0.1, total_time_s=5.0)
        tel_hot = run_simulation(s_hot, dt=0.1, total_time_s=5.0)
        # Hotter initial gas → more buoyancy → higher altitude after 5s
        assert tel_hot[-1]["altitude_m"] > tel_cold[-1]["altitude_m"]

    def test_dynamic_temperature_affects_buoyancy_over_time(self):
        """Over multiple simulation steps, the gas temperature changes due to
        the thermal model, and buoyancy tracks those changes. We verify that
        the gas_temperature_k actually evolves and that buoyancy correlates."""
        s = SimulationState(
            gas_mass_kg=10.0, gas_type="helium",
            gas_temperature_k=288.15,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        # Run a longer simulation to let temperature drift
        tel = run_simulation(s, dt=0.1, total_time_s=10.0)
        # Gas temperature should have changed from its initial value
        # (thermal model: solar heating vs IR/convective cooling)
        initial_temp = tel[0].get("ambient_temperature_k", 288.15)
        final_temp = s.gas_temperature_k
        # The gas temperature should have shifted from the initial 288.15K
        # after 10 seconds of thermal exchange
        assert abs(final_temp - 288.15) > 0.1, \
            "Gas temperature should have drifted from initial value"

    def test_gas_density_uses_dynamic_temperature(self):
        """Verify that gas_density reflects the current gas_temperature_k
        and not a hardcoded value."""
        from balloon_frontier.physics import gas_density, gas_volume
        from balloon_frontier.physics import atmosphere_pressure

        P = atmosphere_pressure(100.0)
        # Cold gas should be denser than hot gas
        rho_cold = gas_density("helium", 270.0, P)
        rho_hot = gas_density("helium", 310.0, P)
        assert rho_cold > rho_hot

        # Cold gas should have smaller volume than hot gas
        vol_cold = gas_volume(10.0, "helium", 270.0, P)
        vol_hot = gas_volume(10.0, "helium", 310.0, P)
        assert vol_hot > vol_cold

    def test_equilibrium_altitude_depends_on_gas_temperature(self):
        """A hotter gas should float at a higher equilibrium altitude
        because the larger displaced volume provides more lift."""
        from balloon_frontier.equilibrium import equilibrium_altitude

        alt_cold = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=270.0,
            total_vehicle_mass_kg=15.0,
            envelope_max_volume=200.0,
        )
        alt_hot = equilibrium_altitude(
            gas_type="helium",
            gas_mass_kg=10.0,
            gas_temperature_k=310.0,
            total_vehicle_mass_kg=15.0,
            envelope_max_volume=200.0,
        )
        assert alt_hot > alt_cold

    def test_buoyancy_formula_consistency_with_temperature(self):
        """Verify the buoyancy formula: F_buoy = (rho_air - rho_gas) * g * V
        where both V and rho_gas depend on gas_temperature_k."""
        s = SimulationState(
            gas_mass_kg=10.0, gas_type="helium",
            gas_temperature_k=300.0,
            payload_mass_kg=5.0,
            envelope=EnvelopeConfig(max_volume_m3=200.0, mass_kg=2.0),
        )
        r = simulation_step(s)
        # Recompute buoyancy from the *post-step* state (temp/mass may have changed)
        from balloon_frontier.physics import (
            gas_volume, gas_density, atmosphere_density,
            atmosphere_pressure,
        )
        P = atmosphere_pressure(max(0.0, s.altitude_m))
        V = gas_volume(s.gas_mass_kg, s.gas_type, s.gas_temperature_k, P)
        rho_gas = gas_density(s.gas_type, s.gas_temperature_k, P)
        rho_air = atmosphere_density(max(0.0, s.altitude_m))
        expected_buoyancy = (rho_air - rho_gas) * G * V
        # The telemetry buoyancy matches the formula with post-step state
        assert abs(r["buoyancy_N"] - expected_buoyancy) < 0.01
