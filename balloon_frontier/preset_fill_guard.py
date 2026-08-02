"""Correct preset gas fills to use nominal envelope volume.

The legacy ``LaunchRequest.gas_mass_kg`` implementation used burst volume as
its baseline.  That can begin a contained envelope at or beyond its burst
threshold, causing a pressure valve to vent immediately before liftoff.
"""

from __future__ import annotations


def _nominal_preset_gas_mass_kg(request) -> float:
    """Calculate a launch fill from nominal volume, not burst capacity."""
    from balloon_frontier.catalog import FillMode

    if request.fill_mode == FillMode.MANUAL:
        assert request.manual_gas_mass_kg is not None
        return request.manual_gas_mass_kg

    from balloon_frontier.physics import atmosphere_pressure, gas_density

    balloon = request.balloon
    fill_volume_m3 = (
        balloon.max_volume_m3
        if balloon is not None
        else request.envelope.max_volume_m3
    )
    gas_density_kg_m3 = gas_density(
        request.gas.id,
        288.15,
        atmosphere_pressure(0.0),
    )
    gas_mass_kg = (
        gas_density_kg_m3
        * fill_volume_m3
        * request.fill_mode.get_multiplier()
    )

    # CLI balloon definitions may provide manufacturer fill limits.
    if balloon is not None and balloon.fill_range_g != (0, 0):
        min_mass_kg = float(balloon.fill_range_g[0]) / 1000.0
        max_mass_kg = float(balloon.fill_range_g[1]) / 1000.0
        gas_mass_kg = min(max(gas_mass_kg, min_mass_kg), max_mass_kg)

    return gas_mass_kg


def install_nominal_preset_fill() -> None:
    """Install the corrected canonical gas-mass property exactly once."""
    from balloon_frontier.launch_result import LaunchRequest

    current = LaunchRequest.gas_mass_kg
    if getattr(current.fget, "_balloon_frontier_nominal_fill", False):
        return

    _nominal_preset_gas_mass_kg._balloon_frontier_nominal_fill = True
    LaunchRequest.gas_mass_kg = property(
        _nominal_preset_gas_mass_kg,
        doc=(
            "Calculate gas mass from nominal launch volume for preset fills; "
            "manual fills remain explicit."
        ),
    )
