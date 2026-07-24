"""Balloon Frontier — Typed Launch & Result Models

Defines the canonical data contracts for:
- LaunchRequest: a player's launch configuration (gas, envelope, payload, site, fill mode)
- TelemetryPoint: a single simulation tick's snapshot
- FlightResult: the full outcome of a simulation run

These types replace the scattered dicts and positional parameters used across
cli_game.py and discord_bot.py. Existing callers continue via backward-compat
shims that convert old signatures into the new dataclasses.

## Usage

```python
from balloon_frontier.launch_result import (
    LaunchRequest,
    FlightResult,
    TelemetryPoint,
    FillMode,
)

# Build a launch request
req = LaunchRequest(
    gas_id="helium",
    envelope_id="latex",
    payload_ids=("camera", "battery"),
    launch_site_id="field",
    fill_mode=FillMode.NORMAL,
)

# Convert to simulation-compatible params
sim_config = req.to_simulation_config()
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

from enum import Enum

if TYPE_CHECKING:
    from balloon_frontier.simulation import SimulationState

from balloon_frontier.catalog import (
    CATALOG,
    GasDefinition,
    EnvelopeDefinition,
    BalloonDefinition,
    PayloadDefinition,
    SiteDefinition,
    FillMode,
)


# ═══════════════════════════════════════════════════════════
# TelemetryPoint
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class TelemetryPoint:
    """Single tick snapshot from the simulation engine.

    Mirrors the dict keys produced by ``simulation_step()`` so that
    callers can inspect per-tick flight data without relying on
    raw-dict field names.

    Attributes:
        time_s: Elapsed simulation time in seconds.
        x_m: Horizontal drift position in metres.
        vx_mps: Horizontal drift velocity in m/s.
        altitude_m: Altitude above sea level in metres.
        velocity_mps: Vertical velocity in m/s (positive = ascending).
        gas_volume_m3: Current gas volume in cubic metres.
        ambient_pressure_pa: Ambient pressure at current altitude.
        ambient_temperature_k: Ambient temperature at current altitude.
        net_lift_N: Net vertical force (buoyancy + drag - weight).
        buoyancy_N: Buoyant force.
        weight_N: Total weight force.
        drag_N: Vertical drag force.
        drag_x_N: Horizontal drag force.
        gas_mass_kg: Remaining gas mass.
        total_mass_kg: Total vehicle mass (gas + envelope + payload + ballast).
        burst: Whether the balloon has burst.
        landed: Whether the balloon has landed safely.
        crashed: Whether the balloon crashed on landing.
    """

    time_s: float
    altitude_m: float
    velocity_mps: float
    gas_volume_m3: float
    ambient_pressure_pa: float
    ambient_temperature_k: float
    net_lift_N: float
    buoyancy_N: float
    weight_N: float
    drag_N: float
    gas_mass_kg: float
    total_mass_kg: float
    burst: bool = False
    landed: bool = False
    crashed: bool = False
    x_m: float = 0.0
    vx_mps: float = 0.0


# ═══════════════════════════════════════════════════════════
# LaunchRequest
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """Immutable description of a player's launch configuration.

    This is the canonical input to the flight pipeline. All callers
    (Discord, CLI, missions) construct one instead of passing raw dicts.

    Attributes:
        gas_id: Gas identifier (e.g. "helium", "hydrogen", "hot_air", "methane").
        envelope_id: Envelope identifier (e.g. "latex", "mylar", "blimp").
        payload_ids: Tuple of payload identifiers (e.g. ("camera", "battery")).
            "none" means no payload.
        launch_site_id: Launch site identifier (e.g. "field", "mountain", "rooftop").
        fill_mode: Fill mode dictating the gas mass multiplier.
        manual_gas_mass_kg: Explicit gas mass (used when fill_mode is MANUAL).
        player_id: Optional player identifier for progression tracking.
        balloon_size: Optional weather balloon size (e.g. "s36"). If None, uses
            the envelope's default fill parameters.
        gas_temperature_delta_k: Optional gas temperature offset from ambient.
            If None, defaults to ambient at launch altitude.
    """

    gas_id: str
    envelope_id: str
    payload_ids: Tuple[str, ...] = ()
    launch_site_id: str = "field"
    fill_mode: FillMode = FillMode.AUTO
    manual_gas_mass_kg: Optional[float] = None
    player_id: Optional[str] = None
    balloon_size: Optional[str] = None
    gas_temperature_delta_k: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate the request against the catalog."""
        # Validate gas
        try:
            CATALOG.gas(self.gas_id)
        except KeyError:
            raise ValueError(f"Unknown gas: {self.gas_id!r}")

        # Validate envelope
        try:
            CATALOG.envelope(self.envelope_id)
        except KeyError:
            raise ValueError(f"Unknown envelope: {self.envelope_id!r}")

        # Validate payload IDs
        for pid in self.payload_ids:
            if pid != "none":
                try:
                    CATALOG.payload(pid)
                except KeyError:
                    raise ValueError(f"Unknown payload: {pid!r}")

        # Validate site
        try:
            CATALOG.site(self.launch_site_id)
        except KeyError:
            raise ValueError(f"Unknown site: {self.launch_site_id!r}")

        # Validate balloon size if specified
        if self.balloon_size is not None:
            try:
                CATALOG.balloon(self.balloon_size)
            except KeyError:
                raise ValueError(f"Unknown balloon size: {self.balloon_size!r}")

        # Validate MANUAL mode has explicit mass
        if self.fill_mode == FillMode.MANUAL and self.manual_gas_mass_kg is None:
            raise ValueError(
                "MANUAL mode requires manual_gas_mass_kg to be specified"
            )

    @property
    def gas(self) -> GasDefinition:
        """Resolve the gas definition."""
        return CATALOG.gas(self.gas_id)

    @property
    def envelope(self) -> EnvelopeDefinition:
        """Resolve the envelope definition."""
        return CATALOG.envelope(self.envelope_id)

    @property
    def site(self) -> SiteDefinition:
        """Resolve the site definition."""
        return CATALOG.site(self.launch_site_id)

    @property
    def balloon(self) -> Optional[BalloonDefinition]:
        """Resolve the balloon size definition if specified."""
        if self.balloon_size:
            return CATALOG.balloon(self.balloon_size)
        return None

    @property
    def payloads(self) -> List[PayloadDefinition]:
        """Resolve all payload definitions.
        
        Note: "none" is a sentinel with no catalog entry and contributes
        0 kg. If you want the old 1 kg default, explicitly include the
        payload ID you want.
        """
        return [CATALOG.payload(pid) for pid in self.payload_ids if pid != "none"]

    @property
    def total_payload_mass_kg(self) -> float:
        """Sum of all payload masses."""
        return sum(p.mass_kg for p in self.payloads)

    @property
    def gas_mass_kg(self) -> float:
        """Calculate the gas mass based on fill mode.

        For AUTO/NORMAL/HEAVY/LIGHT modes, uses the envelope's burst volume
        and the fill mode's multiplier to compute optimal gas mass.
        For MANUAL mode, returns the user-specified mass.
        """
        if self.fill_mode == FillMode.MANUAL:
            assert self.manual_gas_mass_kg is not None
            return self.manual_gas_mass_kg

        multiplier = self.fill_mode.get_multiplier()
        burst_volume = self.envelope.burst_volume_m3
        gas = self.gas

        # Ideal gas law: m = P * V * M / (R * T)
        # At sea level: P = 101325 Pa, T = 288.15 K
        from balloon_frontier.physics import (
            atmosphere_pressure,
            gas_density,
        )

        ambient_pressure = atmosphere_pressure(0.0)  # Sea level reference
        ambient_temp = 288.15  # Standard sea level temperature

        # Gas density at ideal fill conditions
        gas_density_val = gas_density(
            gas.id, ambient_temp, ambient_pressure
        )

        # Ideal gas mass at burst volume * multiplier (already in kg)
        gas_mass = gas_density_val * burst_volume * multiplier

        # Clamp to balloon size fill range if specified
        if self.balloon and self.balloon.fill_range_g != (0, 0):
            min_g = float(self.balloon.fill_range_g[0])
            max_g = float(self.balloon.fill_range_g[1])
            min_mass_kg = min_g / 1000.0  # Limits are in grams, convert to kg
            max_mass_kg = max_g / 1000.0  # Limits are in grams, convert to kg
            return min(max(gas_mass, min_mass_kg), max_mass_kg)

        return gas_mass

    def to_simulation_state(self) -> SimulationState:
        """Convert to a SimulationState object.

        This allows the typed request to be passed directly into the
        simulation engine without manual field mapping.
        """
        from balloon_frontier.simulation import (
            EnvelopeConfig,
            SimulationState,
        )

        env_def = self.envelope
        env_config = EnvelopeConfig(
            max_volume_m3=env_def.max_volume_m3,
            burst_stretch_ratio=env_def.burst_stretch_ratio,
            drag_coefficient=env_def.drag_coefficient,
            mass_kg=env_def.mass_kg,
            contained_gas=env_def.contained_gas,
        )

        site = self.site
        gas_temp = self.gas_temperature_delta_k

        # Build payload mass sum
        payload_mass = self.total_payload_mass_kg

        # Check if payload includes a pressure valve
        has_valve = any(p.has_valve for p in self.payloads)

        # Ballast: default 0 kg (no hidden ballast)
        ballast_mass = 0.0

        return SimulationState(
            altitude_m=site.altitude_m,
            gas_type=self.gas.id,
            gas_mass_kg=self.gas_mass_kg,
            gas_temperature_delta_k=gas_temp,
            payload_mass_kg=payload_mass,
            ballast_mass_kg=ballast_mass,
            envelope=env_config,
            wind_enabled=True,
            wind_site_id=site.id,
            terrain_base_altitude_offset_m=0.0,
            has_pressure_valve=has_valve,
        )

    def to_result_summary(self) -> str:
        """Build a human-readable summary string for post-flight reports."""
        env = self.envelope
        gas = self.gas

        lines = [
            f"🎈 Launch Configuration",
            f"",
            f"Gas: {gas.name} ({gas.molar_mass_string})",
            f"Envelope: {env.name}",
            f"  Volume: {env.max_volume_m3} m³ | Burst: {env.burst_volume_m3} m³",
            f"Fill mode: {self.fill_mode.label}",
            f"Gas mass: {self.gas_mass_kg:.2f} kg",
            f"",
        ]

        if self.payload_ids:
            lines.append("Payloads:")
            for pid in self.payload_ids:
                if pid == "none":
                    continue
                p = CATALOG.payload(pid)
                valve_mark = " [valve]" if p.has_valve else ""
                lines.append(f"  • {p.name} ({p.mass_kg} kg){valve_mark}")
            lines.append("")

        site = self.site
        lines.append(f"Site: {site.name}")
        lines.append(f"  Altitude: {site.altitude_m} m")
        if site.wind_strength > 0:
            lines.append(f"  Wind: {site.wind_strength}x")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# FlightResult
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class FlightResult:
    """Complete result of a simulation run.

    Attributes:
        telemetry: List of TelemetryPoint snapshots (one per tick or sample interval).
        peak_altitude_m: Maximum altitude reached during the flight.
        duration_s: Total flight duration in seconds.
        burst: Whether the balloon burst during the flight.
        landed: Whether the balloon landed (altitude reached ground).
        crashed: Whether the balloon crashed on landing.
        final_altitude_m: Altitude at end of flight.
        final_velocity_mps: Vertical velocity at end of flight.
        final_gas_mass_kg: Remaining gas mass at end of flight.
        launch_request: The original launch configuration.
        score: Flight score (computed by flight_score module).
    """

    telemetry: tuple[TelemetryPoint, ...]
    launch_request: LaunchRequest

    @property
    def peak_altitude_m(self) -> float:
        """Maximum altitude reached during the flight."""
        if not self.telemetry:
            return 0.0
        return max(tp.altitude_m for tp in self.telemetry)

    @property
    def duration_s(self) -> float:
        """Total flight duration in seconds."""
        if not self.telemetry:
            return 0.0
        return self.telemetry[-1].time_s

    @property
    def burst(self) -> bool:
        return any(tp.burst for tp in self.telemetry)

    @property
    def landed(self) -> bool:
        return any(tp.landed for tp in self.telemetry)

    @property
    def crashed(self) -> bool:
        return any(tp.crashed for tp in self.telemetry)

    @property
    def final_altitude_m(self) -> float:
        if not self.telemetry:
            return 0.0
        return self.telemetry[-1].altitude_m

    @property
    def final_velocity_mps(self) -> float:
        if not self.telemetry:
            return 0.0
        return self.telemetry[-1].velocity_mps

    @property
    def final_gas_mass_kg(self) -> float:
        if not self.telemetry:
            return 0.0
        return self.telemetry[-1].gas_mass_kg

    @property
    def flight_time_label(self) -> str:
        """Human-readable flight duration."""
        total_seconds = int(self.duration_s)
        minutes, seconds = divmod(total_seconds, 60)
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @property
    def peak_altitude_label(self) -> str:
        """Human-readable peak altitude."""
        if self.peak_altitude_m >= 1000:
            return f"{self.peak_altitude_m / 1000:.1f} km"
        return f"{self.peak_altitude_m:.0f} m"

    def end_state(self) -> str:
        """Return the end state description."""
        if self.crashed:
            return "💥 Crashed"
        if self.burst:
            return "🎈 Burst"
        if self.landed:
            return "✅ Landed"
        return "🔄 In flight"

    def to_embed_fields(self) -> List[Tuple[str, str]]:
        """Convert result to Discord embed fields.

        Returns a list of (name, value) pairs suitable for a Discord embed.
        """
        fields: List[Tuple[str, str]] = []

        # Flight outcome
        state = self.end_state()
        fields.append(("Flight Result", f"{state}"))

        # Peak altitude
        fields.append(("Peak Altitude", f"{self.peak_altitude_label}"))

        # Duration
        fields.append(("Flight Time", self.flight_time_label))

        # Final state
        if self.telemetry:
            fields.append(("Final Altitude", f"{self.final_altitude_m:.0f} m"))
            fields.append(("Final Gas", f"{self.final_gas_mass_kg:.2f} kg"))

        return fields


