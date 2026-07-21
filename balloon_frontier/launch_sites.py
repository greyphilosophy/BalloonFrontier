"""Launch site definitions.

This repo historically stored launch site data as raw tuples.
This module replaces those tuples with an explicit dataclass so callers
can avoid fragile tuple indexing.

All distances are in meters and temperatures are in Kelvin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from .physics import atmosphere_temperature, atmosphere_pressure, atmosphere_density


@dataclass(frozen=True, slots=True)
class LaunchSiteInfo:
    """Atmospheric launch site configuration.

    Fields:
      - name: UI label
      - altitude_m: launch altitude above sea level (m)
      - gas_temperature_k: absolute gas temperature at launch (K)
        If None, it is derived as:
          atmosphere_temperature(altitude_m) + temperature_offset_k
      - temperature_offset_k: offset applied to the standard atmosphere temperature (K)
      - wind_strength: descriptive wind strength multiplier (currently unused by physics)
      - description: UI text
    """

    name: str
    altitude_m: float
    gas_temperature_k: Optional[float] = None
    temperature_offset_k: float = 0.0
    wind_strength: float = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "altitude_m", float(self.altitude_m))
        if self.gas_temperature_k is not None:
            object.__setattr__(self, "gas_temperature_k", float(self.gas_temperature_k))
        object.__setattr__(self, "temperature_offset_k", float(self.temperature_offset_k))
        object.__setattr__(self, "wind_strength", float(self.wind_strength))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "description", str(self.description))

        if self.gas_temperature_k is not None and self.gas_temperature_k <= 0:
            raise ValueError(
                f"gas_temperature_k must be > 0 K, got {self.gas_temperature_k}"
            )

    def gas_temperature_at_launch(self) -> float:
        if self.gas_temperature_k is not None:
            return float(self.gas_temperature_k)
        return atmosphere_temperature(self.altitude_m) + float(self.temperature_offset_k)

    def derive_conditions(self) -> Dict[str, Any]:
        """Derive ambient conditions used by the simulation/fill functions."""
        launch_altitude = float(self.altitude_m)
        gas_temperature = self.gas_temperature_at_launch()
        launch_pressure = atmosphere_pressure(launch_altitude)
        launch_density_kg_m3 = atmosphere_density(launch_altitude)
        return {
            "launch_altitude": launch_altitude,
            "gas_temperature": gas_temperature,
            "launch_pressure": launch_pressure,
            "launch_density_kg_m3": launch_density_kg_m3,
        }
