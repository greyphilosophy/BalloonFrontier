"""Balloon Frontier - Progression System

Implements budget management, envelope unlocks, and player progression.
Players earn budget from successful missions, unlock envelopes, and
accumulate reputation from consistent flights.

Reference: GDD Sections 20, 21.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class EnvelopeUnlock:
    """Defines when and how an envelope type unlocks."""
    id: str
    name: str
    cost: int  # Budget needed to unlock
    min_reputation: int
    max_volume_m3: float
    burst_stretch_ratio: float
    contained_gas: bool
    mass_kg: float
    description: str = ""

# Envelope progression tree
ENVELOPES = [
    EnvelopeUnlock(
        id="latex", name="Latex Party Balloon",
        cost=0, min_reputation=0,
        max_volume_m3=10.0, burst_stretch_ratio=3.0,
        contained_gas=True, mass_kg=0.5,
        description="The classic: light, stretchy, bursts at 3x volume"),
    EnvelopeUnlock(
        id="mylar", name="Mylar Weather Balloon",
        cost=200, min_reputation=2,
        max_volume_m3=200.0, burst_stretch_ratio=2.5,
        contained_gas=True, mass_kg=2.0,
        description="Durable and gas-tight for longer flights"),
    EnvelopeUnlock(
        id="zero_pressure", name="Zero-Pressure Polyethylene",
        cost=500, min_reputation=5,
        max_volume_m3=300.0, burst_stretch_ratio=2.0,
        contained_gas=False, mass_kg=5.0,
        description="Vents excess gas — survives higher but loses lift"),
    EnvelopeUnlock(
        id="blimp", name="Small Non-Rigid Blimp",
        cost=1200, min_reputation=8,
        max_volume_m3=500.0, burst_stretch_ratio=1.5,
        contained_gas=True, mass_kg=12.0,
        description="Big and sturdy — carries everything"),
]

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
    """List envelopes the player has unlocked based on reputation and budget."""
    unlocked = []
    for e in ENVELOPES:
        if reputation >= e.min_reputation and budget >= e.cost:
            unlocked.append(e)
    return unlocked

class PlayerState:
    """Tracks a player's progression state."""

    def __init__(self, player_id: str = ""):
        self._player_id = player_id
        self.reputation: int = 0
        self.budget: int = 100
        self.unlocked_envelopes: List[str] = []
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

        # Check for new envelope unlocks
        new_unlocks = []
        for e in ENVELOPES:
            if e.id not in self.unlocked_envelopes:
                if self.reputation >= e.min_reputation:
                    self.unlocked_envelopes.append(e.id)
                    new_unlocks.append(e.name)

        # Track completed missions
        if mission_id and mission_id not in self.missions_completed:
            self.missions_completed.append(mission_id)

        return {
            "success": success,
            "reputation_gained": rep_gain,
            "budget_earned": budget_earned,
            "new_unlocks": new_unlocks,
        }

    def save(self, path: Optional[str] = None):
        """Save player state to JSON.

        Args:
            path: Optional path. If None, saves to ~/.balloon_frontier/{player_id}.json
        """
        if path is None:
            # Use a player-specific save file.
            save_path = Path.home() / ".balloon_frontier" / f"{self._player_id}.json"
        else:
            save_path = Path(path).expanduser()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps({
            "reputation": self.reputation,
            "budget": self.budget,
            "unlocked_envelopes": self.unlocked_envelopes,
            "total_flights": self.total_flights,
            "successful_flights": self.successful_flights,
            "missions_completed": self.missions_completed,
        }))

    @classmethod
    def load(cls, path_or_player_id: Optional[str] = None, path: Optional[str] = None) -> "PlayerState":
        """Load player state from JSON.

        Args:
            path_or_player_id: Explicit file path, or player_id for auto-path.
            path: Alias for path_or_player_id (for clarity).

        When path_or_player_id is an existing file path, it is used directly.
        Otherwise it is treated as a player_id and resolved to
        ~/.balloon_frontier/{player_id}.json.
        """
        if path is not None:
            save_path = Path(path).expanduser()
        elif path_or_player_id is not None and Path(path_or_player_id).expanduser().exists():
            save_path = Path(path_or_player_id).expanduser()
        elif path_or_player_id is not None:
            save_path = Path.home() / ".balloon_frontier" / f"{path_or_player_id}.json"
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
            state.save()  # Uses player-specific path when path=None
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
