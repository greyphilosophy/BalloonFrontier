import pytest

from balloon_frontier.launch_sites import LaunchSiteInfo
from balloon_frontier.physics import atmosphere_pressure, atmosphere_temperature
from balloon_frontier.simulation import EnvelopeConfig, SimulationState, run_simulation


def _make_state(*, site: LaunchSiteInfo, gas_mass_kg: float = 5.0, payload_mass_kg: float = 5.0):
    env = EnvelopeConfig(
        max_volume_m3=500.0,
        burst_stretch_ratio=10.0,
        drag_coefficient=0.47,
        permeability=0.0,
        mass_kg=2.0,
        contained_gas=True,
    )
    return SimulationState(
        altitude_m=site.altitude_m,
        terrain_base_altitude_offset_m=site.altitude_m,
        gas_type="helium",
        gas_mass_kg=gas_mass_kg,
        gas_temperature_k=site.gas_temperature_at_launch(),
        payload_mass_kg=payload_mass_kg,
        ballast_mass_kg=0.0,
        envelope=env,
        # Keep thermal/leak changes tiny by using a very short sim in tests.
    )


def test_launch_site_altitude_and_temperature_affect_simulation():
    """Regression: launch-site-specific atmosphere inputs must affect simulation.

    We use a single-step run so the trajectory is deterministic and quick.
    """

    site_a = LaunchSiteInfo(name="A", altitude_m=0.0, gas_temperature_k=270.0)
    site_b = LaunchSiteInfo(name="B", altitude_m=2000.0, gas_temperature_k=305.0)

    tel_a = run_simulation(_make_state(site=site_a), dt=0.01, total_time_s=0.01, max_steps=1)
    tel_b = run_simulation(_make_state(site=site_b), dt=0.01, total_time_s=0.01, max_steps=1)

    assert len(tel_a) == 1
    assert len(tel_b) == 1

    # Atmospheric inputs (altitude → ambient T/P) must differ.
    assert abs(tel_a[0]["ambient_temperature_k"] - tel_b[0]["ambient_temperature_k"]) > 0.5
    assert abs(tel_a[0]["ambient_pressure_pa"] - tel_b[0]["ambient_pressure_pa"]) > 10.0

    # Lifting gas temperature + pressure should change buoyancy / volume.
    assert abs(tel_a[0]["gas_volume_m3"] - tel_b[0]["gas_volume_m3"]) > 0.1

    # Sanity: derived ambient values at launch should match the physics model order of magnitude.
    assert atmosphere_temperature(site_a.altitude_m) > atmosphere_temperature(site_b.altitude_m)
    assert atmosphere_pressure(site_a.altitude_m) > atmosphere_pressure(site_b.altitude_m)


def test_launch_site_defaulting_when_gas_temperature_k_missing():
    """Regression/backward-compatibility: if gas_temperature_k is omitted,
    LaunchSiteInfo must derive it from atmosphere_temperature + temperature_offset_k.

    The simulation should match the explicit derived value.
    """

    site_offset = LaunchSiteInfo(
        name="Offset",
        altitude_m=0.0,
        gas_temperature_k=None,
        temperature_offset_k=10.0,
    )
    derived_temp = site_offset.gas_temperature_at_launch()

    site_explicit = LaunchSiteInfo(
        name="Explicit",
        altitude_m=0.0,
        gas_temperature_k=derived_temp,
        temperature_offset_k=0.0,
    )

    tel_offset = run_simulation(_make_state(site=site_offset), dt=0.01, total_time_s=0.01, max_steps=1)
    tel_explicit = run_simulation(_make_state(site=site_explicit), dt=0.01, total_time_s=0.01, max_steps=1)

    assert len(tel_offset) == 1
    assert len(tel_explicit) == 1

    assert tel_offset[0]["ambient_temperature_k"] == pytest.approx(
        tel_explicit[0]["ambient_temperature_k"],
        rel=1e-9,
        abs=1e-9,
    )
    assert tel_offset[0]["gas_volume_m3"] == pytest.approx(
        tel_explicit[0]["gas_volume_m3"],
        rel=1e-6,
        abs=1e-6,
    )
    assert tel_offset[0]["buoyancy_N"] == pytest.approx(
        tel_explicit[0]["buoyancy_N"],
        rel=1e-6,
        abs=1e-6,
    )
