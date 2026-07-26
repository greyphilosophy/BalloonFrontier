"""Recorded atmosphere profiles, interpolation, and one-flight locking."""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from balloon_frontier.atmosphere import AtmosphereProvider, AtmosphereSample
from balloon_frontier.weather_event import WeatherEvent


@dataclass(frozen=True, slots=True)
class AtmosphereLayer:
    altitude_m: float
    temperature_k: float
    pressure_pa: float
    horizontal_velocity_mps: float = 0.0
    wind_x_mps: float = 0.0
    wind_y_mps: float = 0.0


@dataclass(frozen=True, slots=True)
class AtmosphereProfile:
    layers: tuple[AtmosphereLayer, ...]
    weather: WeatherEvent

    def __post_init__(self) -> None:
        if any(
            current.altitude_m >= following.altitude_m
            for current, following in zip(self.layers, self.layers[1:])
        ):
            raise ValueError("atmosphere profile layers must be strictly ascending")

    def to_dict(self) -> dict:
        return {
            "layers": [asdict(layer) for layer in self.layers],
            "weather": asdict(self.weather),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AtmosphereProfile":
        layers = []
        for stored_item in data.get("layers", ()):
            item = dict(stored_item)
            # PR 46 briefly stored vehicle horizontal velocity under wind_x_mps.
            # Preserve that value as vehicle motion rather than converting it into
            # ambient wind, which would corrupt replayed atmospheric conditions.
            if "horizontal_velocity_mps" not in item and "wind_x_mps" in item:
                item["horizontal_velocity_mps"] = item.pop("wind_x_mps")
            item.setdefault("horizontal_velocity_mps", 0.0)
            item.setdefault("wind_x_mps", 0.0)
            item.setdefault("wind_y_mps", 0.0)
            layers.append(AtmosphereLayer(**item))
        layers.sort(key=lambda layer: layer.altitude_m)
        return cls(
            layers=tuple(layers),
            weather=WeatherEvent(**data["weather"]),
        )


@dataclass(frozen=True, slots=True)
class RecordedAtmosphereProvider:
    """Interpolate a saved vertical sounding through ``AtmosphereProvider``."""

    profile: AtmosphereProfile
    _altitudes: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.profile.layers:
            raise ValueError("recorded atmosphere requires at least one layer")
        object.__setattr__(
            self,
            "_altitudes",
            tuple(layer.altitude_m for layer in self.profile.layers),
        )

    def sample(self, altitude_m: float, *, time_s: float = 0.0) -> AtmosphereSample:
        del time_s  # A sounding is currently a static vertical profile.
        altitude = max(0.0, float(altitude_m))
        layers = self.profile.layers
        if altitude <= layers[0].altitude_m:
            return _sample_from_layer(altitude, layers[0])
        if altitude >= layers[-1].altitude_m:
            return _sample_from_layer(altitude, layers[-1])

        upper_index = bisect_right(self._altitudes, altitude)
        lower = layers[upper_index - 1]
        upper = layers[upper_index]
        fraction = (altitude - lower.altitude_m) / (
            upper.altitude_m - lower.altitude_m
        )
        return AtmosphereSample(
            altitude_m=altitude,
            temperature_k=_interpolate(lower.temperature_k, upper.temperature_k, fraction),
            pressure_pa=_interpolate(lower.pressure_pa, upper.pressure_pa, fraction),
            wind_x_mps=_interpolate(lower.wind_x_mps, upper.wind_x_mps, fraction),
            wind_y_mps=_interpolate(lower.wind_y_mps, upper.wind_y_mps, fraction),
        )


def _interpolate(lower: float, upper: float, fraction: float) -> float:
    return float(lower) + (float(upper) - float(lower)) * float(fraction)


def _sample_from_layer(altitude_m: float, layer: AtmosphereLayer) -> AtmosphereSample:
    return AtmosphereSample(
        altitude_m=altitude_m,
        temperature_k=layer.temperature_k,
        pressure_pa=layer.pressure_pa,
        wind_x_mps=layer.wind_x_mps,
        wind_y_mps=layer.wind_y_mps,
    )


def profile_from_telemetry(
    telemetry: Iterable,
    weather: WeatherEvent,
    atmosphere_provider: AtmosphereProvider | None = None,
) -> AtmosphereProfile:
    """Sample ascent telemetry into approximately 2 km altitude layers.

    When a provider is supplied, temperature, pressure, and wind come from that
    atmospheric field while vehicle velocity remains a separate diagnostic. This
    prevents balloon motion from being mistaken for wind and produces a profile
    that can be replayed through the same provider contract.
    """

    points = sorted(
        (point for point in telemetry if not getattr(point, "landed", False)),
        key=lambda point: point.altitude_m,
    )
    layers: list[AtmosphereLayer] = []
    next_altitude = 0.0
    for point in points:
        if point.altitude_m < next_altitude:
            continue
        if atmosphere_provider is not None:
            sample = atmosphere_provider.sample(
                point.altitude_m,
                time_s=float(getattr(point, "time_s", 0.0)),
            )
            temperature_k = sample.temperature_k
            pressure_pa = sample.pressure_pa
            wind_x_mps = sample.wind_x_mps
            wind_y_mps = sample.wind_y_mps
        else:
            temperature_k = point.ambient_temperature_k
            pressure_pa = point.ambient_pressure_pa
            wind_x_mps = getattr(point, "ambient_wind_x_mps", 0.0)
            wind_y_mps = getattr(point, "ambient_wind_y_mps", 0.0)
        layers.append(AtmosphereLayer(
            altitude_m=round(float(point.altitude_m), 1),
            temperature_k=round(float(temperature_k), 2),
            pressure_pa=round(float(pressure_pa), 1),
            horizontal_velocity_mps=round(float(point.vx_mps), 2),
            wind_x_mps=round(float(wind_x_mps), 2),
            wind_y_mps=round(float(wind_y_mps), 2),
        ))
        next_altitude = point.altitude_m + 2000.0
    return AtmosphereProfile(tuple(layers), weather)


class AtmosphereProfileRepository:
    """JSON-backed per-player profile storage with a one-flight lock flag."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (Path.home() / ".balloon_frontier" / "atmospheres")

    def _path(self, player_id: str) -> Path:
        safe_id = str(player_id).replace("/", "_").replace("\\", "_")
        return self.directory / f"{safe_id}.json"

    def save(self, player_id: str, profile: AtmosphereProfile) -> None:
        path = self._path(player_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"profile": profile.to_dict(), "locked": False}))

    def get(self, player_id: str) -> AtmosphereProfile | None:
        path = self._path(player_id)
        if not path.exists():
            return None
        return AtmosphereProfile.from_dict(json.loads(path.read_text())["profile"])

    def lock_for_next_flight(self, player_id: str) -> bool:
        path = self._path(player_id)
        if not path.exists():
            return False
        data = json.loads(path.read_text())
        data["locked"] = True
        path.write_text(json.dumps(data))
        return True

    def get_locked_profile(self, player_id: str) -> AtmosphereProfile | None:
        """Return the locked profile without consuming it."""

        path = self._path(player_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        if not data.get("locked"):
            return None
        return AtmosphereProfile.from_dict(data["profile"])

    def get_locked_weather(self, player_id: str) -> WeatherEvent | None:
        profile = self.get_locked_profile(player_id)
        return profile.weather if profile is not None else None

    def consume_locked_profile(self, player_id: str) -> AtmosphereProfile | None:
        """Clear and return the locked profile after a successful flight."""

        path = self._path(player_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        if not data.get("locked"):
            return None
        data["locked"] = False
        path.write_text(json.dumps(data))
        return AtmosphereProfile.from_dict(data["profile"])

    def consume_locked_weather(self, player_id: str) -> WeatherEvent | None:
        profile = self.consume_locked_profile(player_id)
        return profile.weather if profile is not None else None


atmosphere_profiles = AtmosphereProfileRepository()
