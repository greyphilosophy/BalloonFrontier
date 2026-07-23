"""Regression test: valve buoyancy calculation uses effective pressure consistently.

This test verifies that the pressure valve's neutral buoyancy calculation
uses the same effective-pressure formula as the main force model, so that
weather pressure modifiers don't cause the post-vent balloon to remain
positively buoyant (and thus fail to land).

Key expectations:
  1. After venting, net buoyant force is negative (descent, not hang).
  2. The balloon does NOT burst (valve prevented it).
  3. The balloon is NOT marked landed until actual ground contact.
  4. Even with non-default pressure modifiers (0.5, 1.5), the behavior holds.
"""

import pytest
from balloon_frontier.simulation import (
    SimulationState,
    EnvelopeConfig,
    simulation_step,
    run_simulation,
)


class TestValveBuoyancyConsistency:
    """Ensure valve buoyancy calc matches force model under pressure modifiers."""

    def test_valve_venting_produces_negative_buoyancy(self):
        """After valve venting, balloon is negatively buoyant and descends.

        This is the core regression: the valve calculates target_gas_kg using
        the same effective-pressure formula as the force model, so after venting
        the balloon's net buoyant force is definitively negative.
        """
        state = SimulationState(
            gas_type="helium",
            gas_mass_kg=2.994,
            envelope=EnvelopeConfig(
                max_volume_m3=10.0,
                burst_stretch_ratio=2.5,  # burst at 25 m³
                drag_coefficient=0.47,
                permeability=0.001,
                mass_kg=0.5,
                contained_gas=True,
            ),
            payload_mass_kg=10.0,
            ballast_mass_kg=0.0,
            terrain_base_altitude_offset_m=0.0,
            gas_temperature_k=293.15,
            has_pressure_valve=True,
        )

        # Run simulation until landing or burst
        telemetry = run_simulation(state, total_time_s=3600.0, max_steps=30000)
        last = telemetry[-1]

        # Valve prevented burst
        assert not last.get("burst", False), (
            "Balloon burst — valve failed to prevent burst"
        )

        # Balloon actually lands (not stuck hovering at altitude)
        assert last.get("landed", False), (
            "Balloon never landed after venting — "
            "possibly stuck positively buoyant due to pressure formula mismatch"
        )

        # Valve actually vented gas
        assert state.gas_mass_kg < 2.994, (
            "Gas mass unchanged — valve did not vent"
        )

        # Final altitude is at ground (0.0)
        assert last.get("final_alt", state.altitude_m) == 0.0, (
            "Balloon not at ground level"
        )

    def test_valve_under_pressure_scale_0_5(self):
        """Pressure modifier of 0.5 still produces net-negative buoyancy.

        With lower ambient pressure (e.g., storm conditions), the valve must
        still vent enough gas to make the balloon descend.
        """
        state = SimulationState(
            gas_type="helium",
            gas_mass_kg=2.994,
            envelope=EnvelopeConfig(
                max_volume_m3=10.0,
                burst_stretch_ratio=2.5,
                drag_coefficient=0.47,
                permeability=0.001,
                mass_kg=0.5,
                contained_gas=True,
                weather_pressure_modifier=0.5,
            ),
            payload_mass_kg=10.0,
            ballast_mass_kg=0.0,
            terrain_base_altitude_offset_m=0.0,
            gas_temperature_k=293.15,
            has_pressure_valve=True,
        )

        telemetry = run_simulation(state, total_time_s=3600.0, max_steps=30000)
        last = telemetry[-1]

        assert not last.get("burst", False), (
            "Burst occurred under low pressure — valve failed"
        )
        assert last.get("landed", False), (
            "Balloon never landed under 0.5 pressure scale — "
            "buoyancy calc likely uses wrong formula"
        )

    def test_valve_under_pressure_scale_1_5(self):
        """Pressure modifier of 1.5 still produces net-negative buoyancy.

        With higher ambient pressure (e.g., high-pressure system), the valve
        must still vent appropriately.
        """
        state = SimulationState(
            gas_type="helium",
            gas_mass_kg=2.994,
            envelope=EnvelopeConfig(
                max_volume_m3=10.0,
                burst_stretch_ratio=2.5,
                drag_coefficient=0.47,
                permeability=0.001,
                mass_kg=0.5,
                contained_gas=True,
                weather_pressure_modifier=1.5,
            ),
            payload_mass_kg=10.0,
            ballast_mass_kg=0.0,
            terrain_base_altitude_offset_m=0.0,
            gas_temperature_k=293.15,
            has_pressure_valve=True,
        )

        telemetry = run_simulation(state, total_time_s=3600.0, max_steps=30000)
        last = telemetry[-1]

        assert not last.get("burst", False), (
            "Burst occurred under high pressure — valve failed"
        )
        assert last.get("landed", False), (
            "Balloon never landed under 1.5 pressure scale — "
            "buoyancy calc likely uses wrong formula"
        )

    def test_valve_no_early_landing_mark(self):
        """Valve must not set landed=True mid-air.

        The balloon should only land when it reaches ground altitude,
        not when the valve activates. This is the original review blocker.
        """
        state = SimulationState(
            gas_type="helium",
            gas_mass_kg=2.994,
            envelope=EnvelopeConfig(
                max_volume_m3=10.0,
                burst_stretch_ratio=2.5,
                drag_coefficient=0.47,
                permeability=0.001,
                mass_kg=0.5,
                contained_gas=True,
            ),
            payload_mass_kg=10.0,
            ballast_mass_kg=0.0,
            terrain_base_altitude_offset_m=0.0,
            gas_temperature_k=293.15,
            has_pressure_valve=True,
        )

        # Run step by step to detect when valve activates
        max_steps = 30000
        step_count = 0
        vented_at_step = None
        landed_at_step = None
        peak_alt = 0.0

        while step_count < max_steps:
            if state.landed or state.burst:
                break

            step_count += 1
            result = simulation_step(state, dt=0.1)

            # Track peak altitude
            if state.altitude_m > peak_alt:
                peak_alt = state.altitude_m

            # Detect valve activation (gas mass drops significantly)
            if vented_at_step is None and state.gas_mass_kg < 2.90:
                vented_at_step = step_count

            # Detect first landing
            if state.landed and landed_at_step is None:
                landed_at_step = step_count

        # Must not burst
        assert not state.burst, (
            f"Burst at step {step_count} — valve did not prevent burst"
        )

        # Must eventually land
        assert landed_at_step is not None, (
            "Never landed — balloon stuck in air"
        )

        # Landing must occur AFTER valve activation
        assert vented_at_step is not None, (
            "Valve never triggered — no step data"
        )
        assert landed_at_step > vented_at_step, (
            f"Landed at step {landed_at_step}, same step as vent ({vented_at_step}) — "
            "valve marked balloon landed mid-air, preventing descent"
        )

        # Altitude must have dropped from peak after venting
        assert state.altitude_m < peak_alt, (
            f"Final alt {state.altitude_m:.1f}m not below peak {peak_alt:.1f}m — "
            "balloon did not descend after valve activation"
        )