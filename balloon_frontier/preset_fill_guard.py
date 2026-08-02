"""Calculate launch gas fills from nominal volume with burst-safe limits.

The legacy ``LaunchRequest.gas_mass_kg`` implementation used burst volume as
its preset baseline. That could begin a contained envelope at or beyond its
burst threshold. This module keeps nominal volume as the preset baseline and
clamps every launch fill, including manual fills, to the envelope's configured
safe fraction of burst capacity at the selected launch conditions.
"""

from __future__ import annotations


def _resolved_launch_temperature_k(request) -> float:
    """Resolve the gas temperature used by both fill and simulation startup."""
    from balloon_frontier.physics import atmosphere_temperature

    altitude_m = float(request.site.altitude_m)
    ambient_k = atmosphere_temperature(altitude_m)

    if request.gas_temperature_delta_k is not None:
        resolved_k = ambient_k + float(request.gas_temperature_delta_k)
    elif request.site.gas_temperature_k is not None:
        resolved_k = float(request.site.gas_temperature_k)
    else:
        resolved_k = ambient_k + float(request.site.temperature_offset_k)

    if resolved_k <= 0.0:
        raise ValueError("Launch gas temperature must be greater than 0 K")
    return resolved_k


def _launch_fill_gas_mass_kg(request) -> float:
    """Return a nominal preset or manual fill capped below burst capacity."""
    from balloon_frontier.catalog import FillMode
    from balloon_frontier.physics import atmosphere_pressure, gas_density

    balloon = request.balloon
    envelope = request.envelope
    nominal_volume_m3 = (
        balloon.max_volume_m3
        if balloon is not None
        else envelope.max_volume_m3
    )
    burst_stretch_ratio = (
        balloon.burst_stretch_ratio
        if balloon is not None
        else envelope.burst_stretch_ratio
    )
    is_manual = request.fill_mode == FillMode.MANUAL
    manual_quantity = int(getattr(request, "balloon_count", 1)) if is_manual else 1

    launch_altitude_m = float(request.site.altitude_m)
    launch_pressure_pa = atmosphere_pressure(launch_altitude_m)
    launch_temperature_k = _resolved_launch_temperature_k(request)
    gas_density_kg_m3 = gas_density(
        request.gas.id,
        launch_temperature_k,
        launch_pressure_pa,
    )

    # Automatic presets are calculated per envelope. Manual mass is defined as
    # a total for the complete cluster, so all per-envelope limits must scale
    # with balloon_count before they are applied to that total.
    safe_volume_m3 = (
        nominal_volume_m3
        * burst_stretch_ratio
        * envelope.safe_fill_fraction
        * manual_quantity
    )
    safe_mass_kg = gas_density_kg_m3 * safe_volume_m3

    if is_manual:
        assert request.manual_gas_mass_kg is not None
        gas_mass_kg = max(0.001, float(request.manual_gas_mass_kg))
    else:
        gas_mass_kg = (
            gas_density_kg_m3
            * nominal_volume_m3
            * request.fill_mode.get_multiplier()
        )

    # CLI balloon definitions provide per-balloon manufacturer limits. Scale
    # them only for manual cluster totals; automatic fills are multiplied by the
    # cluster request after this per-envelope property returns.
    if balloon is not None and balloon.fill_range_g != (0, 0):
        min_mass_kg = float(balloon.fill_range_g[0]) / 1000.0 * manual_quantity
        max_mass_kg = float(balloon.fill_range_g[1]) / 1000.0 * manual_quantity
        gas_mass_kg = min(max(gas_mass_kg, min_mass_kg), max_mass_kg)

    return min(gas_mass_kg, safe_mass_kg)


def _launch_simulation_state(original):
    """Wrap state construction so it uses the same resolved launch temperature."""
    def to_simulation_state(request):
        state = original(request)
        state.gas_temperature_k = _resolved_launch_temperature_k(request)
        state.gas_temperature_delta_k = None
        return state

    to_simulation_state._balloon_frontier_launch_temperature = True
    return to_simulation_state


def install_nominal_preset_fill() -> None:
    """Install corrected fill and launch-temperature behavior exactly once."""
    from balloon_frontier.launch_result import LaunchRequest

    current_property = LaunchRequest.gas_mass_kg
    if not getattr(current_property.fget, "_balloon_frontier_nominal_fill", False):
        _launch_fill_gas_mass_kg._balloon_frontier_nominal_fill = True
        LaunchRequest.gas_mass_kg = property(
            _launch_fill_gas_mass_kg,
            doc=(
                "Calculate gas mass from nominal launch volume and clamp all fills "
                "below the configured burst-safe capacity at launch conditions."
            ),
        )

    current_state_builder = LaunchRequest.to_simulation_state
    if not getattr(
        current_state_builder,
        "_balloon_frontier_launch_temperature",
        False,
    ):
        LaunchRequest.to_simulation_state = _launch_simulation_state(
            current_state_builder
        )
