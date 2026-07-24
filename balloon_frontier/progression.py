"""Balloon Frontier - Progression System

Implements budget management, equipment unlocks, and player progression.
Players earn budget from successful missions, unlock envelopes/payloads/sites,
and accumulate reputation from consistent flights.

Unlock conditions use OR logic — meeting EITHER the credit threshold
OR the reputation threshold is sufficient.

Reference: GDD Sections 20, 21.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class EnvelopeUnlock:
    """Defines when and how an envelope type unlocks."""
    id: str
    name: str
    cost: int                     # Budget needed to unlock
    min_reputation: int           # Reputation needed to unlock
    max_volume_m3: float
    burst_stretch_ratio: float
    contained_gas: bool
    mass_kg: float
    description: str = ""


@dataclass
class PayloadUnlock:
    """Defines an unlockable payload."""
    id: str
    name: str
    cost: int                     # Budget needed to unlock
    min_reputation: int           # Reputation needed to unlock
    mass_kg: float
    tag: str                      # sensor, power, recovery, control, ballast, heater
    description: str = ""


@dataclass
class SiteUnlock:
    """Defines an unlockable launch site."""
    id: str
    name: str
    cost: int                     # Budget needed to unlock
    min_reputation: int           # Reputation needed to unlock
    altitude_m: float
    description: str = ""
    temperature_offset_k: float = 0.0
    wind_strength: float = 0.0


# ── Envelope progression tree ────────────────────────────────────────
# GDD §20: unlock at 1000 credits OR 5 rep (Mylar), 3000 OR 10 (Zero-P),
#          5000 OR 20 (Blimp). Latex always available.

ENVELOPES: List[EnvelopeUnlock] = [
    EnvelopeUnlock(
        id="latex", name="Latex Party Balloon",
        cost=0, min_reputation=0,
        max_volume_m3=10.0, burst_stretch_ratio=3.0,
        contained_gas=True, mass_kg=0.5,
        description="The classic: light, stretchy, bursts at 3x volume"),
    EnvelopeUnlock(
        id="mylar", name="Mylar Weather Balloon",
        cost=1000, min_reputation=5,
        max_volume_m3=200.0, burst_stretch_ratio=2.5,
        contained_gas=True, mass_kg=2.0,
        description="Durable and gas-tight for longer flights"),
    EnvelopeUnlock(
        id="zero_pressure", name="Zero-Pressure Polyethylene",
        cost=3000, min_reputation=10,
        max_volume_m3=300.0, burst_stretch_ratio=2.0,
        contained_gas=False, mass_kg=5.0,
        description="Vents excess gas — survives higher but loses lift"),
    EnvelopeUnlock(
        id="blimp", name="Small Non-Rigid Blimp",
        cost=5000, min_reputation=20,
        max_volume_m3=500.0, burst_stretch_ratio=1.5,
        contained_gas=True, mass_kg=12.0,
        description="Big and sturdy — carries everything"),
]


# ── Payload unlock tiers ──────────────────────────────────────────────
# Basic payloads (camera, radio, weather_sensor, barometer, thermometer,
# battery, solar_panel, parachute, parafoil, gps_receiver, ballast,
# pressure_valve, propeller_pod, none) always available.
# Advanced payloads (heater, flight_computer) need reputation >= 3.

PAYLOAD_UNLOCKS: List[PayloadUnlock] = [
    # Always available
    PayloadUnlock("battery", "Battery Pack", 0, 0, 3.0, "power", "Stores electrical power"),
    PayloadUnlock("parachute", "Parachute", 0, 0, 2.0, "recovery", "Slows descent on landing"),
    PayloadUnlock("parafoil", "Parafoil", 0, 0, 3.5, "recovery", "Gliding parachute for horizontal control"),
    PayloadUnlock("ballast", "Ballast (Sand)", 0, 0, 15.0, "ballast", "Adjustable weight for fine control"),
    PayloadUnlock("pressure_valve", "Pressure Release Valve", 0, 0, 0.5, "vent", "Vents excess gas to prevent burst"),
    PayloadUnlock("propeller_pod", "Propeller Pod", 0, 0, 4.0, "control", "Motor-driven propeller for drift control"),
    PayloadUnlock("gps_receiver", "GPS Receiver", 0, 0, 0.7, "sensor", "Tracks horizontal position"),
    PayloadUnlock("barometer", "Barometer", 0, 0, 0.5, "sensor", "Measures ambient pressure"),
    PayloadUnlock("thermometer", "Thermometer", 0, 0, 0.3, "sensor", "Tracks ambient temperature"),
    PayloadUnlock("camera", "Camera", 0, 0, 1.5, "sensor", "Still camera for horizon photos"),
    PayloadUnlock("radio", "Radio Repeater", 0, 0, 2.0, "sensor", "Transmit telemetry data back to base"),
    PayloadUnlock("weather_sensor", "Weather Sensor", 0, 0, 0.8, "sensor", "Temperature, pressure, humidity"),
    PayloadUnlock("solar_panel", "Solar Panel", 0, 0, 1.0, "power", "Converts sunlight to power"),
    PayloadUnlock("none", "None", 0, 0, 1.0, "misc", "Default light payload"),
    # Advanced — require reputation >= 3
    PayloadUnlock(
        "heater", "Heater", 250, 3, 2.5, "heater",
        "Warm the gas to boost lift — advanced technology"),
    PayloadUnlock(
        "flight_computer", "Flight Computer", 750, 3, 1.2, "sensor",
        "Tracks altitude, temp, velocity — advanced avionics"),
]


# ── Site unlock tiers ─────────────────────────────────────────────────
# Open Field: default
# Rooftop:  reputation >= 3
# Mountain Ridge: reputation >= 8

SITES: List[SiteUnlock] = [
    SiteUnlock(
        id="field", name="Open Field",
        cost=0, min_reputation=0,
        altitude_m=0.0,
        description="Flat terrain, mild crosswind"),
    SiteUnlock(
        id="rooftop", name="Urban Rooftop",
        cost=0, min_reputation=3,
        altitude_m=50.0, temperature_offset_k=3.0, wind_strength=3.0,
        description="Warm microclimate, moderate wind"),
    SiteUnlock(
        id="mountain", name="Mountain Ridge",
        cost=0, min_reputation=8,
        altitude_m=1500.0, temperature_offset_k=-5.0, wind_strength=4.0,
        description="Elevated, colder, stronger wind"),
]


# ── Envelope helpers ──────────────────────────────────────────────────

def get_unlock_path() -> List[str]:
    """Return the unlock order for envelopes."""
    return [e.id for e in ENVELOPES]


def get_envelope(env_id: str) -> EnvelopeUnlock:
    """Get an envelope by ID."""
    for e in ENVELOPES:
        if e.id == env_id:
            return e
    return ENVELOPES[0]


def list_unlocked_envelopes(reputation: int, budget: int) -> List[EnvelopeUnlock]:
    """List envelopes the player has unlocked based on reputation or budget.

    Unlock uses OR logic: meet EITHER the reputation OR the cost threshold.
    Budget gates only apply when cost > 0.
    """
    unlocked = []
    for e in ENVELOPES:
        if e.min_reputation == 0 and e.cost == 0:
            # Always available (latex)
            unlocked.append(e)
        elif reputation >= e.min_reputation or (e.cost > 0 and budget >= e.cost):
            unlocked.append(e)
    return unlocked


def list_locked_envelopes(reputation: int, budget: int) -> List[EnvelopeUnlock]:
    """Return envelopes that are currently locked, sorted by closeness."""
    return [e for e in ENVELOPES if e not in list_unlocked_envelopes(reputation, budget)]


def envelope_needs(reputation: int, budget: int, env: EnvelopeUnlock) -> str:
    """Return a human-readable string describing what's needed to unlock an envelope."""
    rep_ok = reputation >= env.min_reputation
    budget_ok = budget >= env.cost

    if rep_ok and budget_ok:
        return ""  # already unlocked (shouldn't happen)
    if rep_ok:
        return f"{env.cost - budget} more credits"
    if budget_ok:
        return f"{env.min_reputation - reputation} more reputation"
    # Need both — pick whichever is closer proportionally
    rep_pct = reputation / env.min_reputation if env.min_reputation > 0 else 1.0
    budget_pct = budget / env.cost if env.cost > 0 else 1.0
    if rep_pct < budget_pct:
        return f"{env.min_reputation - reputation} more reputation"
    return f"{env.cost - budget} more credits"


# ── Payload helpers ───────────────────────────────────────────────────

def list_unlocked_payloads(reputation: int, budget: int) -> List[PayloadUnlock]:
    """List payloads the player can use based on reputation or budget."""
    unlocked = []
    for p in PAYLOAD_UNLOCKS:
        if reputation >= p.min_reputation or (p.cost > 0 and budget >= p.cost):
            unlocked.append(p)
    return unlocked


def list_locked_payloads(reputation: int, budget: int) -> List[PayloadUnlock]:
    """Return payloads that are currently locked."""
    return [p for p in PAYLOAD_UNLOCKS if p not in list_unlocked_payloads(reputation, budget)]


# ── Site helpers ──────────────────────────────────────────────────────

def list_unlocked_sites(reputation: int, budget: int) -> List[SiteUnlock]:
    """List sites the player can launch from."""
    unlocked = []
    for s in SITES:
        if reputation >= s.min_reputation or (s.cost > 0 and budget >= s.cost):
            unlocked.append(s)
    return unlocked


def list_locked_sites(reputation: int, budget: int) -> List[SiteUnlock]:
    """Return sites that are currently locked."""
    return [s for s in SITES if s not in list_unlocked_sites(reputation, budget)]


# ── Player state ──────────────────────────────────────────────────────

class PlayerState:
    """Tracks a player's progression state."""

    def __init__(self, player_id: str = ""):
        self._player_id = player_id
        self.reputation: int = 0
        self.budget: int = 100
        self.unlocked_envelopes: List[str] = []
        self.unlocked_payloads: List[str] = []
        self.unlocked_sites: List[str] = []
        self.total_flights: int = 0
        self.successful_flights: int = 0
        self.missions_completed: List[str] = []

    @property
    def player_id(self) -> str:
        """Return the player identifier."""
        return self._player_id

    @player_id.setter
    def player_id(self, value: str):
        """Set the player identifier and update save path."""
        self._player_id = value

    def _check_and_apply_unlocks(self) -> List[str]:
        """Check all equipment against thresholds and apply new unlocks.

        Budget gates only apply when cost > 0; if cost == 0 the item is gated
        solely by reputation.  This prevents sites/payloads with cost=0 from
        instantaneously unlocking.

        Returns a list of newly unlocked names.
        """
        new_unlocks: List[str] = []

        # Envelopes
        for e in ENVELOPES:
            if e.id not in self.unlocked_envelopes:
                if self.reputation >= e.min_reputation or (e.cost > 0 and self.budget >= e.cost):
                    self.unlocked_envelopes.append(e.id)
                    new_unlocks.append(e.name)

        # Payloads
        for p in PAYLOAD_UNLOCKS:
            if p.id not in self.unlocked_payloads:
                if self.reputation >= p.min_reputation or (p.cost > 0 and self.budget >= p.cost):
                    self.unlocked_payloads.append(p.id)
                    new_unlocks.append(p.name)

        # Sites
        for s in SITES:
            if s.id not in self.unlocked_sites:
                if self.reputation >= s.min_reputation or (s.cost > 0 and self.budget >= s.cost):
                    self.unlocked_sites.append(s.id)
                    new_unlocks.append(s.name)

        return new_unlocks

    def earn_from_mission(self, mission_id: str, score: float, budget_reward: int = 100) -> dict:
        """Process mission completion and update player state."""
        self.total_flights += 1
        success = score >= 60
        if success:
            self.successful_flights += 1

        # Reputation gain (0-2 per flight)
        rep_gain = min(int(score / 33), 2)
        self.reputation += rep_gain

        # Budget gain
        budget_earned = int(budget_reward * score / 100)
        self.budget += budget_earned

        # Check for new equipment unlocks
        new_unlocks = self._check_and_apply_unlocks()

        # Track completed missions
        if mission_id and mission_id not in self.missions_completed:
            self.missions_completed.append(mission_id)

        return {
            "success": success,
            "reputation_gained": rep_gain,
            "budget_earned": budget_earned,
            "new_unlocks": new_unlocks,
        }

    def is_envelope_unlocked(self, env_id: str) -> bool:
        """Check if a specific envelope is unlocked."""
        if env_id == "latex":
            return True  # always available
        self._check_and_apply_unlocks()
        return env_id in self.unlocked_envelopes

    def is_payload_unlocked(self, payload_id: str) -> bool:
        """Check if a specific payload is unlocked."""
        self._check_and_apply_unlocks()
        return payload_id in self.unlocked_payloads

    def is_site_unlocked(self, site_id: str) -> bool:
        """Check if a specific site is unlocked."""
        self._check_and_apply_unlocks()
        return site_id in self.unlocked_sites

    def status_summary(self) -> str:
        """Return a short summary string for Discord display."""
        lines = [
            f"\u26a1 **{self.player_id}'s Status**",
            f"  Reputation: {self.reputation}",
            f"  Budget: ${self.budget}",
            f"  Flights: {self.total_flights} ({self.successful_flights} successful)",
        ]
        return "\n".join(lines)

    def save(self, path: Optional[str] = None):
        """Save player state to JSON.

        Args:
            path: Optional path. If None, saves to PlayerRegistry._save_dir / {player_id}.json
        """
        if path is None:
            save_path = PlayerRegistry._save_dir / f"{self._player_id}.json"
        else:
            save_path = Path(path).expanduser()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps({
            "reputation": self.reputation,
            "budget": self.budget,
            "unlocked_envelopes": self.unlocked_envelopes,
            "unlocked_payloads": self.unlocked_payloads,
            "unlocked_sites": self.unlocked_sites,
            "total_flights": self.total_flights,
            "successful_flights": self.successful_flights,
            "missions_completed": self.missions_completed,
        }))

    @classmethod
    def load(cls, path_or_player_id: Optional[str] = None, path: Optional[str] = None) -> "PlayerState":
        """Load player state from JSON.

        When path_or_player_id is an existing file path, it is used directly.
        Otherwise it is treated as a player_id and resolved to
        ~/.balloon_frontier/{player_id}.json.
        """
        if path is not None:
            save_path = Path(path).expanduser()
        elif path_or_player_id is not None and Path(path_or_player_id).expanduser().exists():
            save_path = Path(path_or_player_id).expanduser()
        elif path_or_player_id is not None:
            save_path = PlayerRegistry._save_dir / f"{path_or_player_id}.json"
        else:
            return cls()
        if save_path.exists():
            data = json.loads(save_path.read_text())
            p = cls()
            for k, v in data.items():
                setattr(p, k, v)
            return p
        return cls()


class PlayerRegistry:
    """Simple in-memory player registry with per-player file persistence."""
    _players: Dict[str, PlayerState] = {}
    _save_dir = Path.home() / ".balloon_frontier"

    @classmethod
    def get_or_create(cls, player_id: str) -> PlayerState:
        if player_id not in cls._players:
            # Try to load from disk first.
            player_state = PlayerState.load(player_id)
            player_state._player_id = player_id
            cls._players[player_id] = player_state
        return cls._players[player_id]

    @classmethod
    def flush_all(cls) -> int:
        """Save all in-memory player states to disk. Returns count saved."""
        count = 0
        for player_id, state in cls._players.items():
            state.save()
            count += 1
        return count

    @classmethod
    def list_players(cls) -> Dict[str, PlayerState]:
        return dict(cls._players)

    @classmethod
    def leaderboard(cls, key: str = "reputation") -> List[PlayerState]:
        """Get players sorted by a given key (descending)."""
        return sorted(
            cls._players.values(),
            key=lambda p: getattr(p, key, 0),
            reverse=True,
        )