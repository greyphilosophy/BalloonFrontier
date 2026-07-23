"""Balloon Frontier - Simulation Engine

Implements a deterministic fixed-step balloon simulation.

The core model integrates vertical motion (buoyancy + vertical drag + weight).
Optionally, when `wind_enabled=True`, it also integrates a 1D horizontal drift
using aerodynamic drag against the relative air velocity in the x direction.

Reference: GDD Sections 6.1, 6.4, 6.5, 6.8, 16.

Uses semi-implicit Euler integration with configurable time step.
All units are SI (meters, kilograms, seconds, Kelvin, Pascals).
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional

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
    R_AIR,
)
from balloon_frontier.thermal import calculate_balloon_heat_flows, gas_temperature_update


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
        envelope_absorptivity: Solar absorptivity (0–1) of the envelope material.
        envelope_emissivity: IR emissivity (0–1) of the envelope material.
    """

    max_volume_m3: float = 10.0
    burst_stretch_ratio: float = 2.5
    drag_coefficient: float = 0.47
    permeability: float = 0.001  # per second
    mass_kg: float = 1.0
    contained_gas: bool = False
    envelope_absorptivity: float = 0.5
    envelope_emissivity: float = 0.8
    # Weather modifiers — applied at runtime by the weather system.
    weather_burst_risk_modifier: float = 1.0  # multiplier on burst probability
    weather_solar_modifier: float = 1.0       # multiplier on solar heating
    weather_pressure_modifier: float = 1.0    # ambient pressure scale factor
    weather_ascent_multiplier: float = 1.0    # ascent_rate: thermal/buoyancy multiplier
    weather_drift_multiplier: float = 1.0     # drift_factor: horizontal wind scaling


@dataclass
class SimulationState:
    """Mutable state for one balloon vehicle during a simulation tick."""

    # ── Position / Kinematics ────────────────────────────────
    altitude_m: float = 0.0
    velocity_mps: float = 0.0  # positive = ascending

    # Horizontal drift (east-west). Only affected when wind_enabled=True.
    x_m: float = 0.0
    vx_mps: float = 0.0

    # Compatibility fields (used by some higher-level game code / tests).
    terrain_base_altitude_offset_m: float = 0.0
    wind_enabled: bool = False
    wind_site_id: str = "field"

    # ── Weather modifiers (applied at runtime by the weather system) ──
    weather_ascent_multiplier: float = 1.0  # ascent_rate from weather_impact (~1.0)
    weather_drift_multiplier: float = 1.0   # drift_factor from weather_impact (~1.0)

    # ── Gas compartment ─────────────────────────────────────
    gas_type: str = "helium"
    gas_mass_kg: float = 1.0
    # Initial gas temperature.
    #
    # Callers may specify either:
    #   - gas_temperature_k (absolute, Kelvin), OR
    #   - gas_temperature_delta_k (dT in Kelvin), where:
    #       gas_temperature_k = ambient_temperature_k + gas_temperature_delta_k
    #
    # If neither is provided, gas_temperature_k defaults to the ambient
    # temperature at the initial altitude.
    gas_temperature_k: Optional[float] = None
    gas_temperature_delta_k: Optional[float] = None
    # Internal pressure for the compartment (equals ambient for zero-pressure envelopes)
    gas_pressure_pa: float = 101325.0

    # ── Vehicle mass ─────────────────────────────────────────
    payload_mass_kg: float = 10.0
    ballast_mass_kg: float = 5.0
    has_pressure_valve: bool = False  # Vent gas before burst when True

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

    def __post_init__(self) -> None:
        """Resolve the initial gas temperature from either absolute T_gas or dT."""
        # Reject ambiguous input: both absolute and delta specified.
        if (
            self.gas_temperature_k is not None
            and self.gas_temperature_delta_k is not None
        ):
            raise ValueError(
                "Specify either gas_temperature_k or "
                "gas_temperature_delta_k, not both"
            )

        ambient_temp_k = atmosphere_temperature(max(0.0, float(self.altitude_m)))

        if self.gas_temperature_k is not None:
            resolved = float(self.gas_temperature_k)
            if resolved <= 0.0:
                raise ValueError(
                    f"gas_temperature_k must be > 0 K, got {self.gas_temperature_k}"
                )
            self.gas_temperature_k = resolved
            return

        if self.gas_temperature_delta_k is not None:
            resolved = ambient_temp_k + float(self.gas_temperature_delta_k)
            if resolved <= 0.0:
                raise ValueError(
                    "gas_temperature_delta_k would resolve to "
                    f"gas_temperature_k <= 0 K (resolved={resolved})"
                )
            self.gas_temperature_k = resolved
            return

        # Default: ambient temperature at the initial altitude.
        self.gas_temperature_k = ambient_temp_k

        # Type narrowing for the rest of the simulation code.
        assert self.gas_temperature_k is not None

    def total_mass(self) -> float:
        """Total vehicle mass (gas + envelope + payload + remaining ballast)."""

        ballast = max(0.0, self.ballast_mass_kg - self.ballast_released_kg)
        return self.gas_mass_kg + self.envelope.mass_kg + self.payload_mass_kg + ballast


