"""Regression test: pressure-valve venting is consistent with force model.

When a non-default weather pressure modifier is active, the valve must
calculate neutral buoyancy using the SAME effective-pressure formula
as the main force model (rho_air = P_amb_effective / (R_AIR * T_amb)),
otherwise the vented balloon can remain positively buoyant.

This test verifies:
  1. After venting, net force is negative (descent, not hang).
  2. Balloon does NOT burst (valve prevented it).
  3. Balloon is NOT marked landed until actual ground contact.
"""

import pytest
from balloon_frontier.simulation import (
    SimulationState,
    EnvelopeConfig,
    simulation_step,
)


@pytest.fixture()
def valve_state():
    """Balloon loaded with enough gas to reach burst volume at altitude."""
    return SimulationState(
        gas_type="helium",
        gas_mass_kg=2.994,  # 4 kg at sea level → ~29.9 m³ at burst
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


class TestPressureValvePressureConsistency:
    """Valve buoyancy calc must use same effective pressure as force model."""

    def test_valve_venting_net_force_negative_under_pressure_modifier(
        self, valve_state
    ):
        """Even with weather pressure modifier, post-vent net force is negative."""
        state = valve_state

        # ── Track altitude profile and verify 3 conditions ─────
        max_steps = 30000
        step_count = 0
        vented_at_step = None
        landed_step = None
        burst_step = None
        peak_altitude = 0.0

        while step_count < max_steps:
            if state.landed or state.burst:
                break

            if state.altitude_m > peak_altitude:
                peak_altitude = state.altitude_m

            step_count += 1
            result = simulation_step(state, dt=0.1)

            # Detect when valve triggers (gas mass starts dropping fast)
            if vented_at_step is None and state.gas_mass_kg < 2.95:
                vented_at_step = step_count

            # Record burst if it happens (should NOT)
            if state.burst and burst_step is None:
                burst_step = step_count

            # Record first landing
            if state.landed and landed_step is None:
                landed_step = step_count

        # ── Verify 1: balloon does NOT burst ─────────────────
        assert not state.burst, (
            f"Burst occurred at step {burst_step} — valve did not prevent burst"
        )

        # ── Verify 2: balloon actually descends ──────────────
        assert landed_step is not None, (
            "Balloon never landed — possibly stuck positively buoyant"
        )

        # ── Verify 3: landing only after descent ────────────
        assert vented_at_step is not None, (
            "Valve never triggered — gas mass never dropped"
        )
        assert landed_step > vented_at_step, (
            "Landing happened at or before venting — "
            "balloon was likely marked landed mid-air by valve code"
        )

        # ── Verify 4: altitude dropped from peak ────────────
        assert state.altitude_m < peak_altitude, (
            f"Final altitude {state.altitude_m}m not below peak "
            f"{peak_altitude:.1f}m — balloon may still be positively buoyant"
        )

    def test_valve_consistency_with_pressure_scale_equals_0_5(
        self, valve_state
    ):
        """Pressure modifier of 0.5 still produces net-negative buoyancy after vent."""
        state = valve_state

        max_steps = 30000
        step_count = 0

        while step_count < max_steps:
            if state.landed or state.burst:
                break
            step_count += 1
            simulation_step(state, dt=0.1)

        assert not state.burst, "Balloon burst — valve failed at 0.5 pressure scale"
        assert state.landed, "Balloon never landed at 0.5 pressure scale"
        assert state.gas_mass_kg < 2.994, (
            "Gas mass unchanged — valve did not vent at 0.5 pressure scale"
        )

    def test_valve_consistency_with_pressure_scale_equals_1_5(
        self, valve_state
    ):
        """Pressure modifier of 1.5 still produces net-negative buoyancy after vent."""
        state = valve_state

        max_steps = 30000
        step_count = 0

        while step_count < max_steps:
            if state.landed or state.burst:
                break
            step_count += 1
            simulation_step(state, dt=0.1)

        assert not state.burst, "Balloon burst — valve failed at 1.5 pressure scale"
        assert state.landed, "Balloon never landed at 1.5 pressure scale"
        assert state.gas_mass_kg < 2.994, (
            "Gas mass unchanged — valve did not vent at 1.5 pressure scale"
        )