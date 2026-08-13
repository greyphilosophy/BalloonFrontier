"""Coverage for the powered-assist fill calculation."""

import pytest

from balloon_frontier.physics import G
from balloon_frontier.power import powered_assist_gas_mass_kg


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
