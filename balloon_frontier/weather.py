"""Balloon Frontier - Weather Model

Implements time-of-day effects (diurnal temperature curve), wind layer
variation, and cloud layers for the balloon simulation.

Reference: GDD Sections 6.7, 14.3.
"""

import math

# Diurnal temperature model constants
T_MEAN_SEA_LEVEL_K = 285.65  # Mean sea level temperature ~12.5°C
T_SWING = 12.5               # Diurnal swing in Kelvin
T_MAX_HOUR = 14.0           # Temperature peaks at 2 PM

# Wind model constants
WIND_BASE_SPEED_MPS = 3.0   # Base wind speed at sea level
WIND_DIURNAL_AMPLITUDE = 0.4  # Diurnal variation amplitude
WIND_MAX_HOUR = 12.0       # Wind peaks at noon

# Cloud model constants
CLOUD_BASE_ALTITUDES_M = [800, 2000, 4500, 8000, 15000]
CLOUD_THICKNESS_M = 1500
VISIBILITY_CLEAR = 1.0
VISIBILITY_CLOUD = 0.6


def diurnal_temperature(hour: float, altitude_m: float, lapse_rate: float = 0.0065) -> float:
    """Calculate temperature at a given hour and altitude.

    Uses a cosine curve peaking at T_MAX_HOUR.
    Returns temperature in Kelvin.
    """
    # Cosine curve: peaks at T_MAX_HOUR
    diurnal_factor = math.cos(2 * math.pi * (hour - T_MAX_HOUR) / 24.0)
    t_sea_level = T_MEAN_SEA_LEVEL_K + T_SWING * diurnal_factor
    # Apply lapse rate
    return t_sea_level - (lapse_rate * altitude_m)


def get_diurnal_wind_speed(hour: float, altitude_m: float) -> float:
    """Get wind speed adjusted for hour of day.

    Wind peaks at WIND_MAX_HOUR (noon) and bottoms out at midnight.
    """
    # Cosine curve: peaks at WIND_MAX_HOUR
    wind_factor = math.cos(2 * math.pi * (hour - WIND_MAX_HOUR) / 24.0)
    # Altitude increases wind speed
    alt_factor = 1.0 + math.log10(1 + altitude_m / 5000.0) * 0.3
    base = WIND_BASE_SPEED_MPS * alt_factor
    return base * (1 + WIND_DIURNAL_AMPLITUDE * wind_factor)


def is_in_cloud(altitude_m: float, hour: float) -> bool:
    """Check if the balloon is currently in a cloud layer.

    Cloud layers shift with convection (higher during day, lower at night).
    """
    hour_frac = (hour - 6.0) / 24.0
    shift = math.sin(2 * math.pi * hour_frac) * 500  # ±500m shift
    for base in CLOUD_BASE_ALTITUDES_M:
        base_shifted = base + shift
        if base_shifted <= altitude_m <= base_shifted + CLOUD_THICKNESS_M:
            return True
    return False


def get_visibility(altitude_m: float, hour: float) -> float:
    """Get visibility factor (0-1) at given altitude and hour."""
    if is_in_cloud(altitude_m, hour):
        return VISIBILITY_CLOUD
    return VISIBILITY_CLEAR


def get_cloud_coverage(altitude_m: float, hour: float) -> float:
    """Get fractional cloud coverage at altitude (0-1)."""
    coverage = 0.0
    hour_frac = (hour - 6.0) / 24.0
    shift = math.sin(2 * math.pi * hour_frac) * 500
    for base in CLOUD_BASE_ALTITUDES_M:
        base_shifted = base + shift
        if base_shifted <= altitude_m <= base_shifted + CLOUD_THICKNESS_M:
            coverage += 0.2
    return min(coverage, 1.0)


def get_weather_summary(hour: float, altitude_m: float) -> dict:
    """Get a weather summary at a given hour and altitude."""
    return {
        "temperature_k": diurnal_temperature(hour, altitude_m),
        "wind_speed_mps": get_diurnal_wind_speed(hour, altitude_m),
        "visibility": get_visibility(altitude_m, hour),
        "in_cloud": is_in_cloud(altitude_m, hour),
        "cloud_coverage": get_cloud_coverage(altitude_m, hour),
        "hour": hour,
        "altitude_m": altitude_m,
    }
