"""Catalog additions used by the introductory balloon-assisted flight."""

from __future__ import annotations

from balloon_frontier.catalog import CATALOG, PayloadDefinition


QUADCOPTER_ID = "quadcopter"
QUADCOPTER_NAME = "Small Quadcopter"
QUADCOPTER_MASS_KG = 0.25
QUADCOPTER_COST = 250


def ensure_tutorial_catalog() -> None:
    """Register the small off-the-shelf quadcopter and refresh compatibility views."""

    try:
        payload = CATALOG.payload(QUADCOPTER_ID)
    except KeyError:
        payload = PayloadDefinition(
            id=QUADCOPTER_ID,
            name=QUADCOPTER_NAME,
            mass_kg=QUADCOPTER_MASS_KG,
            cost=QUADCOPTER_COST,
            capabilities=("powered_flight", "radio_control"),
        )
        CATALOG._register(payload)  # Central catalog's internal builder API.

    # These dictionaries are materialized when catalog.py is imported. Keep them
    # synchronized when a tutorial component is registered afterward.
    from balloon_frontier import catalog as catalog_module

    catalog_module.PAYLOADS.setdefault(
        QUADCOPTER_ID,
        (payload.name, payload.mass_kg, payload.has_valve),
    )
    catalog_module.DISCORD_PAYLOAD_OPTIONS.setdefault(
        QUADCOPTER_ID,
        (payload.name, payload.mass_kg, payload.cost, payload.has_valve),
    )


def ensure_discord_tutorial_options() -> None:
    """Expose the quadcopter in the existing menu data without a second UI."""

    ensure_tutorial_catalog()
    from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS

    PAYLOAD_OPTIONS.setdefault(
        QUADCOPTER_ID,
        (QUADCOPTER_NAME, QUADCOPTER_MASS_KG, QUADCOPTER_COST, False),
    )


ensure_tutorial_catalog()
