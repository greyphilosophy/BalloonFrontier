"""Seeded, vertically coherent atmospheric columns for simulation and soundings."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from balloon_frontier.atmosphere import AtmosphereSample
from balloon_frontier.physics import (
    _standard_atmosphere_pressure,
    _standard_atmosphere_temperature,
)

COLUMN_ALTITUDES_M = (0.0, 1000.0, 3000.0, 6000.0, 9000.0, 12000.0, 16000.0, 22000.0, 30000.0, 40000.0)
SCENARIOS = ("calm", "frontal", "jet_stream", "atmospheric_river")


@dataclass(frozen=True, slots=True)
class WeatherColumnLayer:
    altitude_m: float
    temperature_anomaly_k: float
    pressure_multiplier: float
    wind_x_mps: float
    wind_y_mps: float


@dataclass(frozen=True, slots=True)
class WeatherColumn:
    """A hidden atmospheric truth sampled smoothly between generated layers."""

    seed: int
    scenario: str
    layers: tuple[WeatherColumnLayer, ...]
    _altitudes: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.scenario not in SCENARIOS:
            raise ValueError(f"unknown weather-column scenario: {self.scenario}")
        if not self.layers:
            raise ValueError("weather column requires at least one layer")
        if any(a.altitude_m >= b.altitude_m for a, b in zip(self.layers, self.layers[1:])):
            raise ValueError("weather-column layers must be strictly ascending")
        object.__setattr__(self, "_altitudes", tuple(layer.altitude_m for layer in self.layers))

    @property
    def ceiling_m(self) -> float:
        return self.layers[-1].altitude_m

    def sample(self, altitude_m: float, *, time_s: float = 0.0) -> AtmosphereSample:
        """Return a smooth sample; the column is static during this first iteration."""

        del time_s
        altitude = min(self.ceiling_m, max(0.0, float(altitude_m)))
        lower, upper, fraction = self._bracket(altitude)
        eased = fraction * fraction * (3.0 - 2.0 * fraction)
        anomaly = _mix(lower.temperature_anomaly_k, upper.temperature_anomaly_k, eased)
        pressure_multiplier = _mix(lower.pressure_multiplier, upper.pressure_multiplier, eased)
        wind_x = _mix(lower.wind_x_mps, upper.wind_x_mps, eased)
        wind_y = _mix(lower.wind_y_mps, upper.wind_y_mps, eased)
        return AtmosphereSample(
            altitude_m=altitude,
            temperature_k=_standard_atmosphere_temperature(altitude) + anomaly,
            pressure_pa=_standard_atmosphere_pressure(altitude) * pressure_multiplier,
            wind_x_mps=wind_x,
            wind_y_mps=wind_y,
        )

    def _bracket(self, altitude_m: float) -> tuple[WeatherColumnLayer, WeatherColumnLayer, float]:
        if altitude_m <= self.layers[0].altitude_m:
            return self.layers[0], self.layers[0], 0.0
        for lower, upper in zip(self.layers, self.layers[1:]):
            if altitude_m <= upper.altitude_m:
                fraction = (altitude_m - lower.altitude_m) / (upper.altitude_m - lower.altitude_m)
                return lower, upper, fraction
        return self.layers[-1], self.layers[-1], 0.0


def generate_weather_column(seed: int, scenario: str | None = None) -> WeatherColumn:
    """Generate a deterministic, coherent vertical column from a game seed."""

    rng = random.Random(int(seed))
    selected = scenario or rng.choice(SCENARIOS)
    if selected not in SCENARIOS:
        raise ValueError(f"unknown weather-column scenario: {selected}")

    surface_heading = rng.uniform(0.0, 2.0 * math.pi)
    turn_sign = rng.choice((-1.0, 1.0))
    surface_pressure = rng.uniform(0.985, 1.015)
    layers = []
    for altitude in COLUMN_ALTITUDES_M:
        wind_speed, heading = _scenario_wind(
            selected,
            altitude,
            surface_heading,
            turn_sign,
            rng,
        )
        anomaly = _temperature_anomaly(selected, altitude, rng)
        pressure_multiplier = 1.0 + (surface_pressure - 1.0) * math.exp(-altitude / 9000.0)
        layers.append(
            WeatherColumnLayer(
                altitude_m=altitude,
                temperature_anomaly_k=anomaly,
                pressure_multiplier=pressure_multiplier,
                wind_x_mps=wind_speed * math.cos(heading),
                wind_y_mps=wind_speed * math.sin(heading),
            )
        )
    return WeatherColumn(seed=int(seed), scenario=selected, layers=tuple(layers))


def _scenario_wind(
    scenario: str,
    altitude_m: float,
    surface_heading: float,
    turn_sign: float,
    rng: random.Random,
) -> tuple[float, float]:
    km = altitude_m / 1000.0
    noise = rng.uniform(-1.5, 1.5)
    if scenario == "calm":
        speed = 2.0 + 0.25 * km + noise
        turn = 0.35 * math.tanh((km - 8.0) / 5.0)
    elif scenario == "frontal":
        speed = 5.0 + 0.7 * km + 10.0 * math.exp(-((km - 8.0) / 4.0) ** 2) + noise
        turn = 1.1 * math.tanh((km - 4.0) / 2.5)
    elif scenario == "jet_stream":
        speed = 4.0 + 38.0 * math.exp(-((km - 11.0) / 3.0) ** 2) + 0.15 * km + noise
        turn = 0.65 * math.tanh((km - 7.0) / 3.0)
    else:  # atmospheric_river
        speed = 5.0 + 20.0 * math.exp(-((km - 3.0) / 2.4) ** 2) + 0.25 * km + noise
        turn = 0.45 * math.tanh((km - 6.0) / 4.0)
    heading = surface_heading + turn_sign * turn + rng.uniform(-0.10, 0.10)
    return max(0.0, min(65.0, speed)), heading


def _temperature_anomaly(scenario: str, altitude_m: float, rng: random.Random) -> float:
    km = altitude_m / 1000.0
    background = rng.uniform(-0.8, 0.8)
    if scenario == "calm":
        return 2.0 * math.exp(-km / 4.0) + background
    if scenario == "frontal":
        return -5.0 * math.exp(-((km - 2.0) / 2.5) ** 2) + background
    if scenario == "jet_stream":
        return -3.0 * math.exp(-((km - 10.0) / 3.5) ** 2) + background
    return 4.0 * math.exp(-((km - 2.5) / 2.8) ** 2) + background


def _mix(lower: float, upper: float, fraction: float) -> float:
    return lower + (upper - lower) * fraction
