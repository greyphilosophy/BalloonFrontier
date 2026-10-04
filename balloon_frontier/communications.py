"""Inspectable radio footprints and timestamp-based relay service scoring.

This is a geometric coverage model, not an LTE capacity or propagation model.
The repeater's range, elevation mask, and electrical load are gameplay design
assumptions, not specifications for SceyeCELL. Ground targets share the launch
site's elevation; horizontal drift is the simulator's existing one-dimensional
ground track. Refraction, terrain obstruction, interference, and backhaul are
not yet modeled.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, asin, cos, isfinite, radians, sqrt
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from balloon_frontier.launch_result import TelemetryPoint


EARTH_RADIUS_M = 6_371_000.0
RADIO_MAX_SLANT_RANGE_M = 100_000.0
RADIO_MIN_ELEVATION_DEG = 10.0
RADIO_POWER_W = 20.0


def radio_coverage_radius_m(
    height_agl_m: float,
    *,
    max_slant_range_m: float = RADIO_MAX_SLANT_RANGE_M,
    min_elevation_deg: float = RADIO_MIN_ELEVATION_DEG,
) -> float:
    """Surface radius limited by both elevation angle and slant range.

For Earth radius R and height h, the elevation-limited central angle is
acos(R*cos(e)/(R+h)) - e. The range-limited angle follows the cosine rule,
written in half-angle form to avoid subtracting nearly equal cosines.
Above the radio's range even a receiver directly below is unreachable.
"""
    if not all(isfinite(v) for v in (
        height_agl_m, max_slant_range_m, min_elevation_deg,
    )):
        raise ValueError("Radio geometry requires finite values")
    if max_slant_range_m <= 0.0 or not 0.0 <= min_elevation_deg < 90.0:
        raise ValueError("Radio range must be positive and elevation in [0, 90)")
    if height_agl_m <= 0.0 or height_agl_m >= max_slant_range_m:
        return 0.0

    earth = EARTH_RADIUS_M
    platform_radius = earth + height_agl_m
    elevation = radians(min_elevation_deg)
    elevation_angle = acos(earth * cos(elevation) / platform_radius) - elevation
    half_chord = sqrt(
        (max_slant_range_m**2 - height_agl_m**2)
        / (4.0 * earth * platform_radius)
    )
    range_angle = 2.0 * asin(min(1.0, half_chord))
    return earth * max(0.0, min(elevation_angle, range_angle))


@dataclass(frozen=True, slots=True)
class RelayService:
    connected_s: float = 0.0
    longest_connection_s: float = 0.0
    interruptions: tuple[str, ...] = ()


def relay_service(
    telemetry: Sequence[TelemetryPoint],
    *,
    target_x_m: float = 0.0,
    target_radius_m: float = 0.0,
    minimum_altitude_m: float = 0.0,
) -> RelayService:
    """Measure intervals with the entire target inside a powered footprint.

Both interval endpoints must qualify. No credit is inferred before the first
sample, across a recorded outage, or from duplicate/reversed timestamps. This
conservatively loses boundary intervals at the telemetry sampling resolution.
The altitude requirement is ASL, like other mission altitude objectives.
"""
    if not all(isfinite(v) for v in (
        target_x_m, target_radius_m, minimum_altitude_m,
    )) or target_radius_m < 0.0 or minimum_altitude_m < 0.0:
        raise ValueError("Relay target requires finite coordinates and nonnegative limits")

    connected_s = longest_s = continuous_s = 0.0
    previous = None
    previous_connected = False
    interruptions: list[str] = []
    for point in telemetry:
        reason = ""
        if not all(isfinite(v) for v in (
            point.time_s, point.altitude_m, point.x_m, point.radio_coverage_radius_m,
        )):
            return RelayService(interruptions=("invalid telemetry",))
        elif point.burst or point.landed or point.crashed:
            reason = "platform no longer in service"
        elif not point.radio_active:
            reason = "radio unpowered"
        elif point.altitude_m < minimum_altitude_m:
            reason = "below service altitude"
        elif (
            point.radio_coverage_radius_m <= 0.0
            or abs(point.x_m - target_x_m) + target_radius_m
            > point.radio_coverage_radius_m
        ):
            reason = "target outside radio footprint"

        connected = not reason
        if reason and reason not in interruptions:
            interruptions.append(reason)
        if previous is not None:
            elapsed_s = point.time_s - previous.time_s
            if elapsed_s <= 0.0:
                return RelayService(interruptions=("non-increasing timestamps",))
            if connected and previous_connected:
                connected_s += elapsed_s
                continuous_s += elapsed_s
                longest_s = max(longest_s, continuous_s)
            else:
                continuous_s = 0.0
        previous = point
        previous_connected = connected

    return RelayService(connected_s, longest_s, tuple(interruptions))
