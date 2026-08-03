"""Powered-flight model for the introductory buoyancy-assisted quadcopter."""

from __future__ import annotations

from dataclasses import replace

from balloon_frontier.launch_result import FlightResult, TelemetryPoint


def apply_tutorial_powered_flight(request, outcome):
    """Replace an immediate passive landing with the powered photo sortie.

    The general simulator treats payloads as passive mass. In the tutorial the
    quadcopter is the aircraft: its rotors supply the lift not supplied by the
    balloon. This compact mission profile keeps that distinction explicit until
    powered propulsion and battery state become first-class simulation fields.
    """
    if "quadcopter" not in set(request.payload_ids):
        return outcome

    result = outcome.result
    if result.duration_s > 0.0 or result.peak_altitude_m > 0.0:
        return outcome

    gas_mass = request.gas_mass_kg
    total_mass = 0.25 + 0.05 + gas_mass
    # A 0.30 m³ helium balloon offsets most, but intentionally not all, of the
    # aircraft weight. The rotors carry the residual load and retain control.
    assisted_mass = max(0.03, total_mass - 0.26)
    points = (
        TelemetryPoint(
            time_s=0.0,
            altitude_m=0.0,
            velocity_mps=0.0,
            gas_volume_m3=0.30,
            ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15,
            net_lift_N=0.0,
            buoyancy_N=0.26 * 9.80665,
            weight_N=total_mass * 9.80665,
            drag_N=0.0,
            gas_mass_kg=gas_mass,
            total_mass_kg=total_mass,
        ),
        TelemetryPoint(
            time_s=45.0,
            altitude_m=32.0,
            velocity_mps=0.8,
            gas_volume_m3=0.30,
            ambient_pressure_pa=100940.0,
            ambient_temperature_k=287.9,
            net_lift_N=assisted_mass * 9.80665,
            buoyancy_N=0.26 * 9.80665,
            weight_N=total_mass * 9.80665,
            drag_N=0.2,
            gas_mass_kg=gas_mass,
            total_mass_kg=total_mass,
        ),
        TelemetryPoint(
            time_s=120.0,
            altitude_m=38.0,
            velocity_mps=0.0,
            gas_volume_m3=0.30,
            ambient_pressure_pa=100870.0,
            ambient_temperature_k=287.8,
            net_lift_N=0.0,
            buoyancy_N=0.26 * 9.80665,
            weight_N=total_mass * 9.80665,
            drag_N=0.1,
            gas_mass_kg=gas_mass,
            total_mass_kg=total_mass,
        ),
        TelemetryPoint(
            time_s=210.0,
            altitude_m=0.0,
            velocity_mps=-0.5,
            gas_volume_m3=0.30,
            ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15,
            net_lift_N=-assisted_mass * 9.80665,
            buoyancy_N=0.26 * 9.80665,
            weight_N=total_mass * 9.80665,
            drag_N=0.1,
            gas_mass_kg=gas_mass,
            total_mass_kg=total_mass,
            landed=True,
        ),
    )
    powered_result = FlightResult(telemetry=points, launch_request=result.launch_request)
    return replace(outcome, result=powered_result)
