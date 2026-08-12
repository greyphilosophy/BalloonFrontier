"""Balloon Frontier - Simulation Engine

Deterministic fixed-step lighter-than-air simulation.

The shared state integrates vertical motion, optional horizontal wind drift,
ideal-gas expansion, leakage/venting, and a lumped thermal energy balance.
Heating is not a separate vehicle mode: any gas can receive heat and its density
then follows from the same equation of state.

All units are SI (meters, kilograms, seconds, Kelvin, Pascals).
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional

from balloon_frontier.physics import (
    atmosphere_temperature,
    atmosphere_pressure,
    gas_volume,
    gas_density,
    drag_force,
    spherical_area,
    G,
    R_AIR,
)
from balloon_frontier.thermal import calculate_balloon_heat_flows, gas_temperature_update


@dataclass
class EnvelopeConfig:
    """Configuration for a balloon/aerostat envelope."""

    max_volume_m3: float = 10.0
    burst_stretch_ratio: float = 2.5
    drag_coefficient: float = 0.47
    permeability: float = 0.001  # fraction of gas mass lost per second
    mass_kg: float = 1.0
    contained_gas: bool = False
    envelope_absorptivity: float = 0.5
    envelope_emissivity: float = 0.8

    # Effective material/system thermal properties. ``None`` keeps the legacy
    # thermal model; material-aware requests populate these through aerostat.py.
    thermal_resistance_m2_k_w: float | None = None
    inflation_heat_loss_exponent: float = 0.0
    stretch_start_fraction: float = 1.0
    max_temperature_k: float = 450.0

    # Weather modifiers — applied at runtime by the weather system.
    weather_burst_risk_modifier: float = 1.0
    weather_solar_modifier: float = 1.0
    weather_pressure_modifier: float = 1.0
    weather_ascent_multiplier: float = 1.0
    weather_drift_multiplier: float = 1.0


@dataclass
class SimulationState:
    """Mutable state for one lighter-than-air vehicle during a simulation tick."""

    # Position / kinematics
    altitude_m: float = 0.0
    velocity_mps: float = 0.0
    x_m: float = 0.0
    vx_mps: float = 0.0
    terrain_base_altitude_offset_m: float = 0.0
    wind_enabled: bool = False
    wind_site_id: str = "field"

    # Weather modifiers
    weather_ascent_multiplier: float = 1.0
    weather_drift_multiplier: float = 1.0

    # Gas compartment
    gas_type: str = "helium"
    gas_mass_kg: float = 1.0
    gas_temperature_k: Optional[float] = None
    gas_temperature_delta_k: Optional[float] = None
    gas_pressure_pa: float = 101325.0

    # Heat inputs. Components supply watts; the thermal model decides the
    # resulting temperature and the physics engine decides the resulting lift.
    heater_power_watts: float = 0.0
    equipment_heat_watts: float = 0.0

    # Vehicle mass
    payload_mass_kg: float = 10.0
    ballast_mass_kg: float = 5.0
    has_pressure_valve: bool = False

    # Envelope
    envelope: EnvelopeConfig = field(default_factory=EnvelopeConfig)

    # Venting / leakage
    vent_open: bool = False
    vent_rate_kg_per_s: float = 0.05

    # Ballast release
    ballast_released_kg: float = 0.0

    # Clock
    time_s: float = 0.0

    # Flags
    burst: bool = False
    landed: bool = False
    crashed: bool = False
    has_lifted_off: bool = False
    thermal_limit_exceeded: bool = False

    def __post_init__(self) -> None:
        """Resolve initial gas temperature from absolute T, delta-T, or ambient."""
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

        self.gas_temperature_k = ambient_temp_k
        assert self.gas_temperature_k is not None

    def total_mass(self) -> float:
        """Total vehicle mass (gas + envelope + payload + remaining ballast)."""
        ballast = max(0.0, self.ballast_mass_kg - self.ballast_released_kg)
        return self.gas_mass_kg + self.envelope.mass_kg + self.payload_mass_kg + ballast


def _effective_pressure(state: SimulationState) -> float:
    pressure_scale = getattr(state.envelope, "weather_pressure_modifier", 1.0)
    ambient = atmosphere_pressure(max(0.0, state.altitude_m))
    return ambient * pressure_scale


def _gas_and_displaced_volume(state: SimulationState) -> tuple[float, float]:
    pressure = _effective_pressure(state)
    ideal_volume = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        pressure,
    )
    if state.envelope.contained_gas:
        return ideal_volume, ideal_volume
    return ideal_volume, min(ideal_volume, state.envelope.max_volume_m3)


def _compute_forces(state: SimulationState) -> tuple:
    """Return Archimedean buoyancy, weight, drag, net force, and frontal area."""
    pressure = _effective_pressure(state)
    _, displaced_vol = _gas_and_displaced_volume(state)

    ambient_temp = atmosphere_temperature(max(0.0, state.altitude_m))
    rho_air = pressure / (R_AIR * ambient_temp)

    # Archimedes supplies the weight of displaced ambient air. Gas mass is
    # already included in total_mass(), so subtracting rho_gas here as well
    # would charge the contained gas weight twice.
    F_buoy = rho_air * G * displaced_vol
    F_weight = state.total_mass() * G

    area_m2 = spherical_area(max(displaced_vol, 1e-12))
    F_drag = drag_force(
        state.velocity_mps,
        max(0.0, state.altitude_m),
        state.envelope.drag_coefficient,
        area_m2,
    )
    drag_sign = -1.0 if state.velocity_mps > 0 else (1.0 if state.velocity_mps < 0 else 0.0)
    F_drag_vertical = F_drag * drag_sign
    F_net = F_buoy + F_drag_vertical - F_weight
    return F_buoy, F_weight, F_drag_vertical, F_net, area_m2


def _update_thermal_state(
    state: SimulationState,
    dt: float,
    pressure_pa: float,
    weather_solar_modifier: float,
) -> tuple[dict, float]:
    """Apply watt-valued heat flows and return flows + inflation fraction."""
    ideal_volume = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        pressure_pa,
    )
    actual_volume = (
        ideal_volume
        if state.envelope.contained_gas
        else min(ideal_volume, state.envelope.max_volume_m3)
    )
    inflation_fraction = actual_volume / max(state.envelope.max_volume_m3, 1e-12)

    # Drag and direct solar interception use projected cross-sectional area.
    # Convection, radiation, and membrane conduction use the whole skin area.
    solar_projected_area_m2 = spherical_area(max(actual_volume, 1e-12))
    envelope_surface_area_m2 = 4.0 * solar_projected_area_m2

    flows = calculate_balloon_heat_flows(
        altitude_m=max(0.0, state.altitude_m),
        gas_temp_K=state.gas_temperature_k,
        gas_mass_kg=state.gas_mass_kg,
        gas_type=state.gas_type,
        envelope_absorptivity=(
            state.envelope.envelope_absorptivity * weather_solar_modifier
        ),
        envelope_emissivity=state.envelope.envelope_emissivity,
        envelope_area_m2=envelope_surface_area_m2,
        envelope_mass_kg=state.envelope.mass_kg,
        heater_power_watts=state.heater_power_watts,
        equipment_heat_watts=state.equipment_heat_watts,
        thermal_resistance_m2_k_w=state.envelope.thermal_resistance_m2_k_w,
        inflation_fraction=inflation_fraction,
        inflation_heat_loss_exponent=state.envelope.inflation_heat_loss_exponent,
        stretch_start_fraction=state.envelope.stretch_start_fraction,
        solar_projected_area_m2=solar_projected_area_m2,
    )
    state.gas_temperature_k = max(
        1.0,
        gas_temperature_update(
            gas_type=state.gas_type,
            gas_mass_kg=state.gas_mass_kg,
            gas_temp_K=state.gas_temperature_k,
            heat_flows=flows,
            dt=dt,
        ),
    )
    if state.gas_temperature_k > state.envelope.max_temperature_k:
        state.thermal_limit_exceeded = True
    return flows, inflation_fraction


def simulation_step(state: SimulationState, dt: float = 0.1) -> dict:
    """Execute one fixed-step simulation tick using semi-implicit Euler."""
    altitude_m0 = float(state.altitude_m)
    time_s0 = float(state.time_s)

    F_buoy, F_weight, F_drag_vertical, F_net, area_m2 = _compute_forces(state)

    # Horizontal wind-relative drag.
    weather_drift_mult = getattr(state, "weather_drift_multiplier", 1.0)
    from balloon_frontier.wind import wind_vector

    wind_vx_mps = 0.0
    if state.wind_enabled:
        wind_vx_mps, _wind_vy_mps = wind_vector(
            altitude_m0,
            time_s=time_s0,
            site_id=state.wind_site_id,
        )
    wind_vx_mps *= weather_drift_mult
    v_rel_x_mps = float(state.vx_mps - wind_vx_mps)
    F_drag_x_mag = drag_force(
        v_rel_x_mps,
        max(0.0, altitude_m0),
        state.envelope.drag_coefficient,
        area_m2,
    )
    drag_x_sign = -1.0 if v_rel_x_mps > 0 else (1.0 if v_rel_x_mps < 0 else 0.0)
    F_drag_x = F_drag_x_mag * drag_x_sign

    weather_pressure_scale = getattr(state.envelope, "weather_pressure_modifier", 1.0)
    weather_solar_mod = getattr(state.envelope, "weather_solar_modifier", 1.0)
    weather_burst_mod = getattr(state.envelope, "weather_burst_risk_modifier", 1.0)

    # Vertical weather wind, expressed as air velocity and therefore handled by
    # relative-velocity drag rather than by multiplying vehicle acceleration.
    weather_ascent_mult = getattr(state, "weather_ascent_multiplier", 1.0)
    vertical_wind_mps = float(weather_ascent_mult - 1.0)
    v_rel_y_mps = float(state.velocity_mps) - vertical_wind_mps
    F_drag_y_mag = drag_force(
        v_rel_y_mps,
        max(0.0, altitude_m0),
        state.envelope.drag_coefficient,
        area_m2,
    )
    drag_y_sign = -1.0 if v_rel_y_mps > 0 else (1.0 if v_rel_y_mps < 0 else 0.0)
    F_drag_vertical = F_drag_y_mag * drag_y_sign
    F_net = F_buoy + F_drag_vertical - F_weight

    total_mass = state.total_mass()
    if total_mass > 0:
        acceleration_y = F_net / total_mass
        acceleration_x = F_drag_x / total_mass
    else:
        acceleration_y = 0.0
        acceleration_x = 0.0

    state.vx_mps += acceleration_x * dt
    state.x_m += state.vx_mps * dt
    state.velocity_mps += acceleration_y * dt
    state.altitude_m += state.velocity_mps * dt

    # A craft that has not lifted off rests on the ground rather than instantly
    # completing a zero-duration "landing". This lets real heater power warm a
    # negatively buoyant envelope until the same force model produces liftoff.
    ground_alt_m = float(state.terrain_base_altitude_offset_m)
    if state.altitude_m > ground_alt_m + 1e-3:
        state.has_lifted_off = True
    elif not state.has_lifted_off and state.altitude_m <= ground_alt_m:
        state.altitude_m = ground_alt_m
        if state.velocity_mps < 0.0:
            state.velocity_mps = 0.0

    # Leakage / permeability.
    P_amb = atmosphere_pressure(max(0.0, state.altitude_m))
    P_amb_effective = P_amb * weather_pressure_scale
    leak_fraction = max(0.0, state.envelope.permeability) * dt
    state.gas_mass_kg *= max(0.0001, 1.0 - leak_fraction)

    # Unified thermal energy update.
    heat_flows, inflation_fraction = _update_thermal_state(
        state,
        dt,
        P_amb_effective,
        weather_solar_mod,
    )

    # Zero-pressure/open envelopes vent overflow instead of stretching without
    # limit. Heating ordinary air therefore reduces contained mass naturally:
    # T rises -> ideal volume rises -> excess gas leaves -> density falls.
    if not state.envelope.contained_gas:
        gas_vol = gas_volume(
            state.gas_mass_kg,
            state.gas_type,
            state.gas_temperature_k,
            P_amb_effective,
        )
        if gas_vol > state.envelope.max_volume_m3:
            state.gas_mass_kg *= state.envelope.max_volume_m3 / gas_vol

    gas_vol_after = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        P_amb_effective,
    )
    burst_vol_limit = (
        state.envelope.max_volume_m3
        * state.envelope.burst_stretch_ratio
        / max(weather_burst_mod, 1e-9)
    )

    # Pressure valve: vent contained gas to slight negative buoyancy before burst.
    if (
        state.has_pressure_valve
        and state.envelope.contained_gas
        and gas_vol_after >= burst_vol_limit
    ):
        rho_air = P_amb_effective / (
            R_AIR * atmosphere_temperature(max(0.0, state.altitude_m))
        )
        rho_gas = gas_density(
            state.gas_type,
            state.gas_temperature_k,
            P_amb_effective,
        )
        non_gas_mass = (
            state.envelope.mass_kg
            + state.payload_mass_kg
            + max(0.0, state.ballast_mass_kg - state.ballast_released_kg)
        )
        if rho_air > rho_gas and non_gas_mass > 0:
            neutral_gas_kg = non_gas_mass * rho_gas / (rho_air - rho_gas)
        else:
            neutral_gas_kg = 0.0
        target_gas_kg = max(0.001, neutral_gas_kg * 0.90)
        while state.gas_mass_kg > target_gas_kg:
            state.gas_mass_kg = max(0.001, state.gas_mass_kg * 0.95)
            gas_vol_after = gas_volume(
                state.gas_mass_kg,
                state.gas_type,
                state.gas_temperature_k,
                P_amb_effective,
            )

    if (
        not state.has_pressure_valve
        and state.envelope.contained_gas
        and gas_vol_after >= burst_vol_limit
    ):
        state.burst = True
        state.envelope.contained_gas = False
        state.vent_open = True

    # Landing/crash applies only after a genuine liftoff. Before liftoff the
    # ground boundary above supplies support while thermal state evolves.
    relative_alt_m = state.altitude_m - ground_alt_m
    if state.has_lifted_off and relative_alt_m <= 0.0 and state.velocity_mps < 0.0:
        state.altitude_m = ground_alt_m
        state.landed = True
        if abs(state.velocity_mps) > 15.0:
            state.crashed = True

    state.time_s += dt

    # Telemetry snapshot.
    gas_vol_current = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        atmosphere_pressure(max(0.0, state.altitude_m)),
    )
    F_buoy_after, F_weight_after, F_drag_after, F_net_after, area_after_m2 = _compute_forces(state)

    if state.wind_enabled:
        wind_vx_mps_after, _wind_vy_mps_after = wind_vector(
            float(state.altitude_m),
            time_s=float(state.time_s),
            site_id=state.wind_site_id,
        )
        wind_vx_mps_after *= weather_drift_mult
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

    return {
        "time_s": state.time_s,
        "x_m": state.x_m,
        "vx_mps": state.vx_mps,
        "altitude_m": state.altitude_m,
        "velocity_mps": state.velocity_mps,
        "gas_volume_m3": gas_vol_current,
        "gas_temperature_k": state.gas_temperature_k,
        "heater_power_watts": state.heater_power_watts,
        "inflation_fraction": inflation_fraction,
        "effective_thermal_resistance_m2_k_w": heat_flows.get(
            "effective_thermal_resistance_m2_k_w"
        ),
        "thermal_limit_exceeded": state.thermal_limit_exceeded,
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


def run_simulation(
    state: SimulationState,
    dt: float = 0.1,
    total_time_s: float = 60.0,
    max_steps: int = 10000,
    step_interval: Optional[float] = None,
) -> List[dict]:
    """Run the simulation and return telemetry snapshots."""
    telemetry = []
    step = 0
    next_sample = 0.0
    while step * dt < total_time_s and step < max_steps:
        if state.landed or state.crashed:
            break
        tick = simulation_step(state, dt)
        if step_interval is None or tick["time_s"] >= next_sample:
            telemetry.append(tick)
            if step_interval is not None:
                next_sample += step_interval
        step += 1
    return telemetry
