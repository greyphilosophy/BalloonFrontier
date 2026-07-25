"""Balloon Frontier - Progression System

Implements budget management, equipment unlocks, and player progression.
Players earn budget from successful missions, unlock envelopes/payloads/sites,
and accumulate reputation from consistent flights.

Unlock conditions use OR logic — meeting EITHER the credit threshold
OR the reputation threshold is sufficient.

Game DATA lives in CATALOG.  Progression defines only the unlock rules
(cost + reputation thresholds).  Helper functions return combined views
that preserve every attribute old code expects.

Reference: GDD Sections 20, 21.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from balloon_frontier.catalog import CATALOG, PayloadDefinition, EnvelopeDefinition, SiteDefinition


# ═══════════════════════════════════════════════════════════════════════════
# UnlockRule — progression-only data
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class UnlockRule:
    """Defines when an item unlocks — nothing more.

    All physical / display data is resolved from CATALOG at lookup time.
    """
    id: str
    unlock_cost: int = 0
    min_reputation: int = 0
    category: str = ""
    description: str = ""

    @property
    def cost(self) -> int:
        """Alias for compatibility."""
        return self.unlock_cost


# ── Envelope unlock rules ──────────────────────────────────────────────
# CATALOG has mass, volume, stretch, contained_gas, name, drag.
# Progression only gates them.

ENVELOPE_RULES: List[UnlockRule] = [
    UnlockRule(id="latex", unlock_cost=2000, min_reputation=0),
    UnlockRule(id="mylar", unlock_cost=500, min_reputation=5),
    UnlockRule(id="zero_pressure", unlock_cost=15000, min_reputation=10),
    UnlockRule(id="blimp", unlock_cost=50000, min_reputation=20),
]

# ── Payload unlock rules ───────────────────────────────────────────────
# CATALOG has mass, cost, has_valve. Progression only gates.

PAYLOAD_RULES: List[UnlockRule] = [
    # Always available (cost=0, min_reputation=0)
    UnlockRule(id="battery", category="power"),
    UnlockRule(id="parachute", category="recovery"),
    UnlockRule(id="parafoil", category="recovery"),
    UnlockRule(id="ballast", category="ballast"),
    UnlockRule(id="valve", unlock_cost=250, category="vent"),
    UnlockRule(id="propeller_pod", category="control"),
    UnlockRule(id="gps_receiver", category="sensor"),
    UnlockRule(id="barometer", category="sensor"),
    UnlockRule(id="thermometer", category="sensor"),
    UnlockRule(id="camera", category="sensor"),
    UnlockRule(id="radio", category="sensor"),
    UnlockRule(id="weather_sensor", category="sensor"),
    UnlockRule(id="solar_panel", category="power"),
    # Advanced — require reputation >= 3
    UnlockRule(id="heater", unlock_cost=250, min_reputation=3, category="heater"),
    UnlockRule(id="flight_computer", unlock_cost=750, min_reputation=3, category="sensor"),
]

# ── Site unlock rules ──────────────────────────────────────────────────
# CATALOG has altitude, gas_temperature, wind_strength, temperature_offset.

SITE_RULES: List[UnlockRule] = [
    UnlockRule(id="field", min_reputation=0),
    UnlockRule(id="rooftop", min_reputation=3),
    UnlockRule(id="mountain", min_reputation=8),
]


# ═══════════════════════════════════════════════════════════════════════════
# Compat views — combine catalog data + rule for API compatibility
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class UnlockableEnvelope:
    """Envelope with both catalog definition and unlock rule."""
    definition: EnvelopeDefinition
    rule: UnlockRule

    @property
    def id(self) -> str:
        return self.definition.id

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def cost(self) -> int:
        return self.rule.unlock_cost

    @property
    def min_reputation(self) -> int:
        return self.rule.min_reputation

    @property
    def max_volume_m3(self) -> float:
        return self.definition.max_volume_m3

    @property
    def burst_stretch_ratio(self) -> float:
        return self.definition.burst_stretch_ratio

    @property
    def contained_gas(self) -> bool:
        return self.definition.contained_gas

    @property
    def mass_kg(self) -> float:
        return self.definition.mass_kg

    @property
    def drag_coefficient(self) -> float:
        return self.definition.drag_coefficient

    @property
    def safe_fill_fraction(self) -> float:
        return self.definition.safe_fill_fraction

    @property
    def description(self) -> str:
        return self.definition.description


@dataclass(frozen=True)
class UnlockablePayload:
    """Payload with both catalog definition and unlock rule."""
    definition: PayloadDefinition
    rule: UnlockRule

    @property
    def id(self) -> str:
        return self.definition.id

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def cost(self) -> int:
        return self.rule.unlock_cost

    @property
    def min_reputation(self) -> int:
        return self.rule.min_reputation

    @property
    def mass_kg(self) -> float:
        return self.definition.mass_kg

    @property
    def tag(self) -> str:
        return self.rule.category

    @property
    def has_valve(self) -> bool:
        return self.definition.has_valve

    @property
    def description(self) -> str:
        return self.definition.description


@dataclass(frozen=True)
class UnlockableSite:
    """Site with both catalog definition and unlock rule."""
    definition: SiteDefinition
    rule: UnlockRule

    @property
    def id(self) -> str:
        return self.definition.id

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def cost(self) -> int:
        return self.rule.unlock_cost

    @property
    def min_reputation(self) -> int:
        return self.rule.min_reputation

    @property
    def altitude_m(self) -> float:
        return self.definition.altitude_m

    @property
    def wind_strength(self) -> float:
        return self.definition.wind_strength

    @property
    def temperature_offset_k(self) -> float:
        return self.definition.temperature_offset_k

    @property
    def gas_temperature_k(self) -> float:
        return self.definition.gas_temperature_k

    @property
    def description(self) -> str:
        return self.definition.description


# ═══════════════════════════════════════════════════════════════════════════
# Helpers — return compat views, iterate rules + catalog
# ═══════════════════════════════════════════════════════════════════════


def _all_envelope_views() -> List[UnlockableEnvelope]:
    return [
        UnlockableEnvelope(CATALOG.envelope(r.id), r) for r in ENVELOPE_RULES
    ]


def _all_payload_views() -> List[UnlockablePayload]:
    return [
        UnlockablePayload(CATALOG.payload(r.id), r) for r in PAYLOAD_RULES
    ]


def _all_site_views() -> List[UnlockableSite]:
    return [
        UnlockableSite(CATALOG.site(r.id), r) for r in SITE_RULES
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Backward-compat aliases (for tests and code that import by these names)
# ═══════════════════════════════════════════════════════════════════════


# Old code: from progression import PayloadUnlock/EnvelopeUnlock/SiteUnlock
# We alias the compat view types so isinstance(x, PayloadUnlock) still works.

PayloadUnlock = UnlockablePayload
EnvelopeUnlock = UnlockableEnvelope
SiteUnlock = UnlockableSite

# Old code: ENVELOPES, PAYLOAD_UNLOCKS, SITES as lists of the compat views.
ENVELOPES = _all_envelope_views()
PAYLOAD_UNLOCKS = _all_payload_views()
SITES = _all_site_views()


# ── Envelope helpers ──────────────────────────────────────────────────

def get_unlock_path() -> List[str]:
    """Return the unlock order for envelopes (IDs in definition order)."""
    return [e.id for e in ENVELOPE_RULES]


def get_envelope(env_id: str) -> UnlockableEnvelope:
    """Get an envelope by ID, returning a compat view with catalog + rule."""
    for r in ENVELOPE_RULES:
        if r.id == env_id:
            return UnlockableEnvelope(CATALOG.envelope(env_id), r)
    # Fallback: default to first envelope
    return UnlockableEnvelope(CATALOG.envelope(ENVELOPE_RULES[0].id), ENVELOPE_RULES[0])


def list_unlocked_envelopes(reputation: int, budget: int) -> List[UnlockableEnvelope]:
    """List envelopes the player has unlocked based on reputation or budget.

    Unlock uses OR logic: meet EITHER the reputation OR the cost threshold.
    Budget gates only apply when cost > 0.
    """
    unlocked = []
    for r in ENVELOPE_RULES:
        e = UnlockableEnvelope(CATALOG.envelope(r.id), r)
        if r.min_reputation == 0 and r.unlock_cost == 0:
            unlocked.append(e)
        elif reputation >= r.min_reputation or (r.unlock_cost > 0 and budget >= r.unlock_cost):
            unlocked.append(e)
    return unlocked


def list_locked_envelopes(reputation: int, budget: int) -> List[UnlockableEnvelope]:
    """Return envelopes that are currently locked."""
    unlocked_ids = {e.id for e in list_unlocked_envelopes(reputation, budget)}
    return [e for e in _all_envelope_views() if e.id not in unlocked_ids]


def envelope_needs(reputation: int, budget: int, env: UnlockableEnvelope) -> str:
    """Return a human-readable string describing what's needed to unlock an envelope."""
    rep_ok = reputation >= env.rule.min_reputation
    budget_ok = budget >= env.rule.unlock_cost

    if rep_ok and budget_ok:
        return ""  # already unlocked (shouldn't happen)
    if rep_ok:
        return f"{env.rule.unlock_cost - budget} more credits"
    if budget_ok:
        return f"{env.rule.min_reputation - reputation} more reputation"
    # Need both — pick whichever is closer proportionally
    rep_pct = reputation / env.rule.min_reputation if env.rule.min_reputation > 0 else 1.0
    budget_pct = budget / env.rule.unlock_cost if env.rule.unlock_cost > 0 else 1.0
    if rep_pct < budget_pct:
        return f"{env.rule.min_reputation - reputation} more reputation"
    return f"{env.rule.unlock_cost - budget} more credits"


