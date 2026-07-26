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

    points = _monotonic_ascent_points(telemetry)
    if not points:
        return AtmosphereProfile(
            layers=(),
            weather=weather,
            wind_measurements_available=True,
        )

    start_altitude = max(0.0, float(points[0].altitude_m))
    ceiling = float(points[-1].altitude_m)
    altitudes = _sample_altitudes(start_altitude, ceiling, resolution)
    layers = []
    for altitude in altitudes:
        time_s = _interpolate_attribute(points, altitude, "time_s")
        vehicle_velocity = _interpolate_attribute(points, altitude, "vx_mps")
        sample = atmosphere_provider.sample(altitude, time_s=time_s)
        layers.append(
            AtmosphereLayer(
                altitude_m=round(altitude, 1),
                temperature_k=round(float(sample.temperature_k), 2),
                pressure_pa=round(float(sample.pressure_pa), 1),
                horizontal_velocity_mps=round(vehicle_velocity, 2),
                wind_x_mps=round(float(sample.wind_x_mps), 2),
                wind_y_mps=round(float(sample.wind_y_mps), 2),
            )
        )
    return AtmosphereProfile(
        layers=tuple(layers),
        weather=weather,
        wind_measurements_available=True,
    )


def _monotonic_ascent_points(telemetry: Iterable) -> tuple:
    usable = [point for point in telemetry if not getattr(point, "landed", False)]
    if not usable:
        return ()
    peak_index = max(
        range(len(usable)),
        key=lambda index: float(usable[index].altitude_m),
    )
    ascent = usable[: peak_index + 1]
    monotonic = []
    highest = float("-inf")
    for point in ascent:
        altitude = float(point.altitude_m)
        if altitude > highest:
            monotonic.append(point)
            highest = altitude
    return tuple(monotonic)


def _interpolate_attribute(points: tuple, altitude_m: float, attribute: str) -> float:
    if altitude_m <= float(points[0].altitude_m):
        return float(getattr(points[0], attribute, 0.0))
    for lower, upper in zip(points, points[1:]):
        lower_altitude = float(lower.altitude_m)
        upper_altitude = float(upper.altitude_m)
        if altitude_m <= upper_altitude:
            fraction = (altitude_m - lower_altitude) / (
                upper_altitude - lower_altitude
            )
            lower_value = float(getattr(lower, attribute, 0.0))
            upper_value = float(getattr(upper, attribute, 0.0))
            return lower_value + (upper_value - lower_value) * fraction
    return float(getattr(points[-1], attribute, 0.0))


def _sample_altitudes(
    start_m: float,
    ceiling_m: float,
    resolution_m: float,
) -> tuple[float, ...]:
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
