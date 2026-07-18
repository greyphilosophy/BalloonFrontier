"""Balloon Frontier — Payload Definitions

Defines payloads players can equip on their balloons. Each payload has a
mass (kg), a cost (game coins), and a description.

Some payloads like the pressure-release valve interact directly with
the simulation's venting logic.
"""

from dataclasses import dataclass, field
from typing import List

@dataclass
class Payload:
    """A single payload item."""
    id: str
    name: str
    mass_kg: float
    cost: int = 0
    description: str = ""
    tag: str = ""  # e.g. "vent", "sensor", "recovery"

class Payloads:
    """Registry of all available payloads."""
    _payloads: dict = {}

    @classmethod
    def get(cls, payload_id: str) -> Payload:
        return cls._payloads[payload_id]

    @classmethod
    def list_all(cls) -> List[Payload]:
        return list(cls._payloads.values())

    @classmethod
    def register(cls, p: Payload):
        cls._payloads[p.id] = p

    @classmethod
    def clear(cls):
        cls._payloads.clear()

# ── Register all payloads ───────────────────────────────────────

PAYLOAD_DEFINITIONS = [
    # Sensors
    Payload("camera", "Camera", 1.5, 500, "Still camera for horizon photos", tag="sensor"),
    Payload("radio", "Radio Repeater", 2.0, 800, "Transmit telemetry data back to base", tag="sensor"),
    Payload("weather_sensor", "Weather Sensor", 0.8, 1200, "Temperature, pressure, humidity", tag="sensor"),
    Payload("barometer", "Barometer", 0.5, 300, "Measures ambient pressure", tag="sensor"),
    Payload("thermometer", "Thermometer", 0.3, 200, "Tracks ambient temperature", tag="sensor"),

    # Power & Heating
    Payload("battery", "Battery Pack", 3.0, 1000, "Stores electrical power", tag="power"),
    Payload("heater", "Heater", 2.5, 750, "Warm the gas to boost lift", tag="heater"),
    Payload("solar_panel", "Solar Panel", 1.0, 600, "Converts sunlight to power", tag="power"),
    Payload("flight_computer", "Flight Computer", 1.2, 2000, "Tracks altitude, temp, velocity", tag="sensor"),

    # Recovery
    Payload("parachute", "Parachute", 2.0, 600, "Slows descent on landing", tag="recovery"),
    Payload("parafoil", "Parafoil", 3.5, 1200, "Gliding parachute for horizontal control", tag="recovery"),
    Payload("gps_receiver", "GPS Receiver", 0.7, 900, "Tracks horizontal position", tag="sensor"),

    # Ballast & Control
    Payload("ballast", "Ballast (Sand)", 15.0, 300, "Adjustable weight for fine control", tag="ballast"),
    Payload("pressure_valve", "Pressure Release Valve", 0.5, 400, "Vents excess gas to prevent burst — but costs lift", tag="vent"),
    Payload("propeller_pod", "Propeller Pod", 4.0, 1500, "Small motor-driven propeller for horizontal drift control", tag="control"),

    # Misc
    Payload("none", "None", 1.0, 100, "Default light payload", tag="misc"),
]

# Auto-register
Payloads.clear()
for defn in PAYLOAD_DEFINITIONS:
    Payloads.register(defn)
