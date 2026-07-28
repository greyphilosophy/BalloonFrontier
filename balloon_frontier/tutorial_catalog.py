"""Catalog additions used by the introductory balloon-assisted flight."""

from __future__ import annotations

from types import MethodType

from balloon_frontier.catalog import (
    CATALOG,
    EnvelopeDefinition,
    PayloadDefinition,
)


QUADCOPTER_ID = "quadcopter"
TUTORIAL_ENVELOPE_ID = "mylar"

# This is a small buoyancy-assist balloon, not the 200 m³ envelope that was
# previously attached to a 250 g quadcopter.  At 0.30 m³ it offsets roughly
# the aircraft's weight while leaving the rotors responsible for control.
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

# The introductory aircraft includes an automatic pressure-relief valve.
# This keeps the tutorial focused on lift and control choices instead of
# allowing a beginner's first flight to end in an envelope burst.
QUADCOPTER = PayloadDefinition(
    id=QUADCOPTER_ID,
    name="Small Quadcopter",
    mass_kg=0.25,
    cost=250,
    has_valve=True,
    capabilities=("powered_flight", "radio_control", "automatic_venting"),
)


def ensure_tutorial_catalog() -> None:
    """Teach the shared catalog to resolve the tutorial aircraft and envelope."""

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
    """Expose tutorial-specific aircraft and envelope data in the existing UI."""

    ensure_tutorial_catalog()
    from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS, PAYLOAD_OPTIONS

    ENVELOPE_OPTIONS[TUTORIAL_ENVELOPE_ID] = (
        TUTORIAL_ASSIST_ENVELOPE.name,
        TUTORIAL_ASSIST_ENVELOPE.max_volume_m3,
        TUTORIAL_ASSIST_ENVELOPE.mass_kg,
        TUTORIAL_ASSIST_ENVELOPE.drag_coefficient,
        TUTORIAL_ASSIST_ENVELOPE.burst_stretch_ratio,
        TUTORIAL_ASSIST_ENVELOPE.cost,
    )
    PAYLOAD_OPTIONS[QUADCOPTER_ID] = (
        QUADCOPTER.name,
        QUADCOPTER.mass_kg,
        QUADCOPTER.cost,
        QUADCOPTER.has_valve,
    )


ensure_tutorial_catalog()
