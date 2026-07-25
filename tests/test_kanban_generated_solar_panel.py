import pytest

from balloon_frontier.kanban_generated.solar_panel import Battery, SolarPanel, altitude_factor, diurnal_factor


def test_diurnal_factor_midnight_zero():
    assert diurnal_factor(0.0) == 0.0


def test_diurnal_factor_noon_one():
    # noon in a 24h day
    assert diurnal_factor(43_200.0) == pytest.approx(1.0, rel=0, abs=1e-7)


def test_altitude_factor_monotonic():
    f0 = altitude_factor(0.0)
    f1 = altitude_factor(1_000.0)
    f2 = altitude_factor(10_000.0)
    assert f1 > f0
    assert f2 > f1


def test_recharge_zero_at_night():
    battery = Battery(capacity_wh=100.0, charge_wh=10.0)
    panel = SolarPanel(rated_power_w=500.0)

    added_wh = panel.recharge(
        battery=battery,
        altitude_m=1_000.0,
        time_of_day_s=0.0,
        dt_s=60.0,
    )

    assert added_wh == 0.0
    assert battery.charge_wh == 10.0


def test_recharge_never_exceeds_capacity():
    battery = Battery(capacity_wh=100.0, charge_wh=99.0)
    panel = SolarPanel(rated_power_w=2_000.0, panel_charge_efficiency=1.0)

    panel.recharge(
        battery=battery,
        altitude_m=5_000.0,
        time_of_day_s=43_200.0,  # noon
        dt_s=3_600.0,  # 1h
    )

    assert battery.charge_wh <= battery.capacity_wh


def test_recharge_scales_with_dt_when_not_saturating():
    battery1 = Battery(capacity_wh=1_000_000.0, charge_wh=0.0)
    battery2 = Battery(capacity_wh=1_000_000.0, charge_wh=0.0)
    panel = SolarPanel(rated_power_w=1_000.0, panel_charge_efficiency=1.0)

    added1 = panel.recharge(
        battery=battery1,
        altitude_m=0.0,
        time_of_day_s=43_200.0,  # noon
        dt_s=10.0,
    )
    added2 = panel.recharge(
        battery=battery2,
        altitude_m=0.0,
        time_of_day_s=43_200.0,  # noon
        dt_s=20.0,
    )

    assert added2 == pytest.approx(2.0 * added1, rel=1e-12, abs=1e-12)


def test_recharge_adds_zero_when_battery_full():
    battery = Battery(capacity_wh=100.0, charge_wh=100.0)
    panel = SolarPanel(rated_power_w=500.0)

    added_wh = panel.recharge(
        battery=battery,
        altitude_m=1_000.0,
        time_of_day_s=43_200.0,
        dt_s=60.0,
    )

    assert added_wh == 0.0
    assert battery.charge_wh == 100.0
