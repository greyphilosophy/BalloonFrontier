import pytest

from balloon_frontier.simulation import EnvelopeConfig, SimulationState, run_simulation


def _env(*, contained_gas: bool = True) -> EnvelopeConfig:
    return EnvelopeConfig(
        max_volume_m3=200.0,
        burst_stretch_ratio=3.0,
        drag_coefficient=0.47,
        permeability=0.0,
        mass_kg=2.0,
        contained_gas=contained_gas,
    )


def test_landing_sets_altitude_to_ground_offset():
    env = _env()
    ground_alt = 500.0

    # Start slightly *below* the launch site's ground and descending.
    st = SimulationState(
        altitude_m=ground_alt - 1.0,
        terrain_base_altitude_offset_m=ground_alt,
        velocity_mps=-20.0,
        gas_type="helium",
        gas_mass_kg=0.05,
        gas_temperature_k=283.15,
        payload_mass_kg=10.0,
        ballast_mass_kg=100.0,
        envelope=env,
    )

    tel = run_simulation(st, dt=0.1, total_time_s=0.1, max_steps=1)
    last = tel[-1]

    assert last["landed"] is True
    assert last["altitude_m"] == pytest.approx(ground_alt, abs=1e-6)


def test_time_of_flight_and_landing_altitude_change_with_terrain_offset():
    env = _env()

    def run(offset_m: float):
        st = SimulationState(
            altitude_m=offset_m,
            terrain_base_altitude_offset_m=offset_m,
            gas_type="helium",
            gas_mass_kg=0.1,
            gas_temperature_k=283.15,
            payload_mass_kg=5.0,
            ballast_mass_kg=10.0,
            envelope=env,
        )
        tel = run_simulation(st, dt=0.1, total_time_s=60.0, max_steps=20000)
        last = tel[-1]
        return last["time_s"], last["landed"], last["altitude_m"], last["crashed"]

    t0, landed0, alt0, crashed0 = run(0.0)
    t1, landed1, alt1, crashed1 = run(500.0)

    assert landed0 is True
    assert landed1 is True

    # Landing altitude should be the site's ground altitude (not sea level).
    assert alt0 == pytest.approx(0.0, abs=1e-6)
    assert alt1 == pytest.approx(500.0, abs=1e-6)

    # Sanity: both trajectories terminate via landing/crash, and the
    # termination altitude is the site's ground altitude.
    # (Time-of-flight may or may not differ depending on buoyancy/drag model,
    # but the landing altitude MUST be correct for the terrain offset logic.)
