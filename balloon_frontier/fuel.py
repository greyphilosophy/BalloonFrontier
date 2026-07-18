"""Balloon Frontier - Fuel & Descent System

Implements fuel consumption models for balloon vehicles:
- Gas permeability (slow leak through envelope material)
- Heater fuel burn (consumes gas mass for thermal lift)
- Battery drain (payload power consumption)

Also models landing mechanics:
- Hot air balloons save fuel for ideal soft landing (burn fuel → slow descent)
- Parachute-equipped balloons exhaust fuel first, then deploy parachute
- Landing score based on altitude, velocity, payload mass

Reference: GDD Sections 6.2, 6.7, 14.2, 16.
"""

import math

# Fuel consumption constants
HEATER_FUEL_BURN_RATE_KG_PER_S = 0.002  # Helium burned per second when heater is on
FUEL_RESERVE_FRACTION = 0.15  # Reserve 15% of fuel for landing

# Descent parameters
HOT_AIR_DESCENT_RATE_MPS = 0.8  # Controlled descent with fuel
PARACHUTE_DESCENT_RATE_MPS = 1.2  # Parachute deployment descent
FREE_FALL_DESCENT_RATE_MPS = 3.5  # No fuel, no parachute

# Landing scoring
MAX_LANDING_ALTITUDE_M = 100  # Above this = crash
SAFE_LANDING_VELOCITY_MPS = 2.0  # Below this = gentle landing
CRASH_VELOCITY_MPS = 8.0  # Above this = hard landing
IDEAL_LANDING_SCORE = 100


def calculate_fuel_consumption(
    fuel_type: str,
    fuel_mass_kg: float,
    heater_on: bool,
    heater_power_fraction: float,
    battery_on: bool,
    battery_capacity_wh: float,
    battery_drain_rate_watts: float,
    permeability: float,
    elapsed_time_s: float,
) -> dict:
    """Calculate fuel consumption over elapsed time.

    Returns dict with remaining fuel mass, consumed fuel, battery state.
    """
    # Gas permeability loss (permeability is fraction lost per second at sea level)
    permeability_loss = fuel_mass_kg * permeability * elapsed_time_s
    fuel_mass_after_permeability = max(fuel_mass_kg - permeability_loss, 0)

    # Heater fuel consumption
    heater_consumption = 0.0
    if heater_on:
        heater_consumption = HEATER_FUEL_BURN_RATE_KG_PER_S * heater_power_fraction * elapsed_time_s
        fuel_mass_after_heater = max(fuel_mass_after_permeability - heater_consumption, 0)
    else:
        fuel_mass_after_heater = fuel_mass_after_permeability

    # Battery drain (independent of fuel)
    battery_remaining_wh = battery_capacity_wh - (battery_drain_rate_watts * elapsed_time_s / 1000)
    battery_remaining_wh = max(battery_remaining_wh, 0)
    battery_percentage = battery_remaining_wh / battery_capacity_wh * 100 if battery_capacity_wh > 0 else 100

    return {
        "fuel_mass_remaining_kg": fuel_mass_after_heater,
        "fuel_consumed_by_permeability_kg": permeability_loss,
        "fuel_consumed_by_heater_kg": heater_consumption,
        "fuel_total_consumed_kg": permeability_loss + heater_consumption,
        "battery_remaining_wh": battery_remaining_wh,
        "battery_percentage": min(battery_percentage, 100),
        "fuel_reserved_kg": fuel_mass_after_heater * FUEL_RESERVE_FRACTION,
        "fuel_usable_kg": fuel_mass_after_heater * (1 - FUEL_RESERVE_FRACTION),
    }


def has_fuel_for_safe_landing(fuel_remaining_kg: float, payload_mass_kg: float) -> bool:
    """Check if there's enough fuel for a controlled descent."""
    fuel_needed = payload_mass_kg * 0.1
    return fuel_remaining_kg >= fuel_needed


def calculate_landing_score(
    landing_method: str,
    landing_altitude_m: float,
    landing_velocity_mps: float,
) -> dict:
    """Calculate landing quality score (0-100).

    landing_method should be one of: "controlled_hot_air", "parachute", "free_fall".
    """
    score = 100.0

    # Altitude penalty (higher = longer fall = harder landing)
    if landing_altitude_m > MAX_LANDING_ALTITUDE_M:
        score -= min((landing_altitude_m - MAX_LANDING_ALTITUDE_M) / 10, 40)

    # Velocity penalty
    if landing_velocity_mps > SAFE_LANDING_VELOCITY_MPS:
        score -= min((landing_velocity_mps - SAFE_LANDING_VELOCITY_MPS) / SAFE_LANDING_VELOCITY_MPS * 20, 40)
    if landing_velocity_mps > CRASH_VELOCITY_MPS:
        score -= min((landing_velocity_mps - CRASH_VELOCITY_MPS) / CRASH_VELOCITY_MPS * 30, 30)

    score = max(0, score)

    return {
        "score": score,
        "landing_method": landing_method,
        "altitude_m": landing_altitude_m,
        "velocity_mps": landing_velocity_mps,
        "is_crash": landing_velocity_mps > CRASH_VELOCITY_MPS,
        "is_safe": landing_velocity_mps <= SAFE_LANDING_VELOCITY_MPS,
    }


def simulate_landing_sequence(
    start_altitude_m: float,
    start_velocity_mps: float,
    fuel_remaining_kg: float,
    has_parachute: bool,
    has_hot_air: bool,
    payload_mass_kg: float,
) -> dict:
    """Simulate the descent sequence from peak altitude to landing.

    Returns landing details: time, altitude, velocity, score.

    Hot air balloons with sufficient fuel: controlled slow descent.
    Parachute balloons: burn fuel during descent, then deploy parachute.
    No fuel, no parachute: free fall.
    """
    # Determine landing method
    if has_hot_air and has_fuel_for_safe_landing(fuel_remaining_kg, payload_mass_kg):
        # Controlled hot air descent using fuel
        landing_vel = HOT_AIR_DESCENT_RATE_MPS
        landing_alt = 0.0
        return calculate_landing_score("controlled_hot_air", landing_alt, landing_vel)

    if has_parachute:
        # Parachute: burn fuel during descent, then parachute
        if fuel_remaining_kg > 0:
            # Burn remaining fuel while descending (hot air rate)
            fuel_burn_rate = HEATER_FUEL_BURN_RATE_KG_PER_S
            fuel_duration = fuel_remaining_kg / fuel_burn_rate
            fuel_burn_distance = HOT_AIR_DESCENT_RATE_MPS * fuel_duration
            remaining_alt = max(start_altitude_m - fuel_burn_distance, 0)

            # Parachute descent from remaining altitude
            landing_vel = PARACHUTE_DESCENT_RATE_MPS
            return calculate_landing_score("parachute", 0.0, landing_vel)
        else:
            # No fuel, parachute still available
            landing_vel = PARACHUTE_DESCENT_RATE_MPS
            return calculate_landing_score("parachute", 0.0, landing_vel)

    # Free fall (no fuel, no parachute)
    landing_time = math.sqrt(2 * start_altitude_m / 9.80665)
    landing_vel = 9.80665 * landing_time
    return calculate_landing_score("free_fall", 0.0, landing_vel)
