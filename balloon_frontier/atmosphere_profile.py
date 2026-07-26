"""Recorded atmosphere profiles and one-flight weather locking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from balloon_frontier.weather_event import WeatherEvent


@dataclass(frozen=True, slots=True)
class AtmosphereLayer:
    altitude_m: float
    temperature_k: float
    pressure_pa: float
    horizontal_velocity_mps: float


@dataclass(frozen=True, slots=True)
class AtmosphereProfile:
    layers: tuple[AtmosphereLayer, ...]
    weather: WeatherEvent

    def to_dict(self) -> dict:
        return {
            "layers": [asdict(layer) for layer in self.layers],
            "weather": asdict(self.weather),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AtmosphereProfile":
        layers = []
        for item in data.get("layers", ()):
            item = dict(item)
            if "horizontal_velocity_mps" not in item and "wind_x_mps" in item:
                item["horizontal_velocity_mps"] = item.pop("wind_x_mps")
            layers.append(AtmosphereLayer(**item))
        return cls(
            layers=tuple(layers),
            weather=WeatherEvent(**data["weather"]),
        )


def profile_from_telemetry(telemetry: Iterable, weather: WeatherEvent) -> AtmosphereProfile:
    """Sample ascent telemetry into approximately 2 km altitude layers."""

    points = sorted(
        (point for point in telemetry if not getattr(point, "landed", False)),
        key=lambda point: point.altitude_m,
    )
    layers: list[AtmosphereLayer] = []
    next_altitude = 0.0
    for point in points:
        if point.altitude_m < next_altitude:
            continue
        layers.append(AtmosphereLayer(
            altitude_m=round(float(point.altitude_m), 1),
            temperature_k=round(float(point.ambient_temperature_k), 2),
            pressure_pa=round(float(point.ambient_pressure_pa), 1),
            horizontal_velocity_mps=round(float(point.vx_mps), 2),
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

    def get_locked_weather(self, player_id: str) -> WeatherEvent | None:
        """Return locked weather without consuming the one-flight lock."""

        path = self._path(player_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        if not data.get("locked"):
            return None
        return AtmosphereProfile.from_dict(data["profile"]).weather

    def consume_locked_weather(self, player_id: str) -> WeatherEvent | None:
        """Clear and return locked weather after a successful flight."""

        path = self._path(player_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        if not data.get("locked"):
            return None
        data["locked"] = False
        path.write_text(json.dumps(data))
        return AtmosphereProfile.from_dict(data["profile"]).weather


atmosphere_profiles = AtmosphereProfileRepository()