def _compute_forces(state: SimulationState) -> tuple:
    """Compute the vertical forces acting on the balloon.

    Returns:
        (F_buoyancy, F_weight, F_drag_vertical, net_vertical_force, area_m2)

    Where:
        - Drag uses drag_force(v, alt, Cd, area) with area derived from displaced volume.
    """

    # Get weather pressure scale (may differ from 1.0 due to pressure anomalies)
    pressure_scale = getattr(state.envelope, 'weather_pressure_modifier', 1.0)

    # Gas volume — ideal gas law with weather-modified pressure
    P_amb = atmosphere_pressure(max(0.0, state.altitude_m))
    P_amb_effective = P_amb * pressure_scale
    gas_vol = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        P_amb_effective,
    )

    # Determine displaced volume based on envelope type:
    # - Contained (latex/superpressure): gas volume IS the displaced volume
    # - Zero-pressure: gas vents at max_volume, displaced = min(ideal, max)
    if state.envelope.contained_gas:
        displaced_vol = gas_vol
    else:
        displaced_vol = min(gas_vol, state.envelope.max_volume_m3)

    # Buoyancy on displaced volume — both ambient air and gas use effective pressure
    # so the pressure_scale modifies them consistently (R_AIR * T_amb).
    T_amb = atmosphere_temperature(max(0.0, state.altitude_m))
    rho_air = P_amb_effective / (R_AIR * T_amb)
    rho_gas = gas_density(state.gas_type, state.gas_temperature_k, P_amb_effective)
    F_buoy = (rho_air - rho_gas) * G * displaced_vol

    # Weight
    F_weight = state.total_mass() * G

    # Drag — uses spherical_area based on displaced volume
    area_m2 = spherical_area(displaced_vol)
    F_drag = drag_force(
        state.velocity_mps,
        max(0.0, state.altitude_m),
        state.envelope.drag_coefficient,
        area_m2,
    )

    # Drag opposes motion
    drag_sign = -1.0 if state.velocity_mps > 0 else (1.0 if state.velocity_mps < 0 else 0.0)
    F_drag_vertical = F_drag * drag_sign

    F_net = F_buoy + F_drag_vertical - F_weight
    return F_buoy, F_weight, F_drag_vertical, F_net, area_m2