# ── Payload helpers ───────────────────────────────────────────────────

def list_unlocked_payloads(reputation: int, budget: int) -> List[UnlockablePayload]:
    """List payloads the player can use based on reputation or budget."""
    unlocked = []
    for r in PAYLOAD_RULES:
        p = UnlockablePayload(CATALOG.payload(r.id), r)
        if reputation >= r.min_reputation or (r.unlock_cost > 0 and budget >= r.unlock_cost):
            unlocked.append(p)
    return unlocked


def list_locked_payloads(reputation: int, budget: int) -> List[UnlockablePayload]:
    """Return payloads that are currently locked."""
    unlocked_ids = {p.id for p in list_unlocked_payloads(reputation, budget)}
    return [p for p in _all_payload_views() if p.id not in unlocked_ids]


# ── Site helpers ──────────────────────────────────────────────────────

def list_unlocked_sites(reputation: int, budget: int) -> List[UnlockableSite]:
    """List sites the player can launch from."""
    unlocked = []
    for r in SITE_RULES:
        s = UnlockableSite(CATALOG.site(r.id), r)
        if reputation >= r.min_reputation or (r.unlock_cost > 0 and budget >= r.unlock_cost):
            unlocked.append(s)
    return unlocked


def list_locked_sites(reputation: int, budget: int) -> List[UnlockableSite]:
    """Return sites that are currently locked."""
    unlocked_ids = {s.id for s in list_unlocked_sites(reputation, budget)}
    return [s for s in _all_site_views() if s.id not in unlocked_ids]


