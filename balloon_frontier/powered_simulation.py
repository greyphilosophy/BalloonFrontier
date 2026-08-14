"""Powered simulation shell for finite batteries and quadcopter control.

The underlying lighter-than-air solver remains the source of truth for buoyancy,
drag, thermal behavior, leakage, venting, and terrain. This wrapper only applies
control inputs between fixed physics steps, accounts for electrical energy, and
records recovery lessons that emerge from the resulting forces.
"""

from __future__ import annotations

from dataclasses import dataclass

from balloon_frontier.power import (
    battery_energy_after_step,
    battery_fraction,
    motor_power_w,
    power_configuration_for_payloads,
    powered_flight_target_altitude_m,
    vertical_control_force_N,
)
from balloon_frontier.simulation import (
    SimulationState,
    _compute_forces,
    run_simulation as run_passive_simulation,
    simulation_step,
)


@dataclass(frozen=True, slots=True)
class PoweredSimulationResult:
    telemetry: tuple[dict, ...]
    flight_notes: tuple[str, ...] = ()
    battery_remaining_wh: float = 0.0
    battery_capacity_wh: float = 0.0


def _needs_power_shell(payload_ids: tuple[str, ...]) -> bool:
    config = power_configuration_for_payloads(payload_ids)
    return config.has_electrical_consumers or config.has_battery


def run_powered_simulation(
    state: SimulationState,
    *,
    payload_ids: tuple[str, ...],
    dt: float = 0.1,
    total_time_s: float = 60.0,
    max_steps: int = 10000,
    step_interval: float | None = None,
) -> PoweredSimulationResult:
    """Run shared physics with finite electrical energy and control inputs."""
    payload_ids = tuple(payload_ids)
    if not _needs_power_shell(payload_ids):
        telemetry = run_passive_simulation(
            state,
            dt=dt,
            total_time_s=total_time_s,
            max_steps=max_steps,
            step_interval=step_interval,
        )
        return PoweredSimulationResult(telemetry=tuple(telemetry))

    config = power_configuration_for_payloads(payload_ids)
    battery_remaining_wh = config.battery_capacity_wh
    ground_altitude_m = float(state.terrain_base_altitude_offset_m)
    telemetry: list[dict] = []
    notes: list[str] = []
    step = 0
    next_sample = 0.0
    recovery_problem_detected = False
    battery_depleted = False

    while step * dt < total_time_s and step < max_steps:
        if state.landed or state.crashed:
            break

        battery_active = battery_remaining_wh > 1e-9
        returning = config.has_quadcopter and state.time_s >= config.return_time_s
        _, _, _, passive_net_force_N, _ = _compute_forces(state)
        total_mass_kg = state.total_mass()

        vertical_force_N = 0.0
        if config.has_quadcopter and battery_active:
            target_altitude_m = powered_flight_target_altitude_m(
                time_s=state.time_s,
                ground_altitude_m=ground_altitude_m,
                config=config,
            )
            vertical_force_N = vertical_control_force_N(
                altitude_m=state.altitude_m,
                velocity_mps=state.velocity_mps,
                target_altitude_m=target_altitude_m,
                passive_net_force_N=passive_net_force_N,
                total_mass_kg=total_mass_kg,
                max_vertical_force_N=config.max_vertical_force_N,
            )
            state.horizontal_control_force_N = config.max_horizontal_force_N
            if total_mass_kg > 0.0:
                state.velocity_mps += vertical_force_N / total_mass_kg * dt
        else:
            state.horizontal_control_force_N = 0.0

        if returning and state.has_pressure_valve:
            state.vent_open = passive_net_force_N > 0.0

        electrical_heater_on = (
            battery_active
            and config.electrical_heater_input_w > 0.0
            and not returning
        )
        state.heater_power_watts = config.non_electrical_heater_coupled_w + (
            config.electrical_heater_coupled_w if electrical_heater_on else 0.0
        )

        cooling_can_reduce_lift = (
            state.gas_type in {"air", "hot_air"}
            and config.electrical_heater_input_w > 0.0
        )
        if (
            returning
            and state.time_s >= config.return_time_s + 10.0
            and passive_net_force_N > 0.0
            and not state.has_pressure_valve
            and not cooling_can_reduce_lift
        ):
            recovery_problem_detected = True

        tick = simulation_step(state, dt)
        horizontal_force_N = float(tick.get("control_force_x_N", 0.0))
        electrical_power_w = 0.0
        if battery_active:
            electrical_power_w = config.constant_load_w
            if electrical_heater_on:
                electrical_power_w += config.electrical_heater_input_w
            if config.has_quadcopter:
                electrical_power_w += motor_power_w(
                    vertical_force_N,
                    horizontal_force_N,
                )
            new_energy_wh = battery_energy_after_step(
                battery_remaining_wh,
                electrical_power_w,
                dt,
            )
            if battery_remaining_wh > 0.0 and new_energy_wh <= 0.0:
                battery_depleted = True
            battery_remaining_wh = new_energy_wh

        tick["battery_remaining_wh"] = battery_remaining_wh
        tick["battery_capacity_wh"] = config.battery_capacity_wh
        tick["battery_fraction"] = battery_fraction(
            battery_remaining_wh,
            config.battery_capacity_wh,
        )
        tick["electrical_power_w"] = electrical_power_w
        tick["vertical_control_force_N"] = vertical_force_N
        tick["returning"] = returning

        if step_interval is None or tick["time_s"] >= next_sample:
            telemetry.append(tick)
            if step_interval is not None:
                next_sample += step_interval
        step += 1

    if config.has_electrical_consumers and not config.has_battery:
        notes.append(
            "Electrical equipment had no Battery Pack, so powered systems could not operate."
        )
    if battery_depleted:
        notes.append(
            "Battery depleted; powered flight and electrical heating shut down."
        )
    if recovery_problem_detected:
        notes.append(
            "Recovery problem: at the commanded return, the aircraft remained positively buoyant with quadcopter vertical thrust already at minimum. Without a way to reduce lift, it could not command a descent."
        )
    if config.has_battery:
        percent = round(
            100.0 * battery_fraction(
                battery_remaining_wh,
                config.battery_capacity_wh,
            )
        )
        notes.append(
            f"Battery: {percent}% remaining ({battery_remaining_wh:.0f} Wh of {config.battery_capacity_wh:.0f} Wh)."
        )

    return PoweredSimulationResult(
        telemetry=tuple(telemetry),
        flight_notes=tuple(notes),
        battery_remaining_wh=battery_remaining_wh,
        battery_capacity_wh=config.battery_capacity_wh,
    )
