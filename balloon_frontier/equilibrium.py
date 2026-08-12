"""Balloon Frontier - Equilibrium Altitude Calculator

Finds the altitude at which a balloon achieves neutral buoyancy
(Archimedean buoyancy = total vehicle weight).

Reference: GDD Section 6.8 (Equilibrium/floating altitude).
"""

from balloon_frontier.physics import (
    atmosphere_pressure,
    atmosphere_density,
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
    """Find the equilibrium altitude where net lift is approximately zero.

    ``total_vehicle_mass_kg`` includes the lifting gas. Therefore Archimedean
    buoyancy is the weight of displaced ambient air; gas weight must not also be
    subtracted inside the buoyancy term.
    """
    alt_low = 0.0
    alt_high = 50000.0
    tol = 0.5

    def net_lift(alt):
        P = atmosphere_pressure(alt)
        rho_air = atmosphere_density(alt)
        vol = gas_volume(gas_mass_kg, gas_type, gas_temperature_k, P)

        if not contained_gas:
            vol = min(vol, envelope_max_volume)

        archimedean_buoyancy = rho_air * G * vol
        weight = total_vehicle_mass_kg * G
        return archimedean_buoyancy - weight

    lift_low = net_lift(alt_low)
    lift_high = net_lift(alt_high)

    if lift_low > 0 and lift_high > 0:
        return -1
    if lift_low < 0 and lift_high < 0:
        return 0

    for _ in range(100):
        alt_mid = (alt_low + alt_high) / 2.0
        lift_mid = net_lift(alt_mid)

        if abs(lift_mid) < 0.01:
            return alt_mid

        if lift_mid > 0:
            alt_low = alt_mid
        else:
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
    """Find equilibrium altitude accounting for gas leakage over time."""
    leak_factor = max(0.01, 1.0 - permeability * simulation_time_s)
    current_gas_mass = gas_mass_kg * leak_factor

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
