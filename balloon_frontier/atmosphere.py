"""Atmospheric sampling contracts and per-flight provider context."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Protocol, runtime_checkable

from balloon_frontier.physics import (
    _standard_atmosphere_pressure,
    _standard_atmosphere_temperature,
)
from balloon_frontier.wind import _standard_wind_vector


@dataclass(frozen=True, slots=True)
class AtmosphereSample:
    """Ambient conditions at one altitude and instant.

    Wind components describe the air mass itself, not vehicle velocity. ``x`` is
    east-west and ``y`` is north-south.
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


_ACTIVE_PROVIDER: ContextVar[AtmosphereProvider | None] = ContextVar(
    "balloon_frontier_active_atmosphere_provider",
    default=None,
)


def current_atmosphere_provider() -> AtmosphereProvider | None:
    """Return the provider active in the current flight context."""

    return _ACTIVE_PROVIDER.get()


@contextmanager
def use_atmosphere(provider: AtmosphereProvider | None) -> Iterator[None]:
    """Activate ``provider`` for physics and wind calls in this context.

    ``ContextVar`` keeps simultaneous Discord flights isolated even when their
    simulations run on different tasks or worker threads.
    """

    token = _ACTIVE_PROVIDER.set(provider)
    try:
        yield
    finally:
        _ACTIVE_PROVIDER.reset(token)


@dataclass(frozen=True, slots=True)
class StandardAtmosphereProvider:
    """The existing standard atmosphere and deterministic site wind."""

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
            wind_x, wind_y = _standard_wind_vector(
                altitude,
                time_s=float(time_s),
                site_id=self.site_id,
            )
        return AtmosphereSample(
            altitude_m=altitude,
            temperature_k=(
                _standard_atmosphere_temperature(altitude)
                + float(self.temperature_offset_k)
            ),
            pressure_pa=(
                _standard_atmosphere_pressure(altitude)
                * float(self.pressure_multiplier)
            ),
            wind_x_mps=float(wind_x) * float(self.wind_multiplier),
            wind_y_mps=float(wind_y) * float(self.wind_multiplier),
        )