# ═══════════════════════════════════════════════════════════════════════════
# Player state
# ═══════════════════════════════════════════════════════════════════════


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

        Returns a list of newly unlocked names (from catalog).
        """
        new_unlocks: List[str] = []

        # Envelopes
        for r in ENVELOPE_RULES:
            if r.id not in self.unlocked_envelopes:
                if self.reputation >= r.min_reputation or (r.unlock_cost > 0 and self.budget >= r.unlock_cost):
                    self.unlocked_envelopes.append(r.id)
                    self.unlocked_envelopes.append(CATALOG.envelope(r.id).name)  # compat: store name too
                    new_unlocks.append(CATALOG.envelope(r.id).name)

        # Payloads
        for r in PAYLOAD_RULES:
            if r.id not in self.unlocked_payloads:
                if self.reputation >= r.min_reputation or (r.unlock_cost > 0 and self.budget >= r.unlock_cost):
                    self.unlocked_payloads.append(r.id)
                    new_unlocks.append(CATALOG.payload(r.id).name)

        # Sites
        for r in SITE_RULES:
            if r.id not in self.unlocked_sites:
                if self.reputation >= r.min_reputation or (r.unlock_cost > 0 and self.budget >= r.unlock_cost):
                    self.unlocked_sites.append(r.id)
                    new_unlocks.append(CATALOG.site(r.id).name)

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
            f"⚡ **{self.player_id}'s Status**",
            f"  Reputation: {self.reputation}",
            f"  Budget: ${self.budget}",
            f"  Flights: {self.total_flights} ({self.successful_flights} successful)",
        ]
        return "\n".join(lines)

    def save(self, path: Optional[str] = None):
        """Save player state to JSON."""
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
        """Load player state from JSON."""
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


# ═══════════════════════════════════════════════════════════════════════════
# Player registry (unchanged)
# ═══════════════════════════════════════════════════════════════════════


class PlayerRegistry:
    """Simple in-memory player registry with per-player file persistence."""
    _players: Dict[str, PlayerState] = {}
    _save_dir = Path.home() / ".balloon_frontier"

    @classmethod
    def get_or_create(cls, player_id: str) -> PlayerState:
        if player_id not in cls._players:
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


# ═══════════════════════════════════════════════════════════════════════════
# Repository pattern (PR G) — unchanged
# ═══════════════════════════════════════════════════════════════════════


from typing import Protocol, runtime_checkable


@runtime_checkable
class PlayerRepository(Protocol):
    """Read/write contract for player persistence.

    Implementations:

    * PlayerRegistryRepository (default) — wraps PlayerRegistry in-memory
      JSON-backed storage.

    * (Future) SqlitePlayerRepository — reads/writes an SQLite database
      so the game no longer needs global state.
    """

    def get(self, player_id: str) -> PlayerState:
        """Return player state; create defaults if unknown.

        May raise on I/O errors that prevent loading.
        """

    def save(self, player: PlayerState) -> None:
        """Persist player state to the backing store.

        May raise on I/O errors.
        """


class PlayerRegistryRepository:
    """Repository adapter that delegates to PlayerRegistry."""

    def get(self, player_id: str) -> PlayerState:
        return PlayerRegistry.get_or_create(player_id)

    def save(self, player: PlayerState) -> None:
        player.save()

    def flush_all(self) -> int:
        """Save all in-memory players.  Returns count saved."""
        return PlayerRegistry.flush_all()