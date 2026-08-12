"""Balloon Frontier - Thermal Model

Lumped-capacitance thermal model for lighter-than-air vehicles.

Heat sources contribute power in watts. Gas identity is independent of thermal
state: ordinary air becomes less dense because its temperature rises, not
because the simulator changes it into a special ``hot air`` substance.

Q_dot = Q_solar + Q_heater + Q_equipment - Q_boundary - Q_radiation
T_next = T + (Q_dot / thermal_capacity) * dt
"""

import math
from balloon_frontier.physics import atmosphere_temperature

STEFAN_BOLTZMANN = 5.67e-8
SOLAR_CONSTANT = 1361.0

SPECIFIC_HEAT_J_KG_K = {
    "helium": 5193.0,
    "hydrogen": 14300.0,
    "air": 1005.0,
    "hot_air": 1005.0,
    "methane": 2214.0,
}


def solar_flux_at_altitude(altitude_m: float) -> float:
    """Approximate solar flux at a given altitude (W/m^2)."""
    scale_height = 8000.0
    return SOLAR_CONSTANT * (0.75 + 0.25 * (1 - math.exp(-altitude_m / scale_height)))


def solar_absorbed(flux: float, absorptivity: float, area_m2: float) -> float:
    """Heat gained from solar absorption over projected area."""
    return flux * absorptivity * area_m2


def ir_radiated(emissivity: float, area_m2: float, temp_K: float, temp_env_K: float) -> float:
    """Net IR radiation over membrane surface area."""
    return emissivity * STEFAN_BOLTZMANN * area_m2 * (temp_K ** 4 - temp_env_K ** 4)


def convective_heat_transfer(convection_coefficient: float, area_m2: float, temp_K: float, temp_air_K: float) -> float:
    """Convective heat flow over membrane surface area."""
    return convection_coefficient * area_m2 * (temp_K - temp_air_K)


def effective_thermal_resistance(
    nominal_resistance_m2_k_w: float,
    inflation_fraction: float,
    inflation_heat_loss_exponent: float = 0.0,
    stretch_start_fraction: float = 1.0,
) -> float:
    """Return effective gas-to-ambient resistance after inflation/stretch."""
    nominal = max(1e-4, float(nominal_resistance_m2_k_w))
    start = max(1e-6, float(stretch_start_fraction))
    fraction = max(0.0, float(inflation_fraction))
    stretch = max(1.0, fraction / start)
    exponent = max(0.0, float(inflation_heat_loss_exponent))
    return max(1e-4, nominal / (stretch ** exponent))


def envelope_heat_transfer(
    thermal_resistance_m2_k_w: float,
    area_m2: float,
    temp_K: float,
    temp_air_K: float,
) -> float:
    """Effective gas-to-ambient boundary loss: Q = A ΔT / R."""
    resistance = max(1e-4, float(thermal_resistance_m2_k_w))
    return area_m2 * (temp_K - temp_air_K) / resistance


def thermal_node_update(
    temp_K: float,
    mass_kg: float,
    specific_heat_j_kg_k: float,
    heat_flow_watts: float,
    dt: float,
) -> float:
    """Update a thermal node from net power."""
    thermal_capacity = mass_kg * specific_heat_j_kg_k
    if thermal_capacity <= 0.0:
        return temp_K
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
    thermal_resistance_m2_k_w: float | None = None,
    inflation_fraction: float = 1.0,
    inflation_heat_loss_exponent: float = 0.0,
    stretch_start_fraction: float = 1.0,
    solar_projected_area_m2: float | None = None,
) -> dict:
    """Calculate thermal power flows for one gas/envelope state.

    Membrane-aware callers provide an effective gas-to-ambient resistance; it
    already includes the boundary path, so explicit convection is used only for
    legacy callers without a material resistance.
    """
    ambient_temp = atmosphere_temperature(altitude_m)
    solar_flux = solar_flux_at_altitude(altitude_m)
    projected_area = (
        envelope_area_m2
        if solar_projected_area_m2 is None
        else max(0.0, float(solar_projected_area_m2))
    )

    Q_solar = solar_absorbed(solar_flux, envelope_absorptivity, projected_area)
    Q_radiation = ir_radiated(envelope_emissivity, envelope_area_m2, gas_temp_K, ambient_temp)
    Q_heater = max(0.0, float(heater_power_watts))
    Q_equipment = float(equipment_heat_watts)

    effective_resistance = None
    Q_envelope = 0.0
    if thermal_resistance_m2_k_w is None:
        Q_convection = convective_heat_transfer(
            0.5, envelope_area_m2, gas_temp_K, ambient_temp
        )
    else:
        Q_convection = 0.0
        effective_resistance = effective_thermal_resistance(
            thermal_resistance_m2_k_w,
            inflation_fraction,
            inflation_heat_loss_exponent,
            stretch_start_fraction,
        )
        Q_envelope = envelope_heat_transfer(
            effective_resistance,
            envelope_area_m2,
            gas_temp_K,
            ambient_temp,
        )

    Q_total = (
        Q_solar
        + Q_heater
        + Q_equipment
        - Q_radiation
        - Q_convection
        - Q_envelope
    )

    return {
        "Q_solar": Q_solar,
        "Q_convection": Q_convection,
        "Q_radiation": Q_radiation,
        "Q_envelope": Q_envelope,
        "Q_heater": Q_heater,
        "Q_equipment": Q_equipment,
        "Q_total": Q_total,
        "ambient_temperature": ambient_temp,
        "effective_thermal_resistance_m2_k_w": effective_resistance,
        "inflation_fraction": inflation_fraction,
    }


def gas_temperature_update(
    gas_type: str,
    gas_mass_kg: float,
    gas_temp_K: float,
    heat_flows: dict,
    dt: float,
    target_heater_temp_K: float | None = None,
) -> float:
    """Update any gas from its energy balance."""
    c = SPECIFIC_HEAT_J_KG_K.get(gas_type, 1005.0)
    if target_heater_temp_K is not None:
        return _compatibility_thermostat_update(gas_temp_K, target_heater_temp_K, dt)
    heat_flow = float(heat_flows.get("Q_total", 0.0))
    return thermal_node_update(gas_temp_K, gas_mass_kg, c, heat_flow, dt)


def _compatibility_thermostat_update(
    gas_temp_K: float,
    target_temp_K: float,
    dt: float,
) -> float:
    """Generic legacy thermostat retained for source compatibility only."""
    if gas_temp_K < target_temp_K:
        rate = 1.0 / 30.0
        return gas_temp_K + (target_temp_K - gas_temp_K) * (
            1.0 - math.exp(-rate * dt)
        )
    if gas_temp_K > target_temp_K:
        rate = 1.0 / 60.0
        return gas_temp_K - (gas_temp_K - target_temp_K) * (
            1.0 - math.exp(-rate * dt)
        )
    return gas_temp_K
