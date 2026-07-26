"""Trajectory prediction from a static recorded atmosphere profile."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from balloon_frontier.atmosphere_profile import AtmosphereProfile, RecordedAtmosphereProvider


@dataclass(frozen=True, slots=True)
class LandingPrediction:
    east_m: float
    north_m: float
    flight_time_s: float
    target_altitude_m: float

    @property
    def distance_m(self) -> float:
        return hypot(self.east_m, self.north_m)


def predict_landing_offset(
    profile: AtmosphereProfile,
    *,
    target_altitude_m: float,
    ascent_rate_mps: float = 5.0,
    descent_rate_mps: float = 7.0,
    altitude_step_m: float = 250.0,
) -> LandingPrediction:
    """Integrate horizontal drift through ascent and descent.

    The first navigation model assumes constant vertical rates and a static vertical
    sounding. It deliberately excludes launch-site coordinates and terrain so the
    result is reusable by Discord, CLI, missions, and future map adapters.
    """

    if not profile.wind_measurements_available:
        raise ValueError("landing prediction requires measured wind vectors")

    target = float(target_altitude_m)
    ascent_rate = float(ascent_rate_mps)
    descent_rate = float(descent_rate_mps)
    step = float(altitude_step_m)
    if target <= 0.0:
        raise ValueError("target_altitude_m must be positive")
    if ascent_rate <= 0.0 or descent_rate <= 0.0:
        raise ValueError("vertical rates must be positive")
    if step <= 0.0:
        raise ValueError("altitude_step_m must be positive")

    provider = RecordedAtmosphereProvider(profile)
    east_m = 0.0
    north_m = 0.0
    elapsed_s = 0.0

    altitude = 0.0
    while altitude < target:
        next_altitude = min(target, altitude + step)
        midpoint = (altitude + next_altitude) / 2.0
        duration = (next_altitude - altitude) / ascent_rate
        sample = provider.sample(midpoint, time_s=elapsed_s + duration / 2.0)
        east_m += sample.wind_x_mps * duration
        north_m += sample.wind_y_mps * duration
        elapsed_s += duration
        altitude = next_altitude

    altitude = target
    while altitude > 0.0:
        next_altitude = max(0.0, altitude - step)
        midpoint = (altitude + next_altitude) / 2.0
        duration = (altitude - next_altitude) / descent_rate
        sample = provider.sample(midpoint, time_s=elapsed_s + duration / 2.0)
        east_m += sample.wind_x_mps * duration
        north_m += sample.wind_y_mps * duration
        elapsed_s += duration
        altitude = next_altitude

    return LandingPrediction(
        east_m=east_m,
        north_m=north_m,
        flight_time_s=elapsed_s,
        target_altitude_m=target,
    )
