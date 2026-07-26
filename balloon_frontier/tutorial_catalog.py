"""Catalog additions used by the introductory balloon-assisted flight."""

from __future__ import annotations

from balloon_frontier.catalog import CATALOG, PayloadDefinition


QUADCOPTER_ID = "quadcopter"


def ensure_tutorial_catalog() -> None:
    """Register the small off-the-shelf quadcopter once."""

    try:
        CATALOG.payload(QUADCOPTER_ID)
        return
    except KeyError:
        pass

    CATALOG._register(  # Central catalog's internal builder API.
        PayloadDefinition(
            id=QUADCOPTER_ID,
            name="Small Quadcopter",
            mass_kg=0.25,
            cost=250,
            capabilities=("powered_flight", "radio_control"),
        )
    )


def ensure_discord_tutorial_options() -> None:
    """Expose the quadcopter in the existing menu data without a second UI."""

    ensure_tutorial_catalog()
    from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS

    PAYLOAD_OPTIONS.setdefault(
        QUADCOPTER_ID,
        ("Small Quadcopter", 0.25, 250, False),
    )


ensure_tutorial_catalog()