# ═══════════════════════════════════════════════════════════
# Backward-compatibility shims
# ═══════════════════════════════════════════════════════════


def build_launch_request_from_discord(
    gas_id: str,
    envelope_id: str,
    payload_ids: List[str],
    site_id: str,
    fill_mode: str,
    manual_mass: Optional[float] = None,
    player_id: Optional[str] = None,
) -> LaunchRequest:
    """Build a LaunchRequest from Discord interaction parameters.

    Discord sends fill mode as a string ("auto", "light", etc.),
    payloads as a list, and site as a string. This helper converts
    them into the typed LaunchRequest.
    """
    fill = FillMode(fill_mode)
    return LaunchRequest(
        gas_id=gas_id,
        envelope_id=envelope_id,
        payload_ids=tuple(payload_ids),
        launch_site_id=site_id,
        fill_mode=fill,
        manual_gas_mass_kg=manual_mass,
        player_id=player_id,
    )


def build_launch_request_from_cli(
    gas_id: str,
    envelope_id: str,
    payload_ids: List[str],
    site_id: str,
    fill_mode: str = "auto",
    manual_mass: Optional[float] = None,
) -> LaunchRequest:
    """Build a LaunchRequest from CLI parameters.

    Similar to the Discord helper but with defaults for interactive use.
    """
    fill = FillMode(fill_mode)
    return LaunchRequest(
        gas_id=gas_id,
        envelope_id=envelope_id,
        payload_ids=tuple(payload_ids),
        launch_site_id=site_id,
        fill_mode=fill,
        manual_gas_mass_kg=manual_mass,
    )


# ═══════════════════════════════════════════════════════════
# TelemetryPoint helper
# ═══════════════════════════════════════════════════════════


def telemetry_point_from_dict(d: dict) -> TelemetryPoint:
    """Convert a simulation_step() telemetry dict to a TelemetryPoint."""
    return TelemetryPoint(
        time_s=d["time_s"],
        altitude_m=d["altitude_m"],
        velocity_mps=d["velocity_mps"],
        gas_volume_m3=d["gas_volume_m3"],
        ambient_pressure_pa=d["ambient_pressure_pa"],
        ambient_temperature_k=d["ambient_temperature_k"],
        net_lift_N=d["net_lift_N"],
        buoyancy_N=d["buoyancy_N"],
        weight_N=d["weight_N"],
        drag_N=d["drag_N"],
        gas_mass_kg=d["gas_mass_kg"],
        total_mass_kg=d["total_mass_kg"],
        burst=d.get("burst", False),
        landed=d.get("landed", False),
        crashed=d.get("crashed", False),
        x_m=d.get("x_m", 0.0),
        vx_mps=d.get("vx_mps", 0.0),
    )


def telemetry_list_to_points(tel_list: List[dict]) -> List[TelemetryPoint]:
    """Convert a list of simulation dicts to TelemetryPoint objects."""
    return [telemetry_point_from_dict(d) for d in tel_list]