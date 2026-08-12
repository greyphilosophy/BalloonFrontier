"""Unified lighter-than-air component properties.

This module deliberately separates *what a component is* from the equations that
fly it. Air, helium, hydrogen, methane, heaters, and envelope materials all feed
the same thermodynamic simulation; there is no special ``hot air`` vehicle mode.

Thermal, fill, and safety calculations are expressed as pure functions over
immutable component profiles. Catalog registration remains an initialization
boundary for the existing catalog API; flight preparation itself does not mutate
caller-owned configuration objects.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from balloon_frontier.catalog import (
    CATALOG,
    EnvelopeDefinition,
    FillMode,
    GasDefinition,
    PayloadDefinition,
)
from balloon_frontier.fill import apply_fill_mode
from balloon_frontier.physics import atmosphere_pressure, atmosphere_temperature
from balloon_frontier.thermal import effective_thermal_resistance


AIR_MOLAR_MASS_KG_PER_MOL = 0.0289652068


@dataclass(frozen=True, slots=True)
class EnvelopeThermalProfile:
    """Thermal behavior of an envelope material/system."""

    thermal_resistance_m2_k_w: float
    inflation_heat_loss_exponent: float = 0.0
    stretch_start_fraction: float = 1.0
    absorptivity: float = 0.5
    emissivity: float = 0.8
    max_temperature_k: float = 450.0
    permeability_per_s: float | None = None
    risk_tags: tuple[str, ...] = ()

    def effective_resistance(self, inflation_fraction: float) -> float:
        return effective_thermal_resistance(
            self.thermal_resistance_m2_k_w,
            inflation_fraction,
            self.inflation_heat_loss_exponent,
            self.stretch_start_fraction,
        )


@dataclass(frozen=True, slots=True)
class HeatSourceProfile:
    """A payload that contributes thermal power to the contained gas."""

    power_watts: float
    coupling_efficiency: float = 1.0
    risk_tags: tuple[str, ...] = ()

    @property
    def coupled_power_watts(self) -> float:
        return max(0.0, self.power_watts) * min(
            1.0,
            max(0.0, self.coupling_efficiency),
        )


ENVELOPE_THERMAL_PROFILES: dict[str, EnvelopeThermalProfile] = {
    "latex": EnvelopeThermalProfile(
        thermal_resistance_m2_k_w=1.20,
        inflation_heat_loss_exponent=0.75,
        stretch_start_fraction=0.65,
        absorptivity=0.55,
        emissivity=0.86,
        max_temperature_k=360.0,
    ),
    "mylar": EnvelopeThermalProfile(
        thermal_resistance_m2_k_w=1.65,
        inflation_heat_loss_exponent=0.15,
        stretch_start_fraction=0.90,
        absorptivity=0.25,
        emissivity=0.30,
        max_temperature_k=420.0,
    ),
    "zero_pressure": EnvelopeThermalProfile(
        thermal_resistance_m2_k_w=1.00,
        inflation_heat_loss_exponent=0.10,
        stretch_start_fraction=0.95,
        absorptivity=0.50,
        emissivity=0.78,
        max_temperature_k=365.0,
    ),
    "blimp": EnvelopeThermalProfile(
        thermal_resistance_m2_k_w=2.20,
        inflation_heat_loss_exponent=0.05,
        stretch_start_fraction=0.95,
        absorptivity=0.45,
        emissivity=0.70,
        max_temperature_k=390.0,
    ),
    "candle_kite": EnvelopeThermalProfile(
        thermal_resistance_m2_k_w=0.85,
        inflation_heat_loss_exponent=0.05,
        stretch_start_fraction=0.95,
        absorptivity=0.45,
        emissivity=0.72,
        max_temperature_k=430.0,
        permeability_per_s=0.0,
        risk_tags=("heat_sensitive_envelope",),
    ),
}


HEAT_SOURCE_PROFILES: dict[str, HeatSourceProfile] = {
    "heater": HeatSourceProfile(
        power_watts=600.0,
        coupling_efficiency=0.90,
        risk_tags=("high_temperature_heat_source",),
    ),
    "candle_heater": HeatSourceProfile(
        power_watts=80.0,
        coupling_efficiency=0.72,
        risk_tags=("open_flame",),
    ),
    "electric_heater": HeatSourceProfile(
        power_watts=80.0,
        coupling_efficiency=0.88,
        risk_tags=("high_temperature_heat_source",),
    ),
}


GAS_RISK_TAGS: dict[str, tuple[str, ...]] = {
    "hydrogen": ("flammable_lifting_gas",),
    "methane": ("flammable_lifting_gas",),
}


RISK_DESCRIPTIONS: dict[str, str] = {
    "flammable_lifting_gas": (
        "Flammable lifting gas: ignition control and separation from heat sources matter."
    ),
    "open_flame": (
        "Open flame heat source: fire and ignition risk must be controlled for the operating environment."
    ),
    "high_temperature_heat_source": (
        "High-temperature heat source: envelope temperature and electrical/thermal protection matter."
    ),
    "heat_sensitive_envelope": (
        "Lightweight heated envelope: very low mass comes with limited thermal margin."
    ),
}


_DEFAULT_ENVELOPE_THERMAL_PROFILE = EnvelopeThermalProfile(
    thermal_resistance_m2_k_w=1.0
)


def envelope_thermal_profile(envelope_id: str) -> EnvelopeThermalProfile:
    return ENVELOPE_THERMAL_PROFILES.get(
        envelope_id,
        _DEFAULT_ENVELOPE_THERMAL_PROFILE,
    )


def heat_source_power_watts(payload_ids: Iterable[str]) -> float:
    return sum(
        HEAT_SOURCE_PROFILES[pid].coupled_power_watts
        for pid in payload_ids
        if pid in HEAT_SOURCE_PROFILES
    )


def fill_mass_for_configuration(
    *,
    gas_id: str,
    envelope_id: str,
    launch_site_id: str,
    fill_mode: FillMode,
    manual_gas_mass_kg: float | None = None,
    balloon_size: str | None = None,
    gas_temperature_delta_k: float | None = None,
) -> float:
    """Resolve gas mass through the shared fill equations for any UI/service."""
    envelope = CATALOG.envelope(envelope_id)
    balloon = CATALOG.balloon(balloon_size) if balloon_size else None
    site = CATALOG.site(launch_site_id)

    volume_m3 = balloon.max_volume_m3 if balloon else envelope.max_volume_m3
    burst_ratio = (
        balloon.burst_stretch_ratio if balloon else envelope.burst_stretch_ratio
    )
    launch_pressure = atmosphere_pressure(site.altitude_m)
    launch_temperature = (
        site.gas_temperature_k
        if site.gas_temperature_k is not None
        else atmosphere_temperature(site.altitude_m) + site.temperature_offset_k
    )
    if gas_temperature_delta_k is not None:
        launch_temperature += gas_temperature_delta_k

    return apply_fill_mode(
        volume_m3,
        gas_id,
        fill_mode,
        manual_mass_kg=manual_gas_mass_kg,
        burst_stretch_ratio=burst_ratio,
        envelope_type=envelope.id,
        launch_altitude=site.altitude_m,
        launch_pressure=launch_pressure,
        gas_temperature=launch_temperature,
        safe_fill_data={
            "burst_stretch_ratio": burst_ratio,
            "safe_fill_fraction": envelope.safe_fill_fraction,
        },
    )


def resolved_gas_mass_kg(request) -> float:
    """Pure adapter from an immutable LaunchRequest to the shared fill function."""
    return fill_mass_for_configuration(
        gas_id=request.gas_id,
        envelope_id=request.envelope_id,
        launch_site_id=request.launch_site_id,
        fill_mode=request.fill_mode,
        manual_gas_mass_kg=request.manual_gas_mass_kg,
        balloon_size=request.balloon_size,
        gas_temperature_delta_k=request.gas_temperature_delta_k,
    )


def risk_tags_for_request(request) -> frozenset[str]:
    tags: set[str] = set(GAS_RISK_TAGS.get(request.gas_id, ()))
    tags.update(envelope_thermal_profile(request.envelope_id).risk_tags)
    for pid in request.payload_ids:
        profile = HEAT_SOURCE_PROFILES.get(pid)
        if profile is not None:
            tags.update(profile.risk_tags)
    return frozenset(tags)


def safety_notes_for_request(request) -> tuple[str, ...]:
    return tuple(
        RISK_DESCRIPTIONS[tag]
        for tag in sorted(risk_tags_for_request(request))
        if tag in RISK_DESCRIPTIONS
    )


def configured_simulation_state(request, state):
    """Return a configured simulation-state copy without mutating the input."""
    profile = envelope_thermal_profile(request.envelope_id)
    envelope = replace(
        state.envelope,
        thermal_resistance_m2_k_w=profile.thermal_resistance_m2_k_w,
        inflation_heat_loss_exponent=profile.inflation_heat_loss_exponent,
        stretch_start_fraction=profile.stretch_start_fraction,
        envelope_absorptivity=profile.absorptivity,
        envelope_emissivity=profile.emissivity,
        max_temperature_k=profile.max_temperature_k,
        permeability=(
            profile.permeability_per_s
            if profile.permeability_per_s is not None
            else state.envelope.permeability
        ),
    )
    return replace(
        state,
        gas_mass_kg=resolved_gas_mass_kg(request),
        heater_power_watts=heat_source_power_watts(request.payload_ids),
        envelope=envelope,
    )


def register_aerostat_catalog_extensions() -> None:
    """Register foundational components at the existing registry boundary."""
    if "air" not in CATALOG._gases:
        CATALOG._register(
            GasDefinition("air", "Air", AIR_MOLAR_MASS_KG_PER_MOL, 0, "neutral")
        )
    if "candle_kite" not in CATALOG._envelopes:
        CATALOG._register(
            EnvelopeDefinition(
                id="candle_kite",
                name="Lightweight Hot-Air Envelope",
                max_volume_m3=0.20,
                mass_kg=0.018,
                drag_coefficient=1.45,
                burst_stretch_ratio=1.05,
                contained_gas=False,
                cost=5,
                safe_fill_fraction=0.95,
            )
        )
    if "candle_heater" not in CATALOG._payloads:
        CATALOG._register(
            PayloadDefinition(
                "candle_heater",
                "Tea Light Heat Source",
                0.015,
                1,
                False,
                capabilities=("heating",),
            )
        )
    if "electric_heater" not in CATALOG._payloads:
        CATALOG._register(
            PayloadDefinition(
                "electric_heater",
                "Small Electric Heater",
                0.080,
                20,
                False,
                capabilities=("heating",),
            )
        )
