"""Shared horizontal-control physics for powered payloads."""

import pytest

from balloon_frontier.simulation import EnvelopeConfig, SimulationState, simulation_step


def _state(control_accel_mps2: float) -> SimulationState:
    return SimulationState(
        altitude_m=100.0,
        gas_type="helium",
        gas_mass_kg=0.05,
        payload_mass_kg=0.25,
        ballast_mass_kg=0.0,
        wind_enabled=True,
        horizontal_control_accel_mps2=control_accel_mps2,
        envelope=EnvelopeConfig(
            max_volume_m3=10.0,
            mass_kg=0.05,
            contained_gas=True,
            permeability=0.0,
            envelope_absorptivity=0.0,
            envelope_emissivity=0.0,
        ),
    )


def test_quadcopter_control_counteracts_mild_wind_without_disabling_it(monkeypatch):
    calls = []

    def mild_wind(altitude_m, *, time_s=0.0, site_id="field"):
        calls.append((altitude_m, time_s, site_id))
        return 1.0, 0.0

    monkeypatch.setattr("balloon_frontier.wind.wind_vector", mild_wind)

    passive = _state(0.0)
    controlled = _state(2.5)
    passive_tick = simulation_step(passive, dt=0.1)
    controlled_tick = simulation_step(controlled, dt=0.1)

    assert calls
    assert passive_tick["vx_mps"] > 0.0
    assert abs(controlled_tick["vx_mps"]) < abs(passive_tick["vx_mps"])
    assert controlled_tick["control_accel_x_mps2"] < 0.0
    assert controlled.wind_enabled is True


def test_control_authority_is_bounded_when_wind_is_too_strong(monkeypatch):
    monkeypatch.setattr(
        "balloon_frontier.wind.wind_vector",
        lambda altitude_m, *, time_s=0.0, site_id="field": (20.0, 0.0),
    )

    controlled = _state(2.5)
    tick = simulation_step(controlled, dt=0.1)

    assert tick["control_accel_x_mps2"] == pytest.approx(-2.5)
    assert tick["vx_mps"] > 0.0
    assert tick["x_m"] > 0.0
