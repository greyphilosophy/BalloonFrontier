"""Balloon Frontier — Random Weather Event Generation.

Each launch gets randomized weather conditions that affect flight dynamics.
Weather is seeded deterministically so the same launch configuration produces
the same weather (reproducible gameplay).

Weather factors that affect flights:
  - wind_gust_factor: Multiplier on wind speed (1.0 = normal, 2.0+ = stormy)
  - temp_anomaly_k: Temperature offset from standard atmosphere (hot/cold)
  - cloud_density: Fraction of sky covered (affects solar heating)
  - pressure_offset_pa: Local pressure anomaly
  - storm_risk: Probability of burst-causing turbulence during flight

Reference: GDD Section 14.3 (Weather Model).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Dict, List, Optional


# ── Weather condition templates ────────────────────────────────────
# Each template defines a named weather event with narrative flavor.

@dataclass
class WeatherEvent:
    """A randomized weather event affecting a single flight."""

    wind_gust_factor: float       # 0.5 = calm, 2.0+ = storm
    temp_anomaly_k: float         # K offset from standard atmosphere
    cloud_density: float          # 0.0 (clear) to 1.0 (overcast)
    pressure_offset_pa: float     # Pa deviation from standard
    storm_risk: float             # 0.0 (safe) to 1.0 (dangerous)
    name: str                     # Human-readable event name
    description: str              # Narrative flavor text
    flight_modifier: str          # Short gameplay impact summary

    @property
    def severity(self) -> str:
        """Return severity level based on combined factors."""
        score = (
            max(0, self.wind_gust_factor - 1.0) * 30
            + abs(self.temp_anomaly_k) * 2
            + self.storm_risk * 20
        )
        if score < 10:
            return "🟢 Favorable"
        elif score < 25:
            return "🟡 Moderate"
        elif score < 40:
            return "🟠 Challenging"
        else:
            return "🔴 Hazardous"


# Weather condition templates by site type.
# Each template defines the probability distribution of factors.
SITE_WEATHER_TEMPLATES: Dict[str, Dict[str, tuple]] = {
    "field": {
        "wind_gust_factor": (0.7, 1.8),       # range, uniform
        "temp_anomaly_k": (-8.0, 8.0),
        "cloud_density": (0.0, 0.6),
        "pressure_offset_pa": (-500, 500),
        "storm_risk": (0.0, 0.2),
    },
    "mountain": {
        "wind_gust_factor": (1.0, 2.5),
        "temp_anomaly_k": (-15.0, 5.0),
        "cloud_density": (0.2, 0.8),
        "pressure_offset_pa": (-800, 200),
        "storm_risk": (0.1, 0.4),
    },
    "rooftop": {
        "wind_gust_factor": (0.8, 1.5),
        "temp_anomaly_k": (0.0, 12.0),
        "cloud_density": (0.0, 0.4),
        "pressure_offset_pa": (-200, 300),
        "storm_risk": (0.0, 0.15),
    },
}

# Named weather events for flavor text when randomization falls in certain ranges.
WEATHER_NAMES_BY_SEVERITY = {
    "favorable": [
        ("", "Calm conditions — the sky is clear and predictable."),
        ("", "Smooth sailing — perfect weather for a first launch."),
        ("", "Gentle breeze — ideal conditions for stable ascent."),
        ("", "A clear day — visibility stretches for miles."),
    ],
    "moderate": [
        ("", "Moderate winds — keep an eye on the drift."),
        ("", "Some cloud cover — solar heating will be reduced."),
        ("", "Unsettled air — expect occasional turbulence."),
        ("", "A mild temperature inversion — ascent rate may vary."),
    ],
    "challenging": [
        ("High Wind Advisory", "Strong crosswinds at multiple altitudes."),
        ("Pressure Dip", "A pocket of low pressure ahead — watch ascent rate."),
        ("Thermal Instability", "Extreme temperature swings in the troposphere."),
        ("Cloud Ceiling", "Dense cloud layers reducing visibility and solar heating."),
    ],
    "hazardous": [
        ("Storm Front", "Severe turbulence and lightning risk — this could be dangerous."),
        ("Jet Stream Crosswind", "Extreme wind shear at 15-20km altitude."),
        ("Temperature Inversion Wall", "A thermal barrier that could trap your balloon."),
        ("Pressure Crash", "A sudden pressure drop ahead — your balloon will expand rapidly."),
    ],
}


def _generate_weather_seed(gas: str, envelope: str, payloads: List[str], site: str) -> int:
    """Create a deterministic seed from launch configuration."""
    payload_str = ",".join(sorted(payloads))
    seed_str = f"weather|{gas}|{envelope}|{payload_str}|{site}"
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def generate_weather(
    site: str,
    gas: str = "helium",
    envelope: str = "latex",
    payloads: Optional[List[str]] = None,
    seed: Optional[int] = None,
) -> WeatherEvent:
    """Generate randomized weather conditions for a launch.

    Weather is deterministic: the same launch configuration always produces
    the same weather. This makes gameplay reproducible and fair.

    Args:
        site: Launch site identifier ('field', 'mountain', 'rooftop').
        gas: Gas type (used for seed).
        envelope: Envelope type (used for seed).
        payloads: List of payload identifiers (used for seed).
        seed: Optional explicit seed override.

    Returns:
        A WeatherEvent with randomized conditions.
    """
    if payloads is None:
        payloads = []

    if seed is None:
        seed = _generate_weather_seed(gas, envelope, payloads, site)

    rng = random.Random(seed)
    template = SITE_WEATHER_TEMPLATES.get(site, SITE_WEATHER_TEMPLATES["field"])

    # Sample each factor from its range
    wind_gust_factor = rng.uniform(*template["wind_gust_factor"])
    temp_anomaly_k = rng.uniform(*template["temp_anomaly_k"])
    cloud_density = rng.uniform(*template["cloud_density"])
    pressure_offset_pa = rng.uniform(*template["pressure_offset_pa"])
    storm_risk = rng.uniform(*template["storm_risk"])

    # Determine severity and pick flavor text
    score = (
        max(0, wind_gust_factor - 1.0) * 30
        + abs(temp_anomaly_k) * 2
        + storm_risk * 20
    )
    if score < 10:
        severity_key = "favorable"
    elif score < 25:
        severity_key = "moderate"
    elif score < 40:
        severity_key = "challenging"
    else:
        severity_key = "hazardous"

    name, description = rng.choice(WEATHER_NAMES_BY_SEVERITY[severity_key])

    # Determine flight modifier summary
    modifiers = []
    if wind_gust_factor > 1.5:
        modifiers.append("strong winds")
    elif wind_gust_factor < 0.9:
        modifiers.append("calm winds")
    if temp_anomaly_k > 5:
        modifiers.append("hot launch")
    elif temp_anomaly_k < -5:
        modifiers.append("cold launch")
    if cloud_density > 0.5:
        modifiers.append("cloudy")
    if pressure_offset_pa < -300:
        modifiers.append("low pressure")
    if storm_risk > 0.3:
        modifiers.append("storm risk")

    flight_modifier = f"{' and '.join(modifiers)}" if modifiers else "normal conditions"

    return WeatherEvent(
        wind_gust_factor=round(wind_gust_factor, 2),
        temp_anomaly_k=round(temp_anomaly_k, 1),
        cloud_density=round(cloud_density, 2),
        pressure_offset_pa=round(pressure_offset_pa, 0),
        storm_risk=round(storm_risk, 2),
        name=name,
        description=description,
        flight_modifier=flight_modifier,
    )


def weather_impact_on_flight(weather: WeatherEvent) -> Dict[str, float]:
    """Calculate how weather affects flight dynamics.

    Returns a dict of multiplicative modifiers applied to the base simulation.

    Args:
        weather: The WeatherEvent for this launch.

    Returns:
        Dict with keys: ascent_rate, burst_risk, thermal_efficiency, drift_factor
    """
    # Wind affects horizontal drift and vertical stability
    drift_factor = 1.0 + (weather.wind_gust_factor - 1.0) * 0.5
    drift_factor = max(0.5, min(2.0, drift_factor))

    # Temperature anomaly affects initial lift
    # Hot air reduces density → more initial lift but also faster expansion
    thermal_efficiency = 1.0 + (weather.temp_anomaly_k / 30.0) * 0.1
    thermal_efficiency = max(0.7, min(1.5, thermal_efficiency))

    # Storm risk increases burst probability
    burst_risk_modifier = 1.0 + weather.storm_risk * 1.5

    # Cloud density reduces solar heating (affects thermal model)
    solar_modifier = 1.0 - weather.cloud_density * 0.4

    # Pressure anomaly affects initial gas volume
    pressure_modifier = 1.0 + (weather.pressure_offset_pa / 101325.0) * 0.3

    return {
        "ascent_rate": thermal_efficiency * (1.0 + (weather.temp_anomaly_k / 50.0)),
        "burst_risk": burst_risk_modifier,
        "thermal_efficiency": solar_modifier,
        "drift_factor": drift_factor,
        "pressure_modifier": pressure_modifier,
    }


def format_weather_briefing(weather: WeatherEvent, site_name: str) -> str:
    """Format weather conditions into a launch briefing string.

    This is displayed to the player before they launch, giving them the
    information to make strategic choices.

    Args:
        weather: The WeatherEvent for this launch.
        site_name: Name of the launch site.

    Returns:
        Formatted briefing text.
    """
    lines = [f"🌤️ **Weather Briefing — {site_name}**\n"]

    if weather.name:
        lines.append(f"**{weather.name}**")

    if weather.description:
        lines.append(weather.description)

    lines.append("")
    lines.append(f"{weather.severity} conditions")

    lines.append(f"Wind: {'Calm 🍃' if weather.wind_gust_factor < 0.8 else 'Moderate 💨' if weather.wind_gust_factor < 1.3 else 'Strong 🌬️' if weather.wind_gust_factor < 1.8 else 'Stormy ⛈️'} ({weather.wind_gust_factor:.1f}x)")
    lines.append(f"Temperature: {'Cold ❄️' if weather.temp_anomaly_k < -5 else 'Normal 🌡️' if weather.temp_anomaly_k < 3 else 'Hot 🔥'} (±{weather.temp_anomaly_k:.0f}K)")
    lines.append(f"Sky: {'Clear ☀️' if weather.cloud_density < 0.3 else 'Partly cloudy ⛅' if weather.cloud_density < 0.6 else 'Overcast ☁️'}")
    lines.append(f"Storm Risk: {'None 🟢' if weather.storm_risk < 0.1 else 'Low 🟡' if weather.storm_risk < 0.25 else 'Moderant 🟠' if weather.storm_risk < 0.4 else 'High 🔴'} ({weather.storm_risk*100:.0f}%)")

    if weather.flight_modifier:
        lines.append(f"\n⚠️ Impact: {weather.flight_modifier}")

    return "\n".join(lines)