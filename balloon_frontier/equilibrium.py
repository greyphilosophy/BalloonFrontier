"""Balloon Frontier - Equilibrium Altitude Calculator

Finds the altitude at which a balloon achieves neutral buoyancy
(buoyancy = weight). This is the "floating" or "equilibrium" altitude.

Reference: GDD Section 6.8 (Equilibrium/floating altitude).
"""

import math
from balloon_frontier.physics import (
    atmosphere_pressure,
    atmosphere_density,
    gas_density,
    gas_volume,
    G,
)


def equilibrium_altitude(
    gas_type: str,
    gas_mass_kg: float,
    gas_temperature_k: float,
    total_vehicle_mass_kg: float,
    envelope_max_volume: float,
    contained_gas: bool = False,
) -> float:
    """Find the equilibrium altitude where net lift ≈ 0.

    Uses binary search over altitude to find where buoyant force
    equals vehicle weight.

    Args:
        gas_type: Lifting gas ("helium", "hydrogen", "hot_air", "methane")
        gas_mass_kg: Mass of lifting gas
        gas_temperature_k: Gas temperature in Kelvin
        total_vehicle_mass_kg: Total vehicle mass (gas + envelope + payload + ballast)
        envelope_max_volume: Max volume for zero-pressure envelopes
        contained_gas: If True, gas volume expands freely (latex/superpressure)

    Returns:
        Equilibrium altitude in meters. Returns -1 if no equilibrium exists
        (e.g., balloon is perpetually ascending or descending).
    """
    # Search range: sea level to 50 km
    alt_low = 0.0
    alt_high = 50000.0
    tol = 0.5  # tolerance in meters

    def net_lift(alt):
        """Net lift force at altitude alt."""
        P = atmosphere_pressure(alt)
        rho_air = atmosphere_density(alt)
        vol = gas_volume(gas_mass_kg, gas_type, gas_temperature_k, P)

        if not contained_gas:
            vol = min(vol, envelope_max_volume)

        rho_gas = gas_density(gas_type, gas_temperature_k, P)
        buoy = (rho_air - rho_gas) * G * vol
        weight = total_vehicle_mass_kg * G
        return buoy - weight

    # Check bounds
    lift_low = net_lift(alt_low)
    lift_high = net_lift(alt_high)

    # If lift is positive at both bounds, equilibrium is above our search range
    if lift_low > 0 and lift_high > 0:
        return -1  # Perpetually ascending
    # If lift is negative at both bounds, equilibrium is below sea level
    if lift_low < 0 and lift_high < 0:
        return 0  # Sits on the ground

    # Binary search
    for _ in range(100):  # Max iterations
        alt_mid = (alt_low + alt_high) / 2.0
        lift_mid = net_lift(alt_mid)

        if abs(lift_mid) < 0.01:  # Within 0.01 N ≈ 1 gram force
            return alt_mid

        if lift_mid > 0:
            # Still rising, go higher
            alt_low = alt_mid
        else:
            # Sinking, go lower
            alt_high = alt_mid

        if alt_high - alt_low < tol:
            return alt_mid

    return (alt_low + alt_high) / 2.0


def equilibrium_altitude_with_leakage(
    gas_type: str,
    gas_mass_kg: float,
    gas_temperature_k: float,
    total_vehicle_mass_kg: float,
    envelope_max_volume: float,
    contained_gas: bool = False,
    permeability: float = 0.0,
    simulation_time_s: float = 0.0,
) -> float:
    """Find equilibrium altitude accounting for gas leakage over time.

    Gas mass decreases over time due to permeability, which affects
    the equilibrium altitude.

    Args:
        gas_type: Lifting gas
        gas_mass_kg: Initial gas mass
        gas_temperature_k: Gas temperature
        total_vehicle_mass_kg: Initial total vehicle mass (includes initial gas mass)
        envelope_max_volume: Max envelope volume
        contained_gas: Contained (latex) vs zero-pressure
        permeability: Fraction of gas mass lost per second
        simulation_time_s: How many seconds into the simulation

    Returns:
        Equilibrium altitude in meters at the given time.
    """
    # Account for gas mass reduction due to leakage
    leak_factor = max(0.01, 1.0 - permeability * simulation_time_s)
    current_gas_mass = gas_mass_kg * leak_factor

    # Total mass decreases by the amount of gas lost
    gas_mass_change = gas_mass_kg - current_gas_mass
    current_total_mass = total_vehicle_mass_kg - gas_mass_change

    return equilibrium_altitude(
        gas_type=gas_type,
        gas_mass_kg=current_gas_mass,
        gas_temperature_k=gas_temperature_k,
        total_vehicle_mass_kg=current_total_mass,
        envelope_max_volume=envelope_max_volume,
        contained_gas=contained_gas,
    )
