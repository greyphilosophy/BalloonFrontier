"""Deprecated compatibility definitions from the removed Tutorial mode.

These names remain importable temporarily for older callers, but importing this
module no longer mutates the central catalog or Discord configuration options.
Story onboarding uses only ordinary catalog equipment.
"""

from __future__ import annotations

from balloon_frontier.catalog import EnvelopeDefinition, PayloadDefinition


QUADCOPTER_ID = "quadcopter"
TUTORIAL_ENVELOPE_ID = "tutorial_party_balloon"
SCIENTIFIC_FILM_BALLOON_NAME = "Scientific Film Balloon"

# Legacy objects are retained only so older imports fail softly. They are not
# registered in CATALOG and are not selectable by the current game.
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

QUADCOPTER = PayloadDefinition(
    id=QUADCOPTER_ID,
    name="Small Quadcopter",
    mass_kg=0.25,
    cost=250,
    has_valve=False,
    capabilities=("powered_flight", "radio_control", "camera"),
)


def ensure_tutorial_catalog() -> None:
    """Deprecated no-op retained for source compatibility."""
    return None


def ensure_discord_tutorial_options() -> None:
    """Deprecated no-op retained for source compatibility."""
    return None
