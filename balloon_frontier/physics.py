"""Balloon Frontier - Physics Engine

Implements the physics model for the balloon simulation game.
Reference: Balloon Frontier GDD Sections 6, 13, 16.

All calculations use SI units internally as specified in the GDD.
"""

import math

# ─── Physical Constants (GDD Appendix A) ───────────────────────────

G = 9.80665                 # Standard gravity (m/s²)
R = 8.314462618            # Universal gas constant (J/(mol·K))
R_AIR = 287.05             # Specific gas constant for dry air (J/(kg·K))
SEA_LEVEL_PRESSURE = 101325.0   # Pa
SEA_LEVEL_TEMPERATURE = 288.15 # K

# Molar masses (kg/mol)
MOLAR_MASS = {
    "helium": 0.0040026,
    "hydrogen": 0.002016,
    "hot_air": 0.02897,
    "methane": 0.01604,
}

# ─── US Standard Atmosphere (Section 6.2) ─────────────────────────

def _find_layer(alt_m):
    """Find the appropriate layer index for a given altitude."""
    # Layers: (bottom_km, top_km, base_temp_K, lapse_K_m, base_pressure_PA)
    layers = [
        (0.0, 11.0, 288.15, -0.0065, 101325.0),
        (11.0, 20.0, 216.65, 0.0, 22632.0),
        (20.0, 50.0, 216.65, 0.001, 5401.0),
    ]
    # Find the layer, handling exact boundaries
    for i, (bot_km, top_km, _, _, _) in enumerate(layers):
        if alt_m <= top_km * 1000.0:
            return i
    return len(layers) - 1  # Last layer for anything above


def atmosphere_temperature(alt_m):
    """US Standard Atmosphere temperature at altitude (K)."""
    layers = [
        (0.0, 11.0, 288.15, -0.0065),
        (11.0, 20.0, 216.65, 0.0),
        (20.0, 50.0, 216.65, 0.001),
    ]
    idx = _find_layer(alt_m)
    bot_km, _, t_base, lapse = layers[idx]
    return t_base + lapse * (alt_m - bot_km * 1000.0)


def atmosphere_pressure(alt_m):
    """US Standard Atmosphere pressure at altitude (Pa)."""
    layers = [
        (0.0, 11.0, 288.15, -0.0065, 101325.0),
        (11.0, 20.0, 216.65, 0.0, 22632.0),
        (20.0, 50.0, 216.65, 0.001, 5401.0),
    ]
    idx = _find_layer(alt_m)
    bot_km, _, t_base, lapse, p_base = layers[idx]
    delta_m = alt_m - bot_km * 1000.0

    if abs(lapse) < 1e-5:
        # Isothermal layer: P = P0 * exp(-g * Δz / (R * T))
        exponent = -G * delta_m / (R_AIR * t_base)
        return p_base * math.exp(exponent)
    else:
        # Lapse layer: P = P0 * (T/T0)^(-g/(R*L))
        T = t_base + lapse * delta_m
        temp_ratio = T / t_base
        exponent = -G / (R_AIR * lapse)
        return p_base * (temp_ratio ** exponent)


def atmosphere_density(alt_m):
    """Air density at altitude (kg/m³) using ideal gas law: ρ = P / (R_air * T)."""
    return atmosphere_pressure(alt_m) / (R_AIR * atmosphere_temperature(alt_m))


# ─── Gas Calculations (Section 6.3) ───────────────────────────────

def gas_volume(mass_kg, gas_type, temp_K, pressure_PA):
    """Ideal gas law: V = nRT/P = (mass/molar_mass) * R * T / P"""
    n = mass_kg / MOLAR_MASS[gas_type]
    return n * R * temp_K / pressure_PA


def gas_density(gas_type, temp_K, pressure_PA):
    """Density of a gas at given T and P."""
    return pressure_PA / ((R / MOLAR_MASS[gas_type]) * temp_K)


# ─── Buoyancy (Section 6.4) ───────────────────────────────────────

def buoyant_force(gas_type, gas_mass_kg, gas_temp_K, alt_m):
    """Net buoyant lift force (N) = (ρ_air - ρ_gas) * g * V."""
    rho_air = atmosphere_density(alt_m)
    p = atmosphere_pressure(alt_m)
    vol = gas_volume(gas_mass_kg, gas_type, gas_temp_K, p)
    rho_gas = gas_density(gas_type, gas_temp_K, p)
    return (rho_air - rho_gas) * G * vol


# ─── Drag (Section 6.6) ──────────────────────────────────────────

def drag_force(velocity_mps, alt_m, drag_coefficient, area_m2):
    """Aerodynamic drag: F = 0.5 * ρ * |v|² * C_d * A"""
    rho = atmosphere_density(alt_m)
    return 0.5 * rho * (velocity_mps ** 2) * drag_coefficient * area_m2


# ─── Geometry (Sections 6.5, 7) ──────────────────────────────────

def spherical_area(volume_m3):
    """Frontal area of a sphere from volume: A = π * r², V = 4/3 * π * r³"""
    r = (3 * volume_m3 / (4 * math.pi)) ** (1.0 / 3.0)
    return math.pi * r * r


def burst_volume(burst_stretch_ratio, initial_volume):
    """Maximum volume before envelope bursts."""
    return burst_stretch_ratio * initial_volume
