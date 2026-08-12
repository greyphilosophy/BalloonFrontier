"""Unified lighter-than-air component properties.

This module deliberately separates *what a component is* from the equations that
fly it.  Air, helium, hydrogen, methane, heaters, and envelope materials all feed
the same thermodynamic simulation; there is no special ``hot air`` vehicle mode.

The catalog extensions here are small Story-facing components.  The thermal and
risk profiles are kept separately so existing catalog dataclasses remain source
compatible while the world model grows toward richer material data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from balloon_frontier.catalog import (
    CATALOG,
    EnvelopeDefinition,
    GasDefinition,
    PayloadDefinition,
)


AIR_MOLAR_MASS_KG_PER_MOL = 0.0289652068


@dataclass(frozen=True, slots=True)
class EnvelopeThermalProfile:
    """Thermal behavior of an envelope material/system.

    ``thermal_resistance_m2_k_w`` is an effective through-envelope + boundary
    resistance used by the lumped model.  As an elastic envelope stretches its
    film gets thinner; ``inflation_heat_loss_exponent`` controls how quickly
    effective resistance falls once ``stretch_start_fraction`` is exceeded.
    """

    thermal_resistance_m2_k_w: float
    inflation_heat_loss_exponent: float = 0.0
    stretch_start_fraction: float = 1.0
    absorptivity: float = 0.5
    emissivity: float = 0.8
    max_temperature_k: float = 450.0
    risk_tags: tuple[str, ...] = ()

    def effective_resistance(self, inflation_fraction: float) -> float:
        fraction = max(0.0, float(inflation_fraction))
        start = max(1e-6, float(self.stretch_start_fraction))
        stretch = max(1.0, fraction / start)
        exponent = max(0.0, float(self.inflation_heat_loss_exponent))
        return max(
            1e-4,
            float(self.thermal_resistance_m2_k_w) / (stretch ** exponent),
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
    # Thin latex loses insulation as it stretches appreciably.
    "latex": EnvelopeThermalProfile(
        thermal_resistance_m2_k_w=1.20,
        inflation_heat_loss_exponent=0.75,
        stretch_start_fraction=0.65,
        absorptivity=0.55,
        emissivity=0.86,
        max_temperature_k=360.0,
    ),
    # Metallized film is a much better radiant barrier and stretches little.
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
    # A very light open-bottom envelope: cheap and thermally leaky, but capable
    # of turning modest heat input into a density deficit if mass stays low.
    "candle_kite": EnvelopeThermalProfile(
        thermal_resistance_m2_k_w=0.85,
        inflation_heat_loss_exponent=0.05,
        stretch_start_fraction=0.95,
        absorptivity=0.45,
        emissivity=0.72,
        max_temperature_k=430.0,
        risk_tags=("heat_sensitive_envelope",),
    ),
}


HEAT_SOURCE_PROFILES: dict[str, HeatSourceProfile] = {
    # Existing later-game heater becomes a real power source rather than a name.
    "heater": HeatSourceProfile(
        power_watts=600.0,
        coupling_efficiency=0.90,
        risk_tags=("high_temperature_heat_source",),
    ),
    # Approximate small tea-light-scale heat release.  It is intentionally a
    # model input, not a construction recommendation.
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


def envelope_thermal_profile(envelope_id: str) -> EnvelopeThermalProfile:
    """Return material/system thermal properties for an envelope ID."""

    return ENVELOPE_THERMAL_PROFILES.get(
        envelope_id,
        EnvelopeThermalProfile(thermal_resistance_m2_k_w=1.0),
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


def configure_simulation_state(request, state) -> None:
    """Apply request component properties to the shared simulation state.

    The simulation still performs the equations.  This function only supplies
    component data: heater watts and material thermal parameters.
    """

    profile = envelope_thermal_profile(request.envelope_id)
    state.heater_power_watts = heat_source_power_watts(request.payload_ids)
    state.envelope.thermal_resistance_m2_k_w = profile.thermal_resistance_m2_k_w
    state.envelope.inflation_heat_loss_exponent = profile.inflation_heat_loss_exponent
    state.envelope.stretch_start_fraction = profile.stretch_start_fraction
    state.envelope.envelope_absorptivity = profile.absorptivity
    state.envelope.envelope_emissivity = profile.emissivity
    state.envelope.max_temperature_k = profile.max_temperature_k


def register_aerostat_catalog_extensions() -> None:
    """Register foundational air/heater/envelope components once.

    ``_register`` is the catalog's existing centralized registration mechanism;
    using it here avoids duplicating lookup behavior while retaining the current
    catalog dataclass API.
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
