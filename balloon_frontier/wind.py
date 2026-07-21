"""Balloon Frontier - Wind Model

Implements atmospheric wind layers for balloon navigation.

The base wind field is modeled as layered sinusoidal oscillations (diurnal
variation + a simple altitude-dependent profile), then modified by
site-specific deterministic gust patterns.

All speeds are m/s, altitude is m.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ─── Standard wind layers (Section 6.7) ────────────────────────
# Each layer: (bottom_alt_m, top_alt_m, base_speed_ms, direction_rad, amplitude_ms)
# Direction 0 = East (along x-axis), π/2 = North
STANDARD_WIND_LAYERS: List[Tuple[float, float, float, float, float]] = [
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


DEFAULT_SITE_ID = "field"


# Wind speeds are intentionally capped to keep the sim stable.
MAX_WIND_SPEED_MPS = 24.0


@dataclass(frozen=True)
class WindSiteParams:
    """Site-specific wind configuration.

    gust_shape options:
      - "sinusoidal": simple bounded sine gust
      - "noise": deterministic multi-sine gust (still fully deterministic)
    """

    # Baseline wind at sea level (used to scale the standard layered profile)
    base_speed_ms: float

    # Gust strength added/subtracted from the base wind (bounded)
    gust_amplitude_ms: float

    # Period for the primary gust oscillation (seconds)
    gust_period_s: float

    # Gust wave shape (deterministic)
    gust_shape: str = "sinusoidal"

    # Optional additional time shift (seconds)
    gust_phase_s: float = 0.0


def _stable_seed_int(site_id: str) -> int:
    # Never use Python's built-in hash(); it's salted per process.
    digest = hashlib.sha256(site_id.encode("utf-8")).digest()
    # Take 32 bits for a stable int seed.
    return int.from_bytes(digest[:4], "big", signed=False)


WIND_SITES: Dict[str, WindSiteParams] = {
    # Field: mild baseline winds + moderate gusts
    "field": WindSiteParams(
        base_speed_ms=2.0,
        gust_amplitude_ms=1.5,
        gust_period_s=90.0,
        gust_shape="sinusoidal",
        gust_phase_s=0.0,
    ),
    # Mountain Ridge: stronger baseline winds + larger, slightly noisier gusts
    "mountain": WindSiteParams(
        base_speed_ms=4.0,
        gust_amplitude_ms=2.2,
        gust_period_s=75.0,
        gust_shape="noise",
        gust_phase_s=12.0,
    ),
    # Urban Rooftop: warm microclimate => fast gust cycle
    "rooftop": WindSiteParams(
        base_speed_ms=3.0,
        gust_amplitude_ms=1.9,
        gust_period_s=60.0,
        gust_shape="sinusoidal",
        gust_phase_s=6.0,
    ),
}


def _standard_wind_speed(alt_m: float, time_s: float) -> float:
    """Base wind speed from the original layered diurnal model."""

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


def _altitude_gust_scale(alt_m: float) -> float:
    """Lightly scale gust strength with altitude.

    This keeps gusts perceptible without destabilizing the sim.
    """

    # 0..1 range-ish
    return 1.0 + 0.1 * math.log10(1.0 + max(0.0, alt_m) / 5000.0)


def _gust_offset_speed(t_s: float, site_id: str, alt_m: float) -> float:
    """Deterministic gust offset (added to base wind speed)."""

    if site_id not in WIND_SITES:
        raise KeyError(f"Unknown wind site_id: {site_id}")

    cfg = WIND_SITES[site_id]

    # Seed-derived phase offsets to keep "noise" deterministic per site.
    seed = _stable_seed_int(site_id)
    phase1 = (seed % 3600) / 3600.0 * 2.0 * math.pi
    phase2 = ((seed // 3600) % 3600) / 3600.0 * 2.0 * math.pi

    # Guard against pathological configs.
    period = max(1e-6, cfg.gust_period_s)
    tau = 2.0 * math.pi * (t_s + cfg.gust_phase_s) / period

    if cfg.gust_shape == "sinusoidal":
        # Bounded in [-amp, +amp]
        wave = math.sin(tau)
    elif cfg.gust_shape == "noise":
        # Deterministic bounded pseudo-noise using a sum of incommensurate sines.
        # Each sine is bounded; the weighted sum is then normalized.
        w1 = math.sin(tau + phase1)
        w2 = 0.7 * math.sin(tau * 1.73 + phase2)
        w3 = 0.4 * math.sin(tau * 0.41 + phase1 * 0.37)
        wave = (w1 + w2 + w3) / (1.0 + 0.7 + 0.4)
    else:
        raise ValueError(f"Unknown gust_shape: {cfg.gust_shape}")

    return cfg.gust_amplitude_ms * wave * _altitude_gust_scale(alt_m)


def getWindVelocity(t_s: float, site_id: str = DEFAULT_SITE_ID, alt_m: float = 0.0) -> Tuple[float, float]:
    """Clean wind API.

    Args:
        t_s: Simulation time in seconds
        site_id: Wind site identifier
        alt_m: Altitude in meters

    Returns:
        (vx_mps, vy_mps): wind velocity components (East, North)
    """

    return wind_vector(alt_m, time_s=t_s, site_id=site_id)


def wind_speed(alt_m: float, time_s: float = 0.0, site_id: str = DEFAULT_SITE_ID) -> float:
    """Return wind speed at altitude (m/s).

    Wind speed is the base layered diurnal model scaled to the site baseline,
    plus a site-specific deterministic gust offset.
    """

    if site_id not in WIND_SITES:
        raise KeyError(f"Unknown wind site_id: {site_id}")

    cfg = WIND_SITES[site_id]

    # Scale the layered base profile to match the requested site baseline.
    standard_sea_level_base = STANDARD_WIND_LAYERS[0][2]  # troposphere base_speed
    base_scale = cfg.base_speed_ms / standard_sea_level_base

    base_speed = _standard_wind_speed(alt_m, time_s)
    gust_offset = _gust_offset_speed(time_s, site_id, alt_m)
    speed = base_speed * base_scale + gust_offset

    # Stability bounds.
    speed = max(0.0, speed)
    return min(MAX_WIND_SPEED_MPS, speed)


def wind_direction(alt_m: float, time_s: float = 0.0, site_id: str = DEFAULT_SITE_ID) -> float:
    """Return wind direction at altitude (radians).

    Direction is primarily altitude-dependent. Site ID is currently unused but
    accepted for interface completeness.
    """

    for bot, top, _base, direction, _amp in STANDARD_WIND_LAYERS:
        if bot <= alt_m <= top:
            layer_fractions = (alt_m - bot) / (top - bot)
            return direction + 0.2 * math.sin(layer_fractions * math.pi)
    return 1.0


def wind_vector(alt_m: float, time_s: float = 0.0, site_id: str = DEFAULT_SITE_ID) -> Tuple[float, float]:
    """Return wind velocity as (u, v) in m/s (East, North components)."""

    speed = wind_speed(alt_m, time_s=time_s, site_id=site_id)
    direction = wind_direction(alt_m, time_s=time_s, site_id=site_id)
    u = speed * math.cos(direction)
    v = speed * math.sin(direction)
    return (u, v)


def wind_profile(altitudes: list, time_s: float = 0.0, site_id: str = DEFAULT_SITE_ID):
    """Compute wind speeds across a list of altitudes."""

    return [
        (alt, wind_speed(alt, time_s=time_s, site_id=site_id), wind_direction(alt, time_s=time_s, site_id=site_id))
        for alt in altitudes
    ]
