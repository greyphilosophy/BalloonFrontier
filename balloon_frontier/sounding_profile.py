"""High-resolution atmospheric sounding capture from flight telemetry."""

from __future__ import annotations

from typing import Iterable

from balloon_frontier.atmosphere import AtmosphereProvider
from balloon_frontier.atmosphere_profile import AtmosphereLayer, AtmosphereProfile
from balloon_frontier.weather_event import WeatherEvent


def record_sounding_profile(
    telemetry: Iterable,
    weather: WeatherEvent,
    atmosphere_provider: AtmosphereProvider,
    *,
    vertical_resolution_m: float = 500.0,
) -> AtmosphereProfile:
    """Sample the atmosphere at regular altitude intervals reached during ascent."""

    resolution = float(vertical_resolution_m)
    if resolution <= 0.0:
        raise ValueError("vertical_resolution_m must be positive")

    points = sorted(
        (point for point in telemetry if not getattr(point, "landed", False)),
        key=lambda point: float(point.altitude_m),
    )
    if not points:
        return AtmosphereProfile(
            layers=(),
            weather=weather,
            wind_measurements_available=True,
        )

    start_altitude = max(0.0, float(points[0].altitude_m))
    ceiling = max(float(point.altitude_m) for point in points)
    altitudes = _sample_altitudes(start_altitude, ceiling, resolution)
    layers = []
    for altitude in altitudes:
        point = min(
            points,
            key=lambda candidate: abs(float(candidate.altitude_m) - altitude),
        )
        sample = atmosphere_provider.sample(
            altitude,
            time_s=float(getattr(point, "time_s", 0.0)),
        )
        layers.append(
            AtmosphereLayer(
                altitude_m=round(altitude, 1),
                temperature_k=round(float(sample.temperature_k), 2),
                pressure_pa=round(float(sample.pressure_pa), 1),
                horizontal_velocity_mps=round(float(getattr(point, "vx_mps", 0.0)), 2),
                wind_x_mps=round(float(sample.wind_x_mps), 2),
                wind_y_mps=round(float(sample.wind_y_mps), 2),
            )
        )
    return AtmosphereProfile(
        layers=tuple(layers),
        weather=weather,
        wind_measurements_available=True,
    )


def _sample_altitudes(start_m: float, ceiling_m: float, resolution_m: float) -> tuple[float, ...]:
    if ceiling_m <= start_m:
        return (start_m,)
    values = [start_m]
    altitude = start_m + resolution_m
    while altitude < ceiling_m:
        values.append(altitude)
        altitude += resolution_m
    if ceiling_m > values[-1]:
        values.append(ceiling_m)
    return tuple(values)
