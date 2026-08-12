"""Balloon Frontier — Physics Engine

All equations use SI units (GDD Sections 6, 13, Appendix A).
"""

import math

# Physical constants (GDD Appendix A)
G = 9.80665
R = 8.314462618
R_AIR = 287.05
SEA_LEVEL_PRESSURE = 101325.0
SEA_LEVEL_TEMPERATURE = 288.15

# Molar masses (kg/mol).  ``air`` is the physical gas; ``hot_air`` remains a
# backward-compatible identifier with exactly the same composition.  Heating
# changes temperature, not gas identity.
MOLAR_MASS = {
    "helium": 0.0040026,
    "hydrogen": 0.002016,
    "air": 0.0289652068,
    "hot_air": 0.0289652068,
    "methane": 0.01604,
}


# US Standard Atmosphere layers
def _find_layer(alt_m):
    layers = [
        (0.0, 11.0, 288.15, -0.0065, 101325.0),
        (11.0, 20.0, 216.65, 0.0, 22632.0),
        (20.0, 50.0, 216.65, 0.001, 5401.0),
    ]
    for i, (bot, top, _, _, _) in enumerate(layers):
        if alt_m <= top * 1000:
            return i
    return len(layers) - 1


def _standard_atmosphere_temperature(alt_m):
    """Standard-atmosphere temperature without provider dispatch."""
    layers = [
        (0.0, 11.0, 288.15, -0.0065),
        (11.0, 20.0, 216.65, 0.0),
        (20.0, 50.0, 216.65, 0.001),
    ]
    idx = _find_layer(alt_m)
    bot, _, t_base, lapse = layers[idx]
    return t_base + lapse * (alt_m - bot * 1000)


def _standard_atmosphere_pressure(alt_m):
    """Standard-atmosphere pressure without provider dispatch."""
    layers = [
        (0.0, 11.0, 288.15, -0.0065, 101325.0),
        (11.0, 20.0, 216.65, 0.0, 22632.0),
        (20.0, 50.0, 216.65, 0.001, 5401.0),
    ]
    idx = _find_layer(alt_m)
    bot, _, t_base, lapse, p_base = layers[idx]
    delta_m = alt_m - bot * 1000
    if abs(lapse) < 1e-5:
        return p_base * math.exp(-G * delta_m / (R_AIR * t_base))
    temperature = t_base + lapse * delta_m
    return p_base * (temperature / t_base) ** (-G / (R_AIR * lapse))


def _active_sample(alt_m):
    # Lazy import avoids a module cycle: atmosphere providers use the raw
    # standard-atmosphere functions above for their default implementation.
    from balloon_frontier.atmosphere import current_atmosphere_provider

    provider = current_atmosphere_provider()
    if provider is None:
        return None
    return provider.sample(max(0.0, float(alt_m)))


def atmosphere_temperature(alt_m):
    """Temperature at altitude (K), including an active replay provider."""
    sample = _active_sample(alt_m)
    if sample is not None:
        return sample.temperature_k
    return _standard_atmosphere_temperature(alt_m)


def atmosphere_pressure(alt_m):
    """Pressure at altitude (Pa), including an active replay provider."""
    sample = _active_sample(alt_m)
    if sample is not None:
        return sample.pressure_pa
    return _standard_atmosphere_pressure(alt_m)


def atmosphere_density(alt_m):
    """Air density at altitude (kg/m³)."""
    return atmosphere_pressure(alt_m) / (R_AIR * atmosphere_temperature(alt_m))


def gas_volume(mass_kg, gas_type, temp_K, pressure_PA):
    """Ideal gas law: V = nRT/P."""
    n = mass_kg / MOLAR_MASS[gas_type]
    return n * R * temp_K / pressure_PA


def gas_density(gas_type, temp_K, pressure_PA):
    """Density of a gas at given T and P."""
    return pressure_PA / ((R / MOLAR_MASS[gas_type]) * temp_K)


def buoyant_force(gas_type, gas_mass, gas_temp, alt_m):
    """Net buoyant lift force (N) = (ρ_air - ρ_gas) × g × V."""
    rho_air = atmosphere_density(alt_m)
    pressure = atmosphere_pressure(alt_m)
    volume = gas_volume(gas_mass, gas_type, gas_temp, pressure)
    rho_gas = gas_density(gas_type, gas_temp, pressure)
    return (rho_air - rho_gas) * G * volume


def drag_force(vel, alt_m, drag_coeff, area_m2):
    """Aerodynamic drag: F = 0.5 × ρ × v² × Cd × A."""
    rho = atmosphere_density(alt_m)
    return 0.5 * rho * (vel ** 2) * drag_coeff * area_m2


def spherical_area(volume_m3):
    """Frontal area of a sphere from volume: A = πr², V = 4/3πr³."""
    radius = (3 * volume_m3 / (4 * math.pi)) ** (1/3)
    return math.pi * radius * radius


def burst_volume(stretch_ratio, initial_volume):
    """Max volume before burst."""
    return stretch_ratio * initial_volume
