"""Catalog additions used by the introductory balloon-assisted flight."""

from __future__ import annotations

from types import MethodType

from balloon_frontier.catalog import CATALOG, PayloadDefinition


QUADCOPTER_ID = "quadcopter"
QUADCOPTER = PayloadDefinition(
    id=QUADCOPTER_ID,
    name="Small Quadcopter",
    mass_kg=0.25,
    cost=250,
    capabilities=("powered_flight", "radio_control"),
)


def ensure_tutorial_catalog() -> None:
    """Teach the shared catalog to resolve the tutorial aircraft by ID.

    The quadcopter is a vehicle used by this introductory mission rather than a
    member of the existing generic payload enumeration. Keeping it as an explicit
    lookup extension avoids silently changing every payload list and compatibility
    dictionary in the game.
    """

    if getattr(CATALOG, "_tutorial_quadcopter_installed", False):
        return

    original_payload = CATALOG.payload

    def payload_with_tutorial_component(self, id_or_name: str):
        if id_or_name == QUADCOPTER_ID or id_or_name.lower() == QUADCOPTER.name.lower():
            return QUADCOPTER
        return original_payload(id_or_name)

    CATALOG.payload = MethodType(payload_with_tutorial_component, CATALOG)
    CATALOG._tutorial_quadcopter_installed = True


def ensure_discord_tutorial_options() -> None:
    """Expose the quadcopter in the existing menu data without a second UI."""

    ensure_tutorial_catalog()
    from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS

    PAYLOAD_OPTIONS.setdefault(
        QUADCOPTER_ID,
        (QUADCOPTER.name, QUADCOPTER.mass_kg, QUADCOPTER.cost, QUADCOPTER.has_valve),
    )


ensure_tutorial_catalog()