def simulation_step(state: SimulationState, dt: float = 0.1) -> dict:
    """Execute one fixed-step simulation tick using semi-implicit Euler.

    Semi-implicit Euler (symplectic):
        velocity += acceleration * dt
        position += velocity * dt     (uses the *updated* velocity)

    Returns a dict of intermediate values for telemetry.
    """

    # ── 1. Compute forces at current state ──────────────────
    altitude_m0 = float(state.altitude_m)
    time_s0 = float(state.time_s)

    F_buoy, F_weight, F_drag_vertical, F_net, area_m2 = _compute_forces(state)

    # Horizontal drag (wind-relative air velocity in x direction)
    # Scale the existing site wind vector by drift_factor (dimensionless modifier ~1.0)
    weather_drift_mult = getattr(state, 'weather_drift_multiplier', 1.0)
    from balloon_frontier.wind import wind_vector

    wind_vx_mps = 0.0
    if state.wind_enabled:
        wind_vx_mps, _wind_vy_mps = wind_vector(
            altitude_m0,
            time_s=time_s0,
            site_id=state.wind_site_id,
        )
    # Always apply drift scaling (even without site wind, this enables drift_factor)
    if weather_drift_mult != 1.0:
        wind_vx_mps *= weather_drift_mult

    v_rel_x_mps = float(state.vx_mps - wind_vx_mps)

    # drag_force returns a magnitude based on v^2.
    F_drag_x_mag = drag_force(
        v_rel_x_mps,
        max(0.0, altitude_m0),
        state.envelope.drag_coefficient,
        area_m2,
    )

    # Drag opposes *relative* horizontal motion.
    drag_x_sign = -1.0 if v_rel_x_mps > 0 else (1.0 if v_rel_x_mps < 0 else 0.0)
    F_drag_x = F_drag_x_mag * drag_x_sign

    # ── Weather: read modifiers from state ─────────────────
    weather_pressure_scale = getattr(state.envelope, 'weather_pressure_modifier', 1.0)
    weather_solar_mod = getattr(state.envelope, 'weather_solar_modifier', 1.0)
    weather_burst_mod = getattr(state.envelope, 'weather_burst_risk_modifier', 1.0)
    weather_drift_mult = getattr(state, 'weather_drift_multiplier', 1.0)

    # ── 2. Update velocity (semi-implicit Euler) ───────────
    if state.total_mass() > 0:
        acceleration_y = F_net / state.total_mass()
        acceleration_x = F_drag_x / state.total_mass()
    else:
        acceleration_y = 0.0
        acceleration_x = 0.0

    state.vx_mps += acceleration_x * dt
    state.x_m += state.vx_mps * dt

    state.velocity_mps += acceleration_y * dt

    # ── 3. Update altitude ─────────────────────────────────
    state.altitude_m += state.velocity_mps * dt

    # ── 4. Gas leakage (permeability model) ────────────────
    P_amb = atmosphere_pressure(max(0.0, state.altitude_m))
    P_amb_effective = P_amb * weather_pressure_scale  # Apply pressure scale
    leak_fraction = state.envelope.permeability * dt
    state.gas_mass_kg *= max(0.0001, 1.0 - leak_fraction)

    # ── 4b. Thermal equilibrium: update gas temperature ──
    gas_vol_before = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        P_amb_effective,
    )
    area = spherical_area(gas_vol_before)

    # Apply solar heating modifier from weather
    heat_flows = calculate_balloon_heat_flows(
        altitude_m=max(0.0, state.altitude_m),
        gas_temp_K=state.gas_temperature_k,
        gas_mass_kg=state.gas_mass_kg,
        gas_type=state.gas_type,
        envelope_absorptivity=state.envelope.envelope_absorptivity * weather_solar_mod,
        envelope_emissivity=state.envelope.envelope_emissivity,
        envelope_area_m2=area,
        envelope_mass_kg=state.envelope.mass_kg,
        heater_power_watts=0.0,
        equipment_heat_watts=0.0,
    )

    state.gas_temperature_k = gas_temperature_update(
        gas_type=state.gas_type,
        gas_mass_kg=state.gas_mass_kg,
        gas_temp_K=state.gas_temperature_k,
        heat_flows=heat_flows,
        dt=dt,
    )

    # ── 5. Venting: only zero-pressure envelopes vent overflow
    #    Contained (latex/superpressure) envelopes keep expanding
    if not state.envelope.contained_gas:
        gas_vol = gas_volume(
            state.gas_mass_kg,
            state.gas_type,
            state.gas_temperature_k,
            P_amb_effective,
        )
        if gas_vol > state.envelope.max_volume_m3:
            state.gas_mass_kg = state.gas_mass_kg * state.envelope.max_volume_m3 / gas_vol

    # ── 6. Burst detection (for contained envelopes) ─────────
    gas_vol_after = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        P_amb_effective,
    )
    # Apply weather burst risk modifier — hazardous conditions lower the effective burst threshold
    burst_vol_limit = state.envelope.max_volume_m3 * state.envelope.burst_stretch_ratio / weather_burst_mod
    
    # ── 6b. Pressure valve: prevent burst by venting gas ──
    # When equipped, the valve vents gas until the balloon becomes
    # slightly negatively buoyant, so normal physics produces a controlled
    # descent rather than a sustained positive-buoyancy hang.
    if state.has_pressure_valve and state.envelope.contained_gas and gas_vol_after >= burst_vol_limit:
        # Calculate the gas mass needed for neutral buoyancy at this altitude.
        # Neutral: (rho_air - rho_gas) * V_gas * g = total_non_gas * g
        # => gas_mass_neutral = non_gas_mass * rho_gas / (rho_air - rho_gas)
        rho_air = atmosphere_density(state.altitude_m)
        rho_gas = gas_density(state.gas_type, state.gas_temperature_k, P_amb_effective)
        non_gas_mass = (state.envelope.mass_kg + state.payload_mass_kg +
                        max(0.0, state.ballast_mass_kg - state.ballast_released_kg))
        if rho_air > rho_gas and non_gas_mass > 0:
            neutral_gas_kg = non_gas_mass * rho_gas / (rho_air - rho_gas)
        else:
            neutral_gas_kg = 0.0  # already neutrally/negatively buoyant or impossible

        # Vent to 90% of neutral gas mass → slight negative buoyancy → descent
        target_gas_kg = max(0.001, neutral_gas_kg * 0.90)

        # Vent in iterations until we reach the target mass.
        # NOTE: do NOT use volume to gate the loop — at altitude the volume
        # shrinks (lower pressure) even though the balloon is still positively
        # buoyant.  The real control is gas mass.
        while state.gas_mass_kg > target_gas_kg:
            vent_mass = state.gas_mass_kg * 0.05  # vent 5% per iteration
            state.gas_mass_kg -= vent_mass
            state.gas_mass_kg = max(0.001, state.gas_mass_kg)
            gas_vol_after = gas_volume(
                state.gas_mass_kg,
                state.gas_type,
                state.gas_temperature_k,
                P_amb_effective,
            )

    # Only check for burst if valve is NOT equipped
    if not state.has_pressure_valve and state.envelope.contained_gas and gas_vol_after >= burst_vol_limit:
        state.burst = True

    # ── 7. Landing / Crash detection ───────────────────────
    ground_alt_m = float(state.terrain_base_altitude_offset_m)
    relative_alt_m = state.altitude_m - ground_alt_m

    # Landing: relative altitude drops to/below 0 while descending
    if relative_alt_m <= 0.0 and state.velocity_mps < 0.0:
        state.altitude_m = ground_alt_m
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

    F_buoy_after, F_weight_after, F_drag_after, F_net_after, area_after_m2 = _compute_forces(state)

    # Horizontal drag for telemetry snapshot (same drift scaling)
    if state.wind_enabled:
        from balloon_frontier.wind import wind_vector

        wind_vx_mps_after, _wind_vy_mps_after = wind_vector(
            float(state.altitude_m),
            time_s=float(state.time_s),
            site_id=state.wind_site_id,
        )
        wind_vx_mps_after *= weather_drift_mult  # Apply same drift scaling to telemetry
    else:
        wind_vx_mps_after = 0.0

    v_rel_x_after_mps = float(state.vx_mps - wind_vx_mps_after)
    F_drag_x_mag_after = drag_force(
        v_rel_x_after_mps,
        max(0.0, float(state.altitude_m)),
        state.envelope.drag_coefficient,
        area_after_m2,
    )

    drag_x_sign_after = -1.0 if v_rel_x_after_mps > 0 else (1.0 if v_rel_x_after_mps < 0 else 0.0)
    F_drag_x_after = F_drag_x_mag_after * drag_x_sign_after

    telemetry = {
        "time_s": state.time_s,
        "x_m": state.x_m,
        "vx_mps": state.vx_mps,
        "altitude_m": state.altitude_m,
        "velocity_mps": state.velocity_mps,
        "gas_volume_m3": gas_vol_current,
        "ambient_pressure_pa": atmosphere_pressure(max(0.0, state.altitude_m)),
        "ambient_temperature_k": atmosphere_temperature(max(0.0, state.altitude_m)),
        "net_lift_N": F_net_after,
        "buoyancy_N": F_buoy_after,
        "weight_N": F_weight_after,
        "drag_N": F_drag_after,
        "drag_x_N": F_drag_x_after,
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
    step_interval: Optional[float] = None,  # Store only every N seconds (default: store every step)
) -> List[dict]:
    """Run the simulation for total_time_s seconds and return telemetry list.

    The simulation stops early if the balloon bursts, lands, or crashes.
    step_interval limits output frequency for long runs (e.g. 1.0 = 1 sample/s)
    so we don't store hundreds of thousands of ticks.
    """

    telemetry = []
    step = 0
    next_sample = 0.0
    while step * dt < total_time_s and step < max_steps:
        if state.burst or state.landed or state.crashed:
            break
        tick = simulation_step(state, dt)
        # Only append to telemetry if we've reached the next sample interval
        if step_interval is None or tick["time_s"] >= next_sample:
            telemetry.append(tick)
            if step_interval is not None:
                next_sample += step_interval
        step += 1

    return telemetry
