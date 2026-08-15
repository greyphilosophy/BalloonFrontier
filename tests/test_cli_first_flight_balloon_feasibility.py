"""First Flight should offer only balloon sizes that can carry the starter aircraft."""

import pytest

import cli_game
from balloon_frontier.career_prologue import (
    FIRST_FLIGHT_PROVIDED_PAYLOADS,
    first_flight_balloon_choices,
)


def _almost_lta_mass(balloon_size: str) -> float:
    return cli_game._first_flight_fill_mass(
        gas_id="helium",
        envelope_id="latex",
        balloon_size=balloon_size,
        payload_ids=FIRST_FLIGHT_PROVIDED_PAYLOADS,
        site_id="field",
        fill_key="almost_lta",
    )


def test_every_offered_helium_balloon_can_support_the_starter_aircraft():
    offered = first_flight_balloon_choices("helium")

    assert tuple(choice.balloon_size for choice in offered) == ("s45", "s55", "s70")
    for choice in offered:
        assert _almost_lta_mass(choice.balloon_size) > 0.0


def test_smaller_s36_is_omitted_because_the_same_lift_target_is_infeasible():
    with pytest.raises(ValueError):
        _almost_lta_mass("s36")
