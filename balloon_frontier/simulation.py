"""Balloon Frontier - Simulation Engine

Implements the deterministic fixed-step vertical balloon simulation.
Reference: GDD Sections 6.1, 6.4, 6.5, 6.8, 16.

Uses semi-implicit Euler integration with configurable time step.
All units are SI (meters, kilograms, seconds, Kelvin, Pascals).
"""

import math
from dataclasses import dataclass, field
from typing import List

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
    G,
)


@dataclass
class EnvelopeConfig:
    """Configuration for a balloon envelope.

    Attributes:
        max_volume_m3: Maximum volume the envelope can hold before becoming volume-limited.
        burst_stretch_ratio: Ratio of burst volume to nominal max volume (e.g. 2.5 means
            a 10 m³ envelope bursts at 25 m³).
        drag_coefficient: Shape-specific drag coefficient (sphere ≈ 0.47).
        permeability: Fraction of gas mass lost per second at sea-level pressure (simple model).
        mass_kg: Dry mass of the envelope material.
        contained_gas: If True (superpressure/latex), gas is contained and volume
            expands freely up to burst. If False (zero-pressure), excess gas vents.
    """
    max_volume_m3: float = 10.0
    burst_stretch_ratio: float = 2.5
    drag_coefficient: float = 0.47
    permeability: float = 0.001  # per second
    mass_kg: float = 1.0
    contained_gas: bool = False


@dataclass
class SimulationState:
    """Mutable state for one balloon vehicle during a simulation tick.

    This mirrors the VehicleState and GasCompartmentState from GDD §13.3,
    simplified for vertical-only flight.
    """
    # ── Position / Kinematics ────────────────────────────────
    altitude_m: float = 0.0
    velocity_mps: float = 0.0         # positive = ascending

    # ── Gas compartment ─────────────────────────────────────
    gas_type: str = "helium"
    gas_mass_kg: float = 1.0
    gas_temperature_k: float = 288.15
    # Internal pressure for the compartment (equals ambient for zero-pressure envelopes)
    gas_pressure_pa: float = 101325.0

    # ── Vehicle mass ─────────────────────────────────────────
    payload_mass_kg: float = 10.0
    ballast_mass_kg: float = 5.0

    # ── Envelope ─────────────────────────────────────────────
    envelope: EnvelopeConfig = field(default_factory=EnvelopeConfig)

    # ── Venting / Leakage ───────────────────────────────────
    # Vent valve open flag; when True, excess gas mass above max_volume is vented
    vent_open: bool = False
    vent_rate_kg_per_s: float = 0.05  # max vent flow rate

    # ── Ballast release ─────────────────────────────────────
    ballast_released_kg: float = 0.0  # cumulative

    # ── Simulation clock ────────────────────────────────────
    time_s: float = 0.0

    # ── Flags ───────────────────────────────────────────────
    burst: bool = False
    landed: bool = False  # altitude drops back to 0 with downward velocity
    crashed: bool = False  # altitude reaches sea level with high speed

    def total_mass(self) -> float:
        """Total vehicle mass (gas + envelope + payload + remaining ballast)."""
        ballast = max(0.0, self.ballast_mass_kg - self.ballast_released_kg)
        return self.gas_mass_kg + self.envelope.mass_kg + self.payload_mass_kg + ballast


def _compute_forces(state: SimulationState) -> tuple:
    """Compute the vertical forces acting on the balloon.

    Returns: (F_buoyancy, F_weight, F_drag, net_vertical_force) in Newtons.

    Physics model:
    - Gas volume is computed from ideal gas law
    - For zero-pressure envelopes, displaced volume is min(ideal_volume, max_volume)
    - Buoyancy scales with displaced volume
    - Drag opposes velocity direction
    """
    # Gas volume — ideal gas law
    P_amb = atmosphere_pressure(max(0.0, state.altitude_m))
    gas_vol = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        P_amb,
    )
    # Determine displaced volume based on envelope type:
    # - Contained (latex/superpressure): gas volume IS the displaced volume
    # - Zero-pressure: gas vents at max_volume, displaced = min(ideal, max)
    if state.envelope.contained_gas:
        displaced_vol = gas_vol
    else:
        displaced_vol = min(gas_vol, state.envelope.max_volume_m3)

    # Buoyancy on displaced volume
    rho_air = atmosphere_density(max(0.0, state.altitude_m))
    rho_gas = gas_density(state.gas_type, state.gas_temperature_k, P_amb)
    F_buoy = (rho_air - rho_gas) * G * displaced_vol

    # Weight
    F_weight = state.total_mass() * G

    # Drag — uses spherical_area based on displaced volume
    area = spherical_area(displaced_vol)
    F_drag = drag_force(
        state.velocity_mps,
        max(0.0, state.altitude_m),
        state.envelope.drag_coefficient,
        area,
    )
    # Drag opposes motion
    drag_sign = -1.0 if state.velocity_mps > 0 else (1.0 if state.velocity_mps < 0 else 0.0)
    F_drag_vertical = F_drag * drag_sign

    F_net = F_buoy + F_drag_vertical - F_weight
    return F_buoy, F_weight, F_drag_vertical, F_net


