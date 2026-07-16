"""Balloon Frontier - Wind Model

Implements atmospheric wind layers for balloon navigation.
Reference: Balloon Frontier GDD Section 6.7 (Wind layers).

Wind speed at a given altitude is modeled as a sum of sinusoidal layers
superimposed on a base geostrophic profile. All speeds in m/s, altitude in m.
"""

import math

# ─── Standard wind layers (Section 6.7) ────────────────────────
# Each layer: (bottom_alt_m, top_alt_m, base_speed_ms, direction_rad, amplitude_ms)
# Direction 0 = East (along x-axis), π/2 = North
STANDARD_WIND_LAYERS = [
    # Troposphere: light, somewhat erratic
    (0, 3000, 2.0, 0.5, 1.5),
    # Mid-troposphere: jet stream influence
    (3000, 8000, 5.0, 1.2, 3.0),
    # Lower stratosphere: stronger, more uniform
    (8000, 15000, 8.0, 1.0, 2.5),
    # Upper stratosphere: peak jet stream
    (15000, 25000, 12.0, 0.8, 4.0),
    # Mesosphere: thin air, moderate winds
    (25000, 40000, 6.0, 1.5, 3.0),
]


def wind_speed(alt_m, time_s=0.0):
    """Return wind speed at altitude (m/s).

    The model uses layered sinusoidal oscillation to simulate
    geostrophic wind profile plus diurnal variation.

    Args:
        alt_m: Altitude in meters above sea level
        time_s: Simulation time in seconds (affects diurnal variation)

    Returns:
        Wind speed in m/s (positive = in the dominant direction)
    """
    speed = 0.0
    for bot, top, base, _dir, amp in STANDARD_WIND_LAYERS:
        if bot <= alt_m <= top:
            # Base speed with sinusoidal variation
            diurnal_phase = 2.0 * math.pi * time_s / 86400.0  # 24h cycle
            speed = base + amp * math.sin(diurnal_phase + 0.5 * alt_m / 10000.0)
            break
    else:
        # Above all defined layers, extrapolate with mesosphere values
        speed = 6.0 + 3.0 * math.sin(0.5 * alt_m / 10000.0)

    return max(0.0, speed)


def wind_direction(alt_m, time_s=0.0):
    """Return wind direction at altitude (radians).

    Returns:
        Direction in radians (0 = East, π/2 = North)
    """
    for bot, top, _base, direction, amp in STANDARD_WIND_LAYERS:
        if bot <= alt_m <= top:
            # Direction shifts slightly with altitude within the layer
            layer_fractions = (alt_m - bot) / (top - bot)
            return direction + 0.2 * math.sin(layer_fractions * math.pi)
    # Default direction for extreme altitudes
    return 1.0


def wind_vector(alt_m, time_s=0.0):
    """Return wind velocity as (u, v) in m/s (East, North components).

    Args:
        alt_m: Altitude in meters
        time_s: Simulation time in seconds

    Returns:
        (u_mps, v_mps): Wind velocity components
    """
    speed = wind_speed(alt_m, time_s)
    direction = wind_direction(alt_m, time_s)
    u = speed * math.cos(direction)  # East component
    v = speed * math.sin(direction)  # North component
    return (u, v)


def wind_profile(altitudes: list, time_s=0.0):
    """Compute wind speeds across a list of altitudes.

    Args:
        altitudes: List of altitude values in meters
        time_s: Simulation time in seconds

    Returns:
        List of (alt_m, speed_ms, direction_rad) tuples
    """
    return [
        (alt, wind_speed(alt, time_s), wind_direction(alt, time_s))
        for alt in altitudes
    ]
