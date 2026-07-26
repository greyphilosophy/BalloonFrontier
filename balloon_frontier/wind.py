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
    (0, 3000, 2.0, 0.5, 1.5),
    (3000, 8000, 5.0, 1.2, 3.0),
    (8000, 15000, 8.0, 1.0, 2.5),
    (15000, 25000, 12.0, 0.8, 4.0),
    (25000, 40000, 6.0, 1.5, 3.0),
]

DEFAULT_SITE_ID = "field"
MAX_WIND_SPEED_MPS = 24.0


@dataclass(frozen=True)
class WindSiteParams:
    """Site-specific wind configuration."""

    base_speed_ms: float
    gust_amplitude_ms: float
    gust_period_s: float
    gust_shape: str = "sinusoidal"
    gust_phase_s: float = 0.0


def _stable_seed_int(site_id: str) -> int:
    digest = hashlib.sha256(site_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big", signed=False)


WIND_SITES: Dict[str, WindSiteParams] = {
    "field": WindSiteParams(
        base_speed_ms=2.0,
        gust_amplitude_ms=1.5,
        gust_period_s=90.0,
        gust_shape="sinusoidal",
        gust_phase_s=0.0,
    ),
    "mountain": WindSiteParams(
        base_speed_ms=4.0,
        gust_amplitude_ms=2.2,
        gust_period_s=75.0,
        gust_shape="noise",
        gust_phase_s=12.0,
    ),
    "rooftop": WindSiteParams(
        base_speed_ms=3.0,
        gust_amplitude_ms=1.9,
        gust_period_s=60.0,
        gust_shape="sinusoidal",
        gust_phase_s=6.0,
    ),
}


def _standard_wind_speed(alt_m: float, time_s: float) -> float:
    speed = 0.0
    for bot, top, base, _direction, amplitude in STANDARD_WIND_LAYERS:
        if bot <= alt_m <= top:
            diurnal_phase = 2.0 * math.pi * time_s / 86400.0
            speed = base + amplitude * math.sin(
                diurnal_phase + 0.5 * alt_m / 10000.0
            )
            break
    else:
        speed = 6.0 + 3.0 * math.sin(0.5 * alt_m / 10000.0)
    return max(0.0, speed)


def _altitude_gust_scale(alt_m: float) -> float:
    return 1.0 + 0.1 * math.log10(1.0 + max(0.0, alt_m) / 5000.0)


def _gust_offset_speed(t_s: float, site_id: str, alt_m: float) -> float:
    if site_id not in WIND_SITES:
        raise KeyError(f"Unknown wind site_id: {site_id}")

    config = WIND_SITES[site_id]
    seed = _stable_seed_int(site_id)
    phase1 = (seed % 3600) / 3600.0 * 2.0 * math.pi
    phase2 = ((seed // 3600) % 3600) / 3600.0 * 2.0 * math.pi
    period = max(1e-6, config.gust_period_s)
    tau = 2.0 * math.pi * (t_s + config.gust_phase_s) / period

    if config.gust_shape == "sinusoidal":
        wave = math.sin(tau)
    elif config.gust_shape == "noise":
        wave1 = math.sin(tau + phase1)
        wave2 = 0.7 * math.sin(tau * 1.73 + phase2)
        wave3 = 0.4 * math.sin(tau * 0.41 + phase1 * 0.37)
        wave = (wave1 + wave2 + wave3) / (1.0 + 0.7 + 0.4)
    else:
        raise ValueError(f"Unknown gust_shape: {config.gust_shape}")

    return config.gust_amplitude_ms * wave * _altitude_gust_scale(alt_m)


def getWindVelocity(
    t_s: float,
    site_id: str = DEFAULT_SITE_ID,
    alt_m: float = 0.0,
) -> Tuple[float, float]:
    """Return wind velocity components (East, North)."""

    return wind_vector(alt_m, time_s=t_s, site_id=site_id)


def wind_speed(
    alt_m: float,
    time_s: float = 0.0,
    site_id: str = DEFAULT_SITE_ID,
) -> float:
    """Return generated wind speed at altitude (m/s)."""

    if site_id not in WIND_SITES:
        raise KeyError(f"Unknown wind site_id: {site_id}")

    config = WIND_SITES[site_id]
    standard_sea_level_base = STANDARD_WIND_LAYERS[0][2]
    base_scale = config.base_speed_ms / standard_sea_level_base
    base_speed = _standard_wind_speed(alt_m, time_s)
    gust_offset = _gust_offset_speed(time_s, site_id, alt_m)
    speed = max(0.0, base_speed * base_scale + gust_offset)
    return min(MAX_WIND_SPEED_MPS, speed)


def wind_direction(
    alt_m: float,
    time_s: float = 0.0,
    site_id: str = DEFAULT_SITE_ID,
) -> float:
    """Return generated wind direction at altitude (radians)."""

    del time_s, site_id
    for bottom, top, _base, direction, _amplitude in STANDARD_WIND_LAYERS:
        if bottom <= alt_m <= top:
            layer_fraction = (alt_m - bottom) / (top - bottom)
            return direction + 0.2 * math.sin(layer_fraction * math.pi)
    return 1.0


def _standard_wind_vector(
    alt_m: float,
    time_s: float = 0.0,
    site_id: str = DEFAULT_SITE_ID,
) -> Tuple[float, float]:
    """Return generated wind without provider dispatch."""

    speed = wind_speed(alt_m, time_s=time_s, site_id=site_id)
    direction = wind_direction(alt_m, time_s=time_s, site_id=site_id)
    return speed * math.cos(direction), speed * math.sin(direction)


def wind_vector(
    alt_m: float,
    time_s: float = 0.0,
    site_id: str = DEFAULT_SITE_ID,
) -> Tuple[float, float]:
    """Return active atmospheric wind as East and North components."""

    from balloon_frontier.atmosphere import current_atmosphere_provider

    provider = current_atmosphere_provider()
    if provider is not None:
        sample = provider.sample(max(0.0, float(alt_m)), time_s=float(time_s))
        return sample.wind_x_mps, sample.wind_y_mps
    return _standard_wind_vector(alt_m, time_s=time_s, site_id=site_id)


def wind_profile(
    altitudes: list,
    time_s: float = 0.0,
    site_id: str = DEFAULT_SITE_ID,
):
    """Compute generated wind speeds across a list of altitudes."""

    return [
        (
            altitude,
            wind_speed(altitude, time_s=time_s, site_id=site_id),
            wind_direction(altitude, time_s=time_s, site_id=site_id),
        )
        for altitude in altitudes
    ]
