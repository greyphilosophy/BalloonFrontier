"""Coverage for powered-assist and semantic lift-target fill calculations."""

import pytest

from balloon_frontier.physics import G
from balloon_frontier.power import (
    ALMOST_LIGHTER_THAN_AIR_SUPPORT_FRACTION,
    LIGHTER_THAN_AIR_SUPPORT_FRACTION,
    gas_mass_for_supported_fraction_kg,
    maximum_capacity_gas_mass_kg,
    powered_assist_gas_mass_kg,
)


def test_lift_target_fill_offsets_requested_fraction_of_aircraft_weight():
    gas_density = 0.169
    ambient_density = 1.225
    non_gas_mass = 5.75

    for support_fraction in (
        ALMOST_LIGHTER_THAN_AIR_SUPPORT_FRACTION,
        LIGHTER_THAN_AIR_SUPPORT_FRACTION,
    ):
        gas_mass = gas_mass_for_supported_fraction_kg(
            non_gas_mass_kg=non_gas_mass,
            ambient_density_kg_m3=ambient_density,
            lifting_gas_density_kg_m3=gas_density,
            max_volume_m3=10.0,
            support_fraction=support_fraction,
        )
        volume_m3 = gas_mass / gas_density
        supported_mass = (ambient_density - gas_density) * volume_m3

        assert 0.0 < gas_mass < gas_density * 10.0
        assert supported_mass / non_gas_mass == pytest.approx(support_fraction)


def test_lift_target_fill_rejects_impossible_or_invalid_targets():
    with pytest.raises(ValueError, match="negative"):
        gas_mass_for_supported_fraction_kg(
            non_gas_mass_kg=5.0,
            ambient_density_kg_m3=1.225,
            lifting_gas_density_kg_m3=0.169,
            max_volume_m3=10.0,
            support_fraction=-0.1,
        )
    with pytest.raises(ValueError, match="lighter than ambient"):
        gas_mass_for_supported_fraction_kg(
            non_gas_mass_kg=5.0,
            ambient_density_kg_m3=1.2,
            lifting_gas_density_kg_m3=1.2,
            max_volume_m3=10.0,
            support_fraction=0.95,
        )
    with pytest.raises(ValueError, match="lighter than ambient"):
        gas_mass_for_supported_fraction_kg(
            non_gas_mass_kg=5.0,
            ambient_density_kg_m3=1.2,
            lifting_gas_density_kg_m3=0.0,
            max_volume_m3=10.0,
            support_fraction=0.95,
        )
    with pytest.raises(ValueError, match="cannot reach"):
        gas_mass_for_supported_fraction_kg(
            non_gas_mass_kg=5.0,
            ambient_density_kg_m3=1.225,
            lifting_gas_density_kg_m3=0.169,
            max_volume_m3=0.1,
            support_fraction=0.95,
        )


def test_maximum_capacity_fill_uses_full_nominal_volume():
    assert maximum_capacity_gas_mass_kg(
        lifting_gas_density_kg_m3=0.169,
        max_volume_m3=10.0,
    ) == pytest.approx(1.69)
    assert maximum_capacity_gas_mass_kg(
        lifting_gas_density_kg_m3=-1.0,
        max_volume_m3=-10.0,
    ) == 0.0


def test_assist_fill_leaves_requested_vertical_work_for_propulsion():
    gas_density = 0.169
    ambient_density = 1.225
    non_gas_mass = 5.75
    gas_mass = powered_assist_gas_mass_kg(
        non_gas_mass_kg=non_gas_mass,
        ambient_density_kg_m3=ambient_density,
        lifting_gas_density_kg_m3=gas_density,
        max_volume_m3=10.0,
        target_control_force_N=4.0,
    )

    volume_m3 = gas_mass / gas_density
    passive_balance_N = (
        ambient_density * volume_m3 * G
        - (non_gas_mass + gas_mass) * G
    )

    assert 0.0 < gas_mass < gas_density * 10.0
    assert passive_balance_N == pytest.approx(-4.0)


def test_assist_fill_rejects_gases_without_buoyant_margin():
    with pytest.raises(ValueError):
        powered_assist_gas_mass_kg(
            non_gas_mass_kg=5.0,
            ambient_density_kg_m3=1.2,
            lifting_gas_density_kg_m3=1.2,
            max_volume_m3=10.0,
        )
    with pytest.raises(ValueError):
        powered_assist_gas_mass_kg(
            non_gas_mass_kg=5.0,
            ambient_density_kg_m3=1.2,
            lifting_gas_density_kg_m3=0.0,
            max_volume_m3=10.0,
        )


def test_assist_fill_respects_nominal_volume_and_zero_floor():
    capped = powered_assist_gas_mass_kg(
        non_gas_mass_kg=100.0,
        ambient_density_kg_m3=1.225,
        lifting_gas_density_kg_m3=0.169,
        max_volume_m3=1.0,
    )
    assert capped == pytest.approx(0.169)

    zero = powered_assist_gas_mass_kg(
        non_gas_mass_kg=0.1,
        ambient_density_kg_m3=1.225,
        lifting_gas_density_kg_m3=0.169,
        max_volume_m3=-1.0,
        target_control_force_N=100.0,
    )
    assert zero == 0.0
