"""Atmospheric sampling contracts used by the simulation and recorded profiles.

The simulation currently derives standard temperature and pressure from altitude and
site wind from :mod:`balloon_frontier.wind`.  This module places those values behind
one small interface so future flights can substitute a recorded atmosphere without
teaching the physics engine about profile storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from balloon_frontier.physics import atmosphere_pressure, atmosphere_temperature
from balloon_frontier.wind import wind_vector


@dataclass(frozen=True, slots=True)
class AtmosphereSample:
    """Ambient conditions at one altitude and instant.

    Wind components describe the air mass itself, not vehicle velocity.  ``x`` is
    the simulation's east-west axis; ``y`` is reserved for a future north-south
    position axis and is still recorded so the data contract does not need to
    change when two-dimensional navigation arrives.
    """

    altitude_m: float
    temperature_k: float
    pressure_pa: float
    wind_x_mps: float = 0.0
    wind_y_mps: float = 0.0

    def __post_init__(self) -> None:
        if self.temperature_k <= 0.0:
            raise ValueError("temperature_k must be greater than zero")
        if self.pressure_pa <= 0.0:
            raise ValueError("pressure_pa must be greater than zero")


@runtime_checkable
class AtmosphereProvider(Protocol):
    """Return ambient conditions without depending on a specific data source."""

    def sample(self, altitude_m: float, *, time_s: float = 0.0) -> AtmosphereSample:
        """Return conditions at ``altitude_m`` and ``time_s``."""


@dataclass(frozen=True, slots=True)
class StandardAtmosphereProvider:
    """Current generated atmosphere expressed through ``AtmosphereProvider``.

    ``wind_enabled=False`` preserves the old still-air behavior.  Weather-event
    modifiers remain separate for now and will be composed with this provider by
    the flight service in the recorded-profile replay change.
    """

    site_id: str = "field"
    wind_enabled: bool = True
    wind_multiplier: float = 1.0
    pressure_multiplier: float = 1.0
    temperature_offset_k: float = 0.0

    def sample(self, altitude_m: float, *, time_s: float = 0.0) -> AtmosphereSample:
        altitude = max(0.0, float(altitude_m))
        wind_x = 0.0
        wind_y = 0.0
        if self.wind_enabled:
            wind_x, wind_y = wind_vector(
                altitude,
                time_s=float(time_s),
                site_id=self.site_id,
            )
        return AtmosphereSample(
            altitude_m=altitude,
            temperature_k=(
                atmosphere_temperature(altitude) + float(self.temperature_offset_k)
            ),
            pressure_pa=(
                atmosphere_pressure(altitude) * float(self.pressure_multiplier)
            ),
            wind_x_mps=float(wind_x) * float(self.wind_multiplier),
            wind_y_mps=float(wind_y) * float(self.wind_multiplier),
        )
