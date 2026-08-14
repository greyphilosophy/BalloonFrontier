"""Pure finite-energy and powered-flight control calculations."""

import pytest

from balloon_frontier.power import (
    BATTERY_PACK_CAPACITY_WH,
    PowerConfiguration,
    battery_energy_after_step,
    battery_fraction,
    motor_power_w,
    power_configuration_for_payloads,
    powered_flight_target_altitude_m,
    vertical_control_force_N,
)


def test_battery_pack_creates_finite_energy_store_and_shared_loads():
    config = power_configuration_for_payloads(
        ("camera", "quadcopter", "battery", "electric_heater")
    )

    assert config.battery_capacity_wh == BATTERY_PACK_CAPACITY_WH
    assert config.has_battery is True
    assert config.has_quadcopter is True
    assert config.has_electrical_consumers is True
    assert config.constant_load_w == pytest.approx(11.0)
    assert config.electrical_heater_input_w == pytest.approx(80.0)
    assert config.electrical_heater_coupled_w == pytest.approx(70.4)
    assert config.max_horizontal_force_N == pytest.approx(2.5)
    assert config.max_vertical_force_N > 0.0


def test_multiple_battery_packs_add_capacity_and_candle_heat_is_not_electrical():
    config = power_configuration_for_payloads(
        ("battery", "battery", "candle_heater")
    )

    assert config.battery_capacity_wh == 2 * BATTERY_PACK_CAPACITY_WH
    assert config.electrical_heater_input_w == 0.0
    assert config.non_electrical_heater_coupled_w == pytest.approx(57.6)
    assert config.has_quadcopter is False


def test_empty_configuration_has_no_power_system():
    config = power_configuration_for_payloads(("none",))

    assert config == PowerConfiguration()
    assert config.has_battery is False
    assert config.has_quadcopter is False
    assert config.has_electrical_consumers is False


def test_motor_power_tracks_resultant_control_load():
    assert motor_power_w(0.0, 0.0) == 0.0
    assert motor_power_w(3.0, 4.0) == pytest.approx(175.0)
    assert motor_power_w(-3.0, 4.0) == pytest.approx(140.0)


def test_battery_energy_depletes_in_watt_hours_and_clamps():
    assert battery_energy_after_step(100.0, 360.0, 10.0) == pytest.approx(99.0)
    assert battery_energy_after_step(0.5, 3600.0, 1.0) == 0.0
    assert battery_energy_after_step(10.0, -5.0, 10.0) == 10.0
    assert battery_energy_after_step(10.0, 5.0, -1.0) == 10.0


def test_battery_fraction_is_clamped():
    assert battery_fraction(50.0, 100.0) == 0.5
    assert battery_fraction(150.0, 100.0) == 1.0
    assert battery_fraction(-1.0, 100.0) == 0.0
    assert battery_fraction(1.0, 0.0) == 0.0


def test_autonomous_target_changes_from_photo_altitude_to_ground():
    config = PowerConfiguration(cruise_altitude_m=30.0, return_time_s=20.0)

    assert powered_flight_target_altitude_m(
        time_s=19.9,
        ground_altitude_m=100.0,
        config=config,
    ) == 130.0
    assert powered_flight_target_altitude_m(
        time_s=20.0,
        ground_altitude_m=100.0,
        config=config,
    ) == 100.0


def test_vertical_controller_adds_upward_force_but_never_negative_force():
    climb = vertical_control_force_N(
        altitude_m=0.0,
        velocity_mps=0.0,
        target_altitude_m=30.0,
        passive_net_force_N=-5.0,
        total_mass_kg=2.0,
        max_vertical_force_N=18.0,
    )
    over_buoyant_return = vertical_control_force_N(
        altitude_m=30.0,
        velocity_mps=0.0,
        target_altitude_m=0.0,
        passive_net_force_N=5.0,
        total_mass_kg=2.0,
        max_vertical_force_N=18.0,
    )

    assert climb > 0.0
    assert climb <= 18.0
    assert over_buoyant_return == 0.0
    assert vertical_control_force_N(
        altitude_m=0.0,
        velocity_mps=0.0,
        target_altitude_m=30.0,
        passive_net_force_N=0.0,
        total_mass_kg=0.0,
        max_vertical_force_N=18.0,
    ) == 0.0
    assert vertical_control_force_N(
        altitude_m=0.0,
        velocity_mps=0.0,
        target_altitude_m=30.0,
        passive_net_force_N=0.0,
        total_mass_kg=2.0,
        max_vertical_force_N=0.0,
    ) == 0.0
