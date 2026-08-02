"""Calculate launch gas fills from nominal volume with burst-safe limits.

The legacy ``LaunchRequest.gas_mass_kg`` implementation used burst volume as
its preset baseline. That could begin a contained envelope at or beyond its
burst threshold. This module keeps nominal volume as the preset baseline and
clamps every launch fill, including manual fills, to the envelope's configured
safe fraction of burst capacity.
"""

from __future__ import annotations


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

    gas_density_kg_m3 = gas_density(
        request.gas.id,
        288.15,
        atmosphere_pressure(0.0),
    )

    # A launch fill may use only the configured safe fraction of the volume at
    # which the envelope would burst. This keeps every configuration safely
    # below an already-bursting state before the first simulation tick.
    safe_volume_m3 = (
        nominal_volume_m3
        * burst_stretch_ratio
        * envelope.safe_fill_fraction
    )
    safe_mass_kg = gas_density_kg_m3 * safe_volume_m3

    if request.fill_mode == FillMode.MANUAL:
        assert request.manual_gas_mass_kg is not None
        # Manual entry remains user-controlled within physical launch limits.
        # Oversized entries are reduced to the safe launch maximum rather than
        # allowing an already-bursting initial state into the simulation.
        gas_mass_kg = max(0.001, float(request.manual_gas_mass_kg))
    else:
        gas_mass_kg = (
            gas_density_kg_m3
            * nominal_volume_m3
            * request.fill_mode.get_multiplier()
        )

    # CLI balloon definitions may provide stricter manufacturer fill limits.
    if balloon is not None and balloon.fill_range_g != (0, 0):
        min_mass_kg = float(balloon.fill_range_g[0]) / 1000.0
        max_mass_kg = float(balloon.fill_range_g[1]) / 1000.0
        gas_mass_kg = min(max(gas_mass_kg, min_mass_kg), max_mass_kg)

    return min(gas_mass_kg, safe_mass_kg)


def install_nominal_preset_fill() -> None:
    """Install the corrected canonical gas-mass property exactly once."""
    from balloon_frontier.launch_result import LaunchRequest

    current = LaunchRequest.gas_mass_kg
    if getattr(current.fget, "_balloon_frontier_nominal_fill", False):
        return

    _launch_fill_gas_mass_kg._balloon_frontier_nominal_fill = True
    LaunchRequest.gas_mass_kg = property(
        _launch_fill_gas_mass_kg,
        doc=(
            "Calculate gas mass from nominal launch volume and clamp all fills "
            "below the configured burst-safe capacity."
        ),
    )
