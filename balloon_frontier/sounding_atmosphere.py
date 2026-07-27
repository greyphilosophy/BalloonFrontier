"""Source-neutral atmospheric soundings and interpolation providers."""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from balloon_frontier.atmosphere import AtmosphereSample


@dataclass(frozen=True, slots=True)
class SoundingLevel:
    """One measured level in a vertical atmospheric sounding."""

    altitude_m: float
    temperature_k: float
    pressure_pa: float
    wind_x_mps: float = 0.0
    wind_y_mps: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.altitude_m,
            self.temperature_k,
            self.pressure_pa,
            self.wind_x_mps,
            self.wind_y_mps,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("sounding level values must be finite")
        if self.altitude_m < 0.0:
            raise ValueError("altitude_m must be non-negative")
        if self.temperature_k <= 0.0:
            raise ValueError("temperature_k must be greater than zero")
        if self.pressure_pa <= 0.0:
            raise ValueError("pressure_pa must be greater than zero")


@dataclass(frozen=True, slots=True)
class AtmosphericSounding:
    """A static vertical observation from any external or simulated source."""

    levels: tuple[SoundingLevel, ...]
    source: str = "unknown"
    station_id: str | None = None
    observed_at: datetime | None = None
    latitude_deg: float | None = None
    longitude_deg: float | None = None

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError("atmospheric sounding requires at least one level")
        if any(
            lower.altitude_m >= upper.altitude_m
            for lower, upper in zip(self.levels, self.levels[1:])
        ):
            raise ValueError("sounding levels must be strictly ascending")
        if self.observed_at is not None and self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include timezone information")
        if (self.latitude_deg is None) != (self.longitude_deg is None):
            raise ValueError("latitude_deg and longitude_deg must be supplied together")
        if self.latitude_deg is not None:
            latitude = float(self.latitude_deg)
            longitude = float(self.longitude_deg)
            if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
                raise ValueError("latitude_deg must be finite and between -90 and 90")
            if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
                raise ValueError("longitude_deg must be finite and between -180 and 180")

    @classmethod
    def from_levels(
        cls,
        levels: Iterable[SoundingLevel],
        **metadata,
    ) -> "AtmosphericSounding":
        """Build a sounding from levels while normalizing their order."""

        ordered = tuple(sorted(levels, key=lambda level: level.altitude_m))
        return cls(levels=ordered, **metadata)

    @property
    def floor_m(self) -> float:
        return self.levels[0].altitude_m

    @property
    def ceiling_m(self) -> float:
        return self.levels[-1].altitude_m


@dataclass(frozen=True, slots=True)
class SoundingAtmosphereProvider:
    """Interpolate a static sounding through the AtmosphereProvider contract.

    Values below the first measured level use that level, which supports launch
    sites whose station elevation is above zero. Values above the measured ceiling
    are rejected so imported data never appears more complete than it is.
    """

    sounding: AtmosphericSounding
    _altitudes: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_altitudes",
            tuple(level.altitude_m for level in self.sounding.levels),
        )

    def sample(self, altitude_m: float, *, time_s: float = 0.0) -> AtmosphereSample:
        del time_s  # A sounding is a static observation at one valid time.
        altitude = float(altitude_m)
        if not math.isfinite(altitude):
            raise ValueError("altitude_m must be finite")
        altitude = max(0.0, altitude)
        levels = self.sounding.levels

        if altitude > self.sounding.ceiling_m:
            raise ValueError(
                "altitude_m exceeds the highest measured sounding level "
                f"({self.sounding.ceiling_m:g} m)"
            )
        if altitude <= self.sounding.floor_m:
            return _sample_from_level(altitude, levels[0])

        upper_index = bisect_right(self._altitudes, altitude)
        lower = levels[upper_index - 1]
        if upper_index >= len(levels):
            return _sample_from_level(altitude, lower)
        upper = levels[upper_index]
        fraction = (altitude - lower.altitude_m) / (
            upper.altitude_m - lower.altitude_m
        )
        return AtmosphereSample(
            altitude_m=altitude,
            temperature_k=_linear(lower.temperature_k, upper.temperature_k, fraction),
            pressure_pa=_log_linear(lower.pressure_pa, upper.pressure_pa, fraction),
            wind_x_mps=_linear(lower.wind_x_mps, upper.wind_x_mps, fraction),
            wind_y_mps=_linear(lower.wind_y_mps, upper.wind_y_mps, fraction),
        )


def _linear(lower: float, upper: float, fraction: float) -> float:
    return float(lower) + (float(upper) - float(lower)) * float(fraction)


def _log_linear(lower: float, upper: float, fraction: float) -> float:
    return math.exp(_linear(math.log(lower), math.log(upper), fraction))


def _sample_from_level(altitude_m: float, level: SoundingLevel) -> AtmosphereSample:
    return AtmosphereSample(
        altitude_m=altitude_m,
        temperature_k=level.temperature_k,
        pressure_pa=level.pressure_pa,
        wind_x_mps=level.wind_x_mps,
        wind_y_mps=level.wind_y_mps,
    )
