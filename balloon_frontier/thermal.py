"""Balloon Frontier - Thermal Model

Implements lumped-capacitance thermal model for balloon vehicles.
Reference: GDD Section 6.7 (Thermal Model).

Tracks gas, envelope, payload, and battery temperatures as thermal nodes
with heat flows from solar absorption, IR radiation, convection, and
electrical heating.

Q_dot = Q_solar + Q_heater + Q_equipment - Q_convection - Q_radiation
T_next = T + (Q_dot / thermal_capacity) * dt
"""

import math
from balloon_frontier.physics import atmosphere_temperature, atmosphere_density, G

# Stefan-Boltzmann constant (W/m^4*K^4)
STEFAN_BOLTZMANN = 5.67e-8

# Solar constant at 1 AU (W/m^2)
SOLAR_CONSTANT = 1361.0


def solar_flux_at_altitude(altitude_m: float) -> float:
    """Approximate solar flux at a given altitude (W/m^2).

    Solar flux increases with altitude as atmospheric attenuation decreases.
    Sea level ≈ 75% of S0, space ≈ 100% of S0.
    flux = S0 * (0.75 + 0.25 * (1 - exp(-alt/H)))
    """
    scale_height = 8000.0
    return SOLAR_CONSTANT * (0.75 + 0.25 * (1 - math.exp(-altitude_m / scale_height)))


def solar_absorbed(flux: float, absorptivity: float, area_m2: float) -> float:
    """Heat gained from solar absorption: Q = α * S * A (Watts)"""
    return flux * absorptivity * area_m2


def ir_radiated(emissivity: float, area_m2: float, temp_K: float, temp_env_K: float) -> float:
    """Net IR radiation: Q = ε * σ * A * (T^4 - T_env^4) (Watts)"""
    return emissivity * STEFAN_BOLTZMANN * area_m2 * (temp_K ** 4 - temp_env_K ** 4)


def convective_heat_transfer(convection_coefficient: float, area_m2: float, temp_K: float, temp_air_K: float) -> float:
    """Convective heat flow: Q = h * A * (T - T_air) (Watts)"""
    return convection_coefficient * area_m2 * (temp_K - temp_air_K)


def thermal_node_update(
    temp_K: float,
    mass_kg: float,
    specific_heat_j_kg_k: float,
    heat_flow_watts: float,
    dt: float,
) -> float:
    """Update temperature of a thermal node using:
    T_next = T + (Q_dot / (m * c)) * dt
    
    Returns new temperature in Kelvin.
    """
    thermal_capacity = mass_kg * specific_heat_j_kg_k
    return temp_K + (heat_flow_watts / thermal_capacity) * dt


def calculate_balloon_heat_flows(
    altitude_m: float,
    gas_temp_K: float,
    gas_mass_kg: float,
    gas_type: str,
    envelope_absorptivity: float,
    envelope_emissivity: float,
    envelope_area_m2: float,
    envelope_mass_kg: float,
    heater_power_watts: float,
    equipment_heat_watts: float,
) -> dict:
    """Calculate all heat flows for a balloon at a given state.

    Returns dict with Q_solar, Q_convection, Q_radiation, Q_heater,
    Q_equipment, Q_total, and resulting temperature rates of change.
    """
    ambient_temp = atmosphere_temperature(altitude_m)
    solar_flux = solar_flux_at_altitude(altitude_m)

    Q_solar = solar_absorbed(solar_flux, envelope_absorptivity, envelope_area_m2)
    Q_radiation = ir_radiated(envelope_emissivity, envelope_area_m2, gas_temp_K, ambient_temp)
    Q_convection = convective_heat_transfer(0.5, envelope_area_m2, gas_temp_K, ambient_temp)
    Q_heater = heater_power_watts
    Q_equipment = equipment_heat_watts
    Q_total = Q_solar + Q_heater + Q_equipment - Q_radiation - Q_convection

    return {
        "Q_solar": Q_solar,
        "Q_convection": Q_convection,
        "Q_radiation": Q_radiation,
        "Q_heater": Q_heater,
        "Q_equipment": Q_equipment,
        "Q_total": Q_total,
        "ambient_temperature": ambient_temp,
    }


def gas_temperature_update(
    gas_type: str,
    gas_mass_kg: float,
    gas_temp_K: float,
    heat_flows: dict,
    dt: float,
) -> float:
    """Update gas temperature based on heat flows.
    
    Specific heat of helium ~5193 J/(kg·K), hydrogen ~14300, etc.
    """
    specific_heats = {
        "helium": 5193.0,
        "hydrogen": 14300.0,
        "hot_air": 1005.0,
        "methane": 2214.0,
    }
    c = specific_heats.get(gas_type, 1005.0)
    heat_flow = heat_flows["Q_total"]
    return thermal_node_update(gas_temp_K, gas_mass_kg, c, heat_flow, dt)
