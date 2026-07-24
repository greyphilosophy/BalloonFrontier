"""Balloon Frontier — Central Game Catalog

Typed source of truth for all game configuration data.
Replaces tuple-heavy dictionaries scattered across cli_game.py,
discord_bot.py, and fill.py with explicit dataclasses.

No behavior changes — callers migrate at their own pace while
both the old module-level dicts and the new catalog coexist.

## Usage

```python
from balloon_frontier.catalog import CATALOG

# Resolve a gas by ID
gas = CATALOG.gas("helium")

# Resolve an envelope by ID
env = CATALOG.envelope("latex")

# Resolve a payload by ID
payload = CATALOG.payload("camera")

# Resolve a launch site by ID
site = CATALOG.site("mountain")

# Resolve a balloon size by ID
balloon = CATALOG.balloon("s36")

# Iterate options
for gas in CATALOG.all_gases():
    print(gas.name)

# Filter / lookup by property
heliums = CATALOG.gases_by_behavior("lighter")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Tuple


# ═══════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════


class FillMode(str, Enum):
    """Fill mode for the launch state machine.

    AUTO, LIGHT, NORMAL, HEAVY use pre-calculated optimal masses.
    MANUAL lets the player specify an exact gas mass, optionally
    clamped to a burst-safe range.
    """
    AUTO    = "auto"
    LIGHT   = "light"
    NORMAL  = "normal"
    HEAVY   = "heavy"
    MANUAL  = "manual"

    def __new__(cls, value: str):
        obj = str.__new__(cls, value)
        obj._value_ = value
        return obj

    @property
    def label(self) -> str:
        _labels = {
            "auto": "Auto (Optimal)",
            "light": "Light",
            "normal": "Normal",
            "heavy": "Heavy",
            "manual": "Manual",
        }
        return _labels[self.value]

    @property
    def description(self) -> str:
        _descs = {
            "auto": "Calculated optimal fill",
            "light": "Less free lift — slower ascent, higher burst",
            "normal": "Baseline optimal fill",
            "heavy": "More free lift — faster ascent, earlier burst",
            "manual": "Your chosen gas mass",
        }
        return _descs[self.value]

    def get_multiplier(self) -> float:
        """Get the mass multiplier for this fill mode (all except MANUAL)."""
        if self == FillMode.MANUAL:
            raise ValueError("MANUAL mode requires an explicit mass")
        _mults = {
            "auto": 1.0,
            "light": 0.8,
            "normal": 1.0,
            "heavy": 1.2,
        }
        return _mults[self.value]


# ═══════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class GasDefinition:
    """Lifting gas definition.

    Attributes:
        id: Unique identifier (e.g. "helium").
        name: Display name (e.g. "Helium").
        molar_mass: Molar mass in kg/mol.
        cost_per_kg: Cost in-game currency per kilogram.
        gas_behavior: "lighter" | "heavier" | "neutral".
    """
    id: str
    name: str
    molar_mass: float
    cost_per_kg: int
    gas_behavior: str = "lighter"

    @property
    def density_string(self) -> str:
        return f"ρ={self.molar_mass} kg/m³"

    def matches_behavior(self, behavior: str) -> bool:
        return self.gas_behavior.lower() == behavior.lower()


@dataclass(frozen=True, slots=True)
class EnvelopeDefinition:
    """Envelope (balloon) type definition.

    Attributes:
        id: Unique identifier (e.g. "latex").
        name: Display name (e.g. "Latex Weather Balloon").
        max_volume_m3: Nominal volume in cubic metres.
        mass_kg: Envelope dry mass in kg.
        drag_coefficient: Drag coefficient (C_d).
        burst_stretch_ratio: Ratio of burst volume to nominal volume.
        contained_gas: Whether gas is contained (True = latex/superpressure).
        cost: Cost in-game currency.
        safe_fill_fraction: Fraction of burst volume that is safe to fill.
        min_reputation: Minimum reputation to unlock (0 = always available).
    """
    id: str
    name: str
    max_volume_m3: float
    mass_kg: float
    drag_coefficient: float
    burst_stretch_ratio: float
    contained_gas: bool = True
    cost: int = 0
    safe_fill_fraction: float = 0.6
    min_reputation: int = 0

    @property
    def burst_volume_m3(self) -> float:
        """Maximum volume before burst."""
        return self.max_volume_m3 * self.burst_stretch_ratio


@dataclass(frozen=True, slots=True)
class BalloonDefinition:
    """Weather balloon size definition (cli_game style).

    Attributes:
        id: Unique identifier (e.g. "s36").
        name: Display name (e.g. '36"').
        mass_kg: Envelope dry mass.
        max_volume_m3: Nominal volume.
        burst_stretch_ratio: Ratio at burst.
        fill_range_g: Tuple of (min_fill_g, max_fill_g) for safe fill.
    """
    id: str
    name: str
    mass_kg: float
    max_volume_m3: float
    burst_stretch_ratio: float
    fill_range_g: Tuple[int, int] = (0, 0)

    @property
    def burst_volume_m3(self) -> float:
        return self.max_volume_m3 * self.burst_stretch_ratio


@dataclass(frozen=True, slots=True)
class PayloadDefinition:
    """Carried payload definition.

    Attributes:
        id: Unique identifier (e.g. "camera").
        name: Display name (e.g. "Camera").
        mass_kg: Payload mass in kg.
        cost: Cost in-game currency.
        has_valve: Whether this payload is the pressure release valve.
        min_reputation: Minimum reputation to unlock (0 = always available).
    """
    id: str
    name: str
    mass_kg: float
    cost: int = 0
    has_valve: bool = False
    min_reputation: int = 0


@dataclass(frozen=True, slots=True)
class SiteDefinition:
    """Launch site definition (wraps LaunchSiteInfo semantics).

    Attributes:
        id: Unique identifier (e.g. "field").
        name: Display name (e.g. "Open Field").
        altitude_m: Launch altitude above sea level.
        gas_temperature_k: Absolute gas temperature at launch (K).
            If None, derived from atmosphere_temperature(altitude) + offset.
        temperature_offset_k: Offset from standard atmosphere temperature.
        wind_strength: Descriptive wind strength multiplier.
        description: UI text description.
        min_reputation: Minimum reputation to unlock.
    """
    id: str
    name: str
    altitude_m: float = 0.0
    gas_temperature_k: Optional[float] = None
    temperature_offset_k: float = 0.0
    wind_strength: float = 0.0
    description: str = ""
    min_reputation: int = 0


# ═══════════════════════════════════════════════════════════
# Catalog registry
# ═══════════════════════════════════════════════════════════


class _Catalog:
    """Central catalog holding all game definition lookups."""

    # ── Construction (called once at module import) ──────────

    def __init__(self) -> None:
        self._gases: Dict[str, GasDefinition] = {}
        self._envelopes: Dict[str, EnvelopeDefinition] = {}
        self._balloons: Dict[str, BalloonDefinition] = {}
        self._payloads: Dict[str, PayloadDefinition] = {}
        self._sites: Dict[str, SiteDefinition] = {}

        self._build()

    # ── Builder ──────────────────────────────────────────────

    def _build(self) -> None:
        """Populate the catalog with all definitions."""
        # ── Gases ───────────────────────────────────────────
        self._register(
            GasDefinition("helium",      "Helium",      0.0040026, 5, "lighter"),
            GasDefinition("hydrogen",    "Hydrogen",    0.002016,  3, "lighter"),
            GasDefinition("hot_air",     "Hot Air",     0.028965,  1, "neutral"),
            GasDefinition("methane",     "Methane",     0.01604,   4, "lighter"),
        )

        # ── Envelopes (Discord-style) ────────────────────
        self._register(
            EnvelopeDefinition(
                id="mylar", name="Mylar Party Balloon",
                max_volume_m3=200.0, mass_kg=0.05,
                drag_coefficient=2.0, burst_stretch_ratio=3.0,
                contained_gas=True, cost=500, safe_fill_fraction=0.55,
            ),
            EnvelopeDefinition(
                id="latex", name="Latex Weather Balloon",
                max_volume_m3=10.0, mass_kg=1.0,
                drag_coefficient=3.0, burst_stretch_ratio=2.5,
                contained_gas=True, cost=2000, safe_fill_fraction=0.6,
            ),
            EnvelopeDefinition(
                id="zero_pressure", name="Zero-Pressure Polyethylene",
                max_volume_m3=300.0, mass_kg=18.0,
                drag_coefficient=1.5, burst_stretch_ratio=1.8,
                contained_gas=True, cost=15000, safe_fill_fraction=0.65,
            ),
            EnvelopeDefinition(
                id="blimp", name="Small Non-Rigid Blimp",
                max_volume_m3=500.0, mass_kg=45.0,
                drag_coefficient=1.3, burst_stretch_ratio=2.0,
                contained_gas=False, cost=50000, safe_fill_fraction=0.6,
            ),
        )

        # ── Balloon sizes (CLI weather-balloon style) ────
        self._register(
            BalloonDefinition("s21",  "21\"",  0.025,  0.6,   2.3, (10, 120)),
            BalloonDefinition("s29",  "29\"",  0.040,  1.5,   2.3, (20, 250)),
            BalloonDefinition("s36",  "36\"",  0.060,  3.5,   2.3, (30, 1158)),
            BalloonDefinition("s45",  "45\"",  0.085,  6.0,   2.2, (50, 1163)),
            BalloonDefinition("s55",  "55\"",  0.110,  10.0,  2.2, (80, 1500)),
            BalloonDefinition("s70",  "70\"",  0.200,  25.0,  2.2, (150, 3000)),
            BalloonDefinition("s100", "100\"", 0.400,  75.0,  2.1, (400, 7000)),
            BalloonDefinition("s150", "150\"", 0.700,  250.0, 2.0, (1000, 15000)),
        )

        # ── Payloads ───────────────────────────────────────
        self._register(
            PayloadDefinition("camera",      "Camera",           1.5, 500,  False),
            PayloadDefinition("radio",       "Radio Repeater",   2.0, 800,  False),
            PayloadDefinition("weather_sens","Weather Sensor",   0.8, 1200, False),
            PayloadDefinition("battery",     "Battery Pack",     3.0, 1000, False),
            PayloadDefinition("heater",      "Heater",           2.5, 750,  False),
            PayloadDefinition("ballast",     "Ballast (Sand)",  15.0, 300,  False),
            PayloadDefinition("parachute",   "Parachute",        2.0, 600,  False),
            PayloadDefinition("flight_comp", "Flight Computer",  1.2, 2000, False),
            PayloadDefinition("valve",       "Pressure Valve",   0.3, 250,  True),
            # "none" is a special sentinel; not registered as a real payload
        )

        # ── Sites ──────────────────────────────────────────
        self._register(
            SiteDefinition(
                id="field", name="Open Field",
                altitude_m=0.0, gas_temperature_k=288.15,
                temperature_offset_k=0.0, wind_strength=2.0,
                description="Flat terrain, mild crosswind",
            ),
            SiteDefinition(
                id="mountain", name="Mountain Ridge",
                altitude_m=1500.0, gas_temperature_k=278.15,
                temperature_offset_k=-5.0, wind_strength=4.0,
                description="Elevated, colder, stronger wind",
            ),
            SiteDefinition(
                id="rooftop", name="Urban Rooftop",
                altitude_m=50.0, gas_temperature_k=291.15,
                temperature_offset_k=3.0, wind_strength=3.0,
                description="Warm microclimate, moderate wind",
            ),
        )

    def _register(self, *defs) -> None:
        for d in defs:
            if isinstance(d, GasDefinition):
                self._gases[d.id] = d
            elif isinstance(d, EnvelopeDefinition):
                self._envelopes[d.id] = d
            elif isinstance(d, BalloonDefinition):
                self._balloons[d.id] = d
            elif isinstance(d, PayloadDefinition):
                self._payloads[d.id] = d
            elif isinstance(d, SiteDefinition):
                self._sites[d.id] = d

    # ── Lookup methods ─────────────────────────────────────

    def gas(self, id_or_name: str) -> GasDefinition:
        """Look up a gas by id or by name (case-insensitive)."""
        if id_or_name in self._gases:
            return self._gases[id_or_name]
        for g in self._gases.values():
            if g.name.lower() == id_or_name.lower():
                return g
        raise KeyError(f"Unknown gas: {id_or_name!r}")

    def envelope(self, id_or_name: str) -> EnvelopeDefinition:
        """Look up an envelope by id or by name (case-insensitive)."""
        if id_or_name in self._envelopes:
            return self._envelopes[id_or_name]
        for e in self._envelopes.values():
            if e.name.lower() == id_or_name.lower():
                return e
        raise KeyError(f"Unknown envelope: {id_or_name!r}")

    def balloon(self, id_or_name: str) -> BalloonDefinition:
        """Look up a balloon size by id or by name (case-insensitive)."""
        if id_or_name in self._balloons:
            return self._balloons[id_or_name]
        for b in self._balloons.values():
            if b.name.lower() == id_or_name.lower():
                return b
        raise KeyError(f"Unknown balloon size: {id_or_name!r}")

    def payload(self, id_or_name: str) -> PayloadDefinition:
        """Look up a payload by id or by name (case-insensitive)."""
        if id_or_name in self._payloads:
            return self._payloads[id_or_name]
        for p in self._payloads.values():
            if p.name.lower() == id_or_name.lower():
                return p
        raise KeyError(f"Unknown payload: {id_or_name!r}")

    def site(self, id_or_name: str) -> SiteDefinition:
        """Look up a site by id or by name (case-insensitive)."""
        if id_or_name in self._sites:
            return self._sites[id_or_name]
        for s in self._sites.values():
            if s.name.lower() == id_or_name.lower():
                return s
        raise KeyError(f"Unknown site: {id_or_name!r}")

    # ── Iteration / query methods ──────────────────────────

    def all_gases(self) -> List[GasDefinition]:
        return list(self._gases.values())

    def all_envelopes(self) -> List[EnvelopeDefinition]:
        return list(self._envelopes.values())

    def all_balloons(self) -> List[BalloonDefinition]:
        return list(self._balloons.values())

    def all_payloads(self) -> List[PayloadDefinition]:
        return list(self._payloads.values())

    def all_sites(self) -> List[SiteDefinition]:
        return list(self._sites.values())

    def gas_ids(self) -> List[str]:
        return list(self._gases.keys())

    def envelope_ids(self) -> List[str]:
        return list(self._envelopes.keys())

    def balloon_ids(self) -> List[str]:
        return list(self._balloons.keys())

    def payload_ids(self) -> List[str]:
        return list(self._payloads.keys())

    def site_ids(self) -> List[str]:
        return list(self._sites.keys())

    def gases_by_behavior(self, behavior: str) -> List[GasDefinition]:
        """Filter gases by gas_behavior string."""
        return [g for g in self._gases.values() if g.matches_behavior(behavior)]


# ═══════════════════════════════════════════════════════════
# Module-level singleton
# ═══════════════════════════════════════════════════════════


CATALOG = _Catalog()


# ═══════════════════════════════════════════════════════════
# Backward-compatibility shims
# ═══════════════════════════════════════════════════════════
# The old tuple dicts are re-exposed so existing code continues
# to work without immediate changes.  They are derived from the
# canonical catalog so they always stay in sync.
# ═══════════════════════════════════════════════════════════


# cli_game.py style: {"id": ("name", molar_mass, behavior)}
def _build_cli_gas_dict() -> Dict[str, Tuple[str, float, str]]:
    return {
        g.id: (g.name, g.molar_mass, g.gas_behavior) for g in CATALOG.all_gases()
    }

GAS_OPTIONS = _build_cli_gas_dict()  # For cli_game.py compat

# cli_game.py style: {"id": ("name", mass_kg, has_valve)}
def _build_cli_payload_dict() -> Dict[str, Tuple[str, float, bool]]:
    payloads: Dict[str, Tuple[str, float, bool]] = {}
    for p in CATALOG.all_payloads():
        payloads[p.id] = (p.name, p.mass_kg, p.has_valve)
    # Add the "none" sentinel
    payloads["none"] = ("None", 1.0, False)
    return payloads

PAYLOADS = _build_cli_payload_dict()  # For cli_game.py compat

# discord_bot.py style: {"id": ("name", molar_mass, cost_per_kg)}
def _build_discord_gas_dict() -> Dict[str, Tuple[str, float, int]]:
    return {
        g.id: (g.name, g.molar_mass, g.cost_per_kg)
        for g in CATALOG.all_gases()
    }

DISCORD_GAS_OPTIONS = _build_discord_gas_dict()

# discord_bot.py style: {"id": ("name", volume, mass, drag, burst, cost)}
def _build_discord_envelope_dict() -> Dict[str, Tuple[str, float, float, float, float, int]]:
    return {
        e.id: (e.name, e.max_volume_m3, e.mass_kg,
               e.drag_coefficient, e.burst_stretch_ratio, e.cost)
        for e in CATALOG.all_envelopes()
    }

DISCORD_ENVELOPE_OPTIONS = _build_discord_envelope_dict()

# discord_bot.py style: {"id": ("name", mass, cost, has_valve)}
def _build_discord_payload_dict() -> Dict[str, Tuple[str, float, int, bool]]:
    d: Dict[str, Tuple[str, float, int, bool]] = {}
    for p in CATALOG.all_payloads():
        d[p.id] = (p.name, p.mass_kg, p.cost, p.has_valve)
    d["none"] = ("None", 1.0, 100, False)
    return d

DISCORD_PAYLOAD_OPTIONS = _build_discord_payload_dict()