"""Catalog additions used by the introductory balloon-assisted flight."""

from __future__ import annotations

from dataclasses import replace
from types import MethodType

from balloon_frontier.catalog import CATALOG, EnvelopeDefinition, PayloadDefinition


QUADCOPTER_ID = "quadcopter"
TUTORIAL_ENVELOPE_ID = "tutorial_party_balloon"
SCIENTIFIC_FILM_BALLOON_NAME = "Scientific Film Balloon"

TUTORIAL_ASSIST_ENVELOPE = EnvelopeDefinition(
    id=TUTORIAL_ENVELOPE_ID,
    name="Foil Party Balloon",
    max_volume_m3=0.30,
    mass_kg=0.05,
    drag_coefficient=2.0,
    burst_stretch_ratio=3.0,
    contained_gas=True,
    cost=500,
    safe_fill_fraction=0.55,
)

# Active steering is independent from pressure management. The shared catalog's
# ``valve`` payload supplies venting only when the player pays its mass and cost.
QUADCOPTER = PayloadDefinition(
    id=QUADCOPTER_ID,
    name="Small Quadcopter",
    mass_kg=0.25,
    cost=250,
    has_valve=False,
    capabilities=("powered_flight", "radio_control"),
)


def ensure_tutorial_catalog() -> None:
    """Register tutorial-only components and clarify the shared film envelope."""
    if getattr(CATALOG, "_tutorial_components_installed", False):
        return

    # Preserve the legacy ``mylar`` ID for saves and requests, but give the
    # 200 m³ envelope a name appropriate to a large scientific film balloon.
    shared_mylar = CATALOG._envelopes.get("mylar")
    if shared_mylar is not None and shared_mylar.name != SCIENTIFIC_FILM_BALLOON_NAME:
        CATALOG._envelopes["mylar"] = replace(
            shared_mylar,
            name=SCIENTIFIC_FILM_BALLOON_NAME,
        )

    original_payload = CATALOG.payload
    original_envelope = CATALOG.envelope

    def payload_with_tutorial_component(self, id_or_name: str):
        if id_or_name == QUADCOPTER_ID or id_or_name.lower() == QUADCOPTER.name.lower():
            return QUADCOPTER
        return original_payload(id_or_name)

    def envelope_with_tutorial_component(self, id_or_name: str):
        if (
            id_or_name == TUTORIAL_ENVELOPE_ID
            or id_or_name.lower() == TUTORIAL_ASSIST_ENVELOPE.name.lower()
        ):
            return TUTORIAL_ASSIST_ENVELOPE
        return original_envelope(id_or_name)

    CATALOG.payload = MethodType(payload_with_tutorial_component, CATALOG)
    CATALOG.envelope = MethodType(envelope_with_tutorial_component, CATALOG)
    CATALOG._tutorial_components_installed = True


def ensure_discord_tutorial_options() -> None:
    """Expose tutorial equipment and keep the shared envelope label unambiguous."""
    ensure_tutorial_catalog()
    from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS, PAYLOAD_OPTIONS

    shared = ENVELOPE_OPTIONS.get("mylar")
    if shared is not None:
        ENVELOPE_OPTIONS["mylar"] = (SCIENTIFIC_FILM_BALLOON_NAME, *shared[1:])

    PAYLOAD_OPTIONS.setdefault(
        QUADCOPTER_ID,
        (QUADCOPTER.name, QUADCOPTER.mass_kg, QUADCOPTER.cost, QUADCOPTER.has_valve),
    )

    # The pressure valve is shared equipment, not part of the quadcopter. Make
    # it independently selectable in both explicit Tutorial mode and the hidden
    # Story prologue. The green recommendation remains the quadcopter alone, so
    # the player can compare the valve's added mass and cost deliberately.
    from balloon_frontier import tutorial

    tutorial.TUTORIAL_OPTION_KEYS[3] = (QUADCOPTER_ID, "valve", "none")


ensure_tutorial_catalog()
