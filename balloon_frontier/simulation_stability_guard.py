"""Adaptive substeps for stiff horizontal quadratic drag.

The fixed-step integrator can overshoot the local wind velocity when the
quadratic drag impulse is larger than the current relative momentum. That
creates a sign-flipping numerical instability where horizontal velocity grows
without bound. This guard subdivides only those stiff steps.
"""

from __future__ import annotations

import math


def _required_substeps(state, dt: float) -> int:
    """Return enough substeps to keep horizontal drag from crossing the wind."""
    if dt <= 0.0 or not getattr(state, "wind_enabled", False):
        return 1

    from balloon_frontier.physics import (
        atmosphere_density,
        gas_volume,
        spherical_area,
    )
    from balloon_frontier.wind import wind_vector

    altitude = max(0.0, float(state.altitude_m))
    wind_vx, _ = wind_vector(
        altitude,
        time_s=float(state.time_s),
        site_id=state.wind_site_id,
    )
    wind_vx *= float(getattr(state, "weather_drift_multiplier", 1.0))
    relative_velocity = float(state.vx_mps) - float(wind_vx)
    speed = abs(relative_velocity)
    if speed <= 1e-9:
        return 1

    pressure_scale = float(
        getattr(state.envelope, "weather_pressure_modifier", 1.0)
    )
    from balloon_frontier.physics import atmosphere_pressure

    pressure = atmosphere_pressure(altitude) * pressure_scale
    volume = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        pressure,
    )
    if not state.envelope.contained_gas:
        volume = min(volume, state.envelope.max_volume_m3)
    area = spherical_area(volume)
    rho = atmosphere_density(altitude)
    drag = (
        0.5
        * rho
        * speed
        * speed
        * state.envelope.drag_coefficient
        * area
    )
    mass = float(state.total_mass())
    if mass <= 0.0 or drag <= 0.0:
        return 1

    impulse_ratio = (drag / mass) * dt / speed
    if impulse_ratio <= 0.5:
        return 1

    # Keep each substep's drag impulse comfortably below the relative momentum.
    return min(256, max(2, math.ceil(impulse_ratio / 0.5)))


def install_simulation_stability_guard() -> None:
    """Wrap simulation_step with adaptive substeps exactly once."""
    from balloon_frontier import simulation

    current = simulation.simulation_step
    if getattr(current, "_balloon_frontier_adaptive_drag", False):
        return

    def stable_simulation_step(state, dt: float = 0.1):
        substeps = _required_substeps(state, dt)
        if substeps == 1:
            return current(state, dt)

        sub_dt = dt / substeps
        telemetry = None
        for _ in range(substeps):
            telemetry = current(state, sub_dt)
            if state.landed or state.crashed:
                break
        assert telemetry is not None
        return telemetry

    stable_simulation_step._balloon_frontier_adaptive_drag = True
    simulation.simulation_step = stable_simulation_step
