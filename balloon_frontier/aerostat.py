"""Unified lighter-than-air component properties.

This module deliberately separates *what a component is* from the equations that
fly it. Air, helium, hydrogen, methane, heaters, and envelope materials all feed
the same thermodynamic simulation; there is no special ``hot air`` vehicle mode.

Thermal and safety calculations are expressed as pure functions over immutable
component profiles. Catalog registration remains an initialization boundary for
the existing catalog API; flight preparation itself does not mutate caller-owned
configuration objects.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from balloon_frontier.catalog import (
    CATALOG,
    EnvelopeDefinition,
    GasDefinition,
    PayloadDefinition,
)
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
        """Return resistance after stretch using the shared thermal equation."""
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
        """Power reaching the gas after clamping efficiency to a physical range."""
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
    # Open-bottom lightweight envelope. Bulk exchange through the mouth is
    # handled by zero-pressure venting, so membrane permeation is not added too.
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
    # Approximate tea-light-scale heat release. This is a simulation input, not
    # a construction recommendation or a promise that the vehicle will fly.
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
    """Return material/system thermal properties for an envelope ID."""
    return ENVELOPE_THERMAL_PROFILES.get(
        envelope_id,
        _DEFAULT_ENVELOPE_THERMAL_PROFILE,
    )


def heat_source_power_watts(payload_ids: Iterable[str]) -> float:
    """Total heat coupled into the gas by selected heater payloads."""
    return sum(
        HEAT_SOURCE_PROFILES[pid].coupled_power_watts
        for pid in payload_ids
        if pid in HEAT_SOURCE_PROFILES
    )


def risk_tags_for_request(request) -> frozenset[str]:
    """Collect safety-relevant material/method tags without changing physics."""
    tags: set[str] = set(GAS_RISK_TAGS.get(request.gas_id, ()))
    tags.update(envelope_thermal_profile(request.envelope_id).risk_tags)
    for pid in request.payload_ids:
        profile = HEAT_SOURCE_PROFILES.get(pid)
        if profile is not None:
            tags.update(profile.risk_tags)
    return frozenset(tags)


def safety_notes_for_request(request) -> tuple[str, ...]:
    """Human-readable score/report notes for selected risk-bearing components."""
    return tuple(
        RISK_DESCRIPTIONS[tag]
        for tag in sorted(risk_tags_for_request(request))
        if tag in RISK_DESCRIPTIONS
    )


def configured_simulation_state(request, state):
    """Return a configured simulation-state copy for the selected components.

    This is intentionally a pure transformation. Neither ``state`` nor its
    nested envelope is modified, which keeps preparation deterministic and
    prevents configuration from leaking between simulations.
    """
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
        heater_power_watts=heat_source_power_watts(request.payload_ids),
        envelope=envelope,
    )


def register_aerostat_catalog_extensions() -> None:
    """Register foundational air/heater/envelope components once.

    The existing catalog is a process-wide registry, so this function is kept as
    an explicit initialization boundary. Domain calculations above remain pure.
    """
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