def simulation_step(state: SimulationState, dt: float = 0.1) -> dict:
    """Execute one fixed-step simulation tick using semi-implicit Euler.

    Semi-implicit Euler (symplectic):
        velocity += acceleration * dt
        position += velocity * dt     (uses the *updated* velocity)

    Returns a dict of intermediate values for telemetry.
    """
    # ── 1. Compute forces at current state ──────────────────
    F_buoy, F_weight, F_drag, F_net = _compute_forces(state)

    # ── 2. Update velocity (semi-implicit Euler) ───────────
    if state.total_mass() > 0:
        acceleration = F_net / state.total_mass()
    else:
        acceleration = 0.0
    state.velocity_mps += acceleration * dt

    # ── 3. Update altitude ─────────────────────────────────
    state.altitude_m += state.velocity_mps * dt

    # ── 4. Gas leakage (permeability model) ────────────────
    P_amb = atmosphere_pressure(max(0.0, state.altitude_m))
    leak_fraction = state.envelope.permeability * dt
    state.gas_mass_kg *= max(0.0001, 1.0 - leak_fraction)

    # ── 5. Venting: only zero-pressure envelopes vent overflow
    #    Contained (latex/superpressure) envelopes keep expanding
    if not state.envelope.contained_gas:
        gas_vol = gas_volume(
            state.gas_mass_kg,
            state.gas_type,
            state.gas_temperature_k,
            P_amb,
        )
        if gas_vol > state.envelope.max_volume_m3:
            state.gas_mass_kg = state.gas_mass_kg * state.envelope.max_volume_m3 / gas_vol

    # ── 6. Burst detection (for contained envelopes) ─────────
    gas_vol_after = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        P_amb,
    )
    burst_vol_limit = state.envelope.max_volume_m3 * state.envelope.burst_stretch_ratio
    if state.envelope.contained_gas and gas_vol_after >= burst_vol_limit:
        state.burst = True

    # ── 7. Landing / Crash detection ───────────────────────
    # Landing: altitude drops below zero while descending
    if state.altitude_m <= 0.0 and state.velocity_mps < 0.0:
        state.altitude_m = 0.0
        state.landed = True
        if abs(state.velocity_mps) > 15.0:
            state.crashed = True

    # ── 8. Advance clock ──────────────────────────────────
    state.time_s += dt

    # ── Telemetry snapshot ─────────────────────────────────
    gas_vol_current = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        atmosphere_pressure(max(0.0, state.altitude_m)),
    )
    F_buoy_after, F_weight_after, F_drag_after, F_net_after = _compute_forces(state)

    telemetry = {
        "time_s": state.time_s,
        "altitude_m": state.altitude_m,
        "velocity_mps": state.velocity_mps,
        "gas_volume_m3": gas_vol_current,
        "ambient_pressure_pa": atmosphere_pressure(max(0.0, state.altitude_m)),
        "ambient_temperature_k": atmosphere_temperature(max(0.0, state.altitude_m)),
        "net_lift_N": F_net_after,
        "buoyancy_N": F_buoy_after,
        "weight_N": F_weight_after,
        "drag_N": F_drag_after,
        "gas_mass_kg": state.gas_mass_kg,
        "total_mass_kg": state.total_mass(),
        "burst": state.burst,
        "landed": state.landed,
        "crashed": state.crashed,
    }

    return telemetry


def run_simulation(
    state: SimulationState,
    dt: float = 0.1,
    total_time_s: float = 60.0,
    max_steps: int = 10000,
) -> List[dict]:
    """Run the simulation for total_time_s seconds and return telemetry list.

    The simulation stops early if the balloon bursts, lands, or crashes.
    """
    telemetry = []
    step = 0
    while step * dt < total_time_s and step < max_steps:
        if state.burst or state.landed or state.crashed:
            break
        tick = simulation_step(state, dt)
        telemetry.append(tick)
        step += 1

    return telemetry
