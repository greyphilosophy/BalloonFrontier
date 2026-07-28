"""Catalog additions used by the introductory balloon-assisted flight."""

from __future__ import annotations

from types import MethodType

from balloon_frontier.catalog import CATALOG, EnvelopeDefinition, PayloadDefinition


QUADCOPTER_ID = "quadcopter"
TUTORIAL_ENVELOPE_ID = "tutorial_mylar_assist"

TUTORIAL_ASSIST_ENVELOPE = EnvelopeDefinition(
    id=TUTORIAL_ENVELOPE_ID,
    name="Mylar Assist Balloon",
    max_volume_m3=0.30,
    mass_kg=0.05,
    drag_coefficient=2.0,
    burst_stretch_ratio=3.0,
    contained_gas=True,
    cost=500,
    safe_fill_fraction=0.55,
)

QUADCOPTER = PayloadDefinition(
    id=QUADCOPTER_ID,
    name="Small Quadcopter",
    mass_kg=0.25,
    cost=250,
    has_valve=True,
    capabilities=("powered_flight", "radio_control", "automatic_venting"),
)


def ensure_tutorial_catalog() -> None:
    """Register tutorial-only component IDs without replacing shared equipment."""
    if getattr(CATALOG, "_tutorial_components_installed", False):
        return

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
    """Expose only the shared quadcopter option; the envelope stays tutorial-local."""
    ensure_tutorial_catalog()
    from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS

    PAYLOAD_OPTIONS.setdefault(
        QUADCOPTER_ID,
        (QUADCOPTER.name, QUADCOPTER.mass_kg, QUADCOPTER.cost, QUADCOPTER.has_valve),
    )


ensure_tutorial_catalog()
