"""Finite electrical energy and powered-flight control primitives.

This is the functional core for electrical equipment. It deliberately knows
nothing about Discord, Story missions, or mutable simulation loops: payload IDs
become an immutable power configuration, then pure functions answer questions
about battery energy, motor power, and requested vertical thrust.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Iterable

from balloon_frontier.aerostat import HEAT_SOURCE_PROFILES, horizontal_control_force_N


BATTERY_PACK_CAPACITY_WH = 500.0
QUADCOPTER_MAX_VERTICAL_FORCE_N = 18.0
QUADCOPTER_CRUISE_ALTITUDE_M = 30.0
QUADCOPTER_RETURN_TIME_S = 30.0
QUADCOPTER_MOTOR_W_PER_N = 35.0

CONSTANT_ELECTRICAL_LOAD_W: dict[str, float] = {
    "camera": 5.0,
    "radio": 15.0,
    "weather_sensor": 3.0,
    "flight_computer": 8.0,
    "quadcopter": 6.0,
}

ELECTRICAL_HEATER_INPUT_W: dict[str, float] = {
    "electric_heater": 80.0,
    "heater": 600.0,
}

NON_ELECTRICAL_HEAT_SOURCES = frozenset({"candle_heater"})


@dataclass(frozen=True, slots=True)
class PowerConfiguration:
    """Resolved electrical and powered-flight capabilities for one loadout."""

    battery_capacity_wh: float = 0.0
    constant_load_w: float = 0.0
    electrical_heater_input_w: float = 0.0
    electrical_heater_coupled_w: float = 0.0
    non_electrical_heater_coupled_w: float = 0.0
    max_horizontal_force_N: float = 0.0
    max_vertical_force_N: float = 0.0
    cruise_altitude_m: float = QUADCOPTER_CRUISE_ALTITUDE_M
    return_time_s: float = QUADCOPTER_RETURN_TIME_S

    @property
    def has_battery(self) -> bool:
        return self.battery_capacity_wh > 0.0

    @property
    def has_quadcopter(self) -> bool:
        return self.max_vertical_force_N > 0.0

    @property
    def has_electrical_consumers(self) -> bool:
        return (
            self.constant_load_w > 0.0
            or self.electrical_heater_input_w > 0.0
            or self.has_quadcopter
        )


def power_configuration_for_payloads(payload_ids: Iterable[str]) -> PowerConfiguration:
    """Resolve a loadout into finite-energy sources and consumers."""
    payloads = tuple(pid for pid in payload_ids if pid != "none")
    battery_count = sum(1 for pid in payloads if pid == "battery")
    has_quadcopter = "quadcopter" in payloads

    electrical_heater_ids = tuple(
        pid for pid in payloads if pid in ELECTRICAL_HEATER_INPUT_W
    )
    non_electrical_heater_ids = tuple(
        pid for pid in payloads if pid in NON_ELECTRICAL_HEAT_SOURCES
    )

    return PowerConfiguration(
        battery_capacity_wh=BATTERY_PACK_CAPACITY_WH * battery_count,
        constant_load_w=sum(CONSTANT_ELECTRICAL_LOAD_W.get(pid, 0.0) for pid in payloads),
        electrical_heater_input_w=sum(
            ELECTRICAL_HEATER_INPUT_W[pid] for pid in electrical_heater_ids
        ),
        electrical_heater_coupled_w=sum(
            HEAT_SOURCE_PROFILES[pid].coupled_power_watts
            for pid in electrical_heater_ids
            if pid in HEAT_SOURCE_PROFILES
        ),
        non_electrical_heater_coupled_w=sum(
            HEAT_SOURCE_PROFILES[pid].coupled_power_watts
            for pid in non_electrical_heater_ids
            if pid in HEAT_SOURCE_PROFILES
        ),
        max_horizontal_force_N=(
            horizontal_control_force_N(payloads) if has_quadcopter else 0.0
        ),
        max_vertical_force_N=(
            QUADCOPTER_MAX_VERTICAL_FORCE_N if has_quadcopter else 0.0
        ),
    )


def motor_power_w(vertical_force_N: float, horizontal_force_N: float) -> float:
    """Approximate propulsive electrical draw from resultant commanded thrust."""
    resultant_force_N = hypot(
        max(0.0, float(vertical_force_N)),
        float(horizontal_force_N),
    )
    return QUADCOPTER_MOTOR_W_PER_N * resultant_force_N


def battery_energy_after_step(
    remaining_wh: float,
    electrical_power_w: float,
    dt_s: float,
) -> float:
    """Return remaining battery energy after one simulation interval."""
    consumed_wh = max(0.0, float(electrical_power_w)) * max(0.0, float(dt_s)) / 3600.0
    return max(0.0, float(remaining_wh) - consumed_wh)


def battery_fraction(remaining_wh: float, capacity_wh: float) -> float:
    """Return a clamped 0..1 state of charge."""
    capacity = max(0.0, float(capacity_wh))
    if capacity <= 0.0:
        return 0.0
    return min(1.0, max(0.0, float(remaining_wh)) / capacity)


def powered_flight_target_altitude_m(
    *,
    time_s: float,
    ground_altitude_m: float,
    config: PowerConfiguration,
) -> float:
    """Return the generic autonomous sortie target: climb/hold, then return."""
    if float(time_s) >= config.return_time_s:
        return float(ground_altitude_m)
    return float(ground_altitude_m) + config.cruise_altitude_m


def vertical_control_force_N(
    *,
    altitude_m: float,
    velocity_mps: float,
    target_altitude_m: float,
    passive_net_force_N: float,
    total_mass_kg: float,
    max_vertical_force_N: float,
) -> float:
    """Return bounded upward thrust for a simple altitude-hold controller.

    The controller can add upward force but cannot create negative thrust. That
    asymmetry is intentional: an over-buoyant aircraft cannot command descent by
    merely reducing quadcopter thrust to zero.
    """
    mass = max(0.0, float(total_mass_kg))
    authority = max(0.0, float(max_vertical_force_N))
    if mass <= 0.0 or authority <= 0.0:
        return 0.0

    altitude_error_m = float(target_altitude_m) - float(altitude_m)
    desired_accel_mps2 = 0.25 * altitude_error_m - 0.9 * float(velocity_mps)
    desired_accel_mps2 = max(-2.0, min(2.0, desired_accel_mps2))
    required_force_N = mass * desired_accel_mps2 - float(passive_net_force_N)
    return max(0.0, min(authority, required_force_N))
