"""Regression tests for the unified gas/thermal aerostat model."""

from balloon_frontier.aerostat import configure_simulation_state
from balloon_frontier.flight_service import FlightService
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.physics import (
    atmosphere_density,
    atmosphere_pressure,
    atmosphere_temperature,
    gas_density,
)
from balloon_frontier.simulation import EnvelopeConfig, SimulationState, run_simulation
from balloon_frontier.thermal import effective_thermal_resistance


def test_air_at_ambient_state_matches_ambient_density():
    pressure = atmosphere_pressure(0.0)
    temperature = atmosphere_temperature(0.0)
    assert abs(
        gas_density("air", temperature, pressure) - atmosphere_density(0.0)
    ) < 0.01


def test_heating_air_continuously_reduces_density():
    pressure = atmosphere_pressure(0.0)
    cold = gas_density("air", 293.15, pressure)
    warm = gas_density("air", 333.15, pressure)
    hot = gas_density("air", 393.15, pressure)
    assert hot < warm < cold


def test_envelope_resistance_falls_when_stretch_increases():
    relaxed = effective_thermal_resistance(
        1.2,
        inflation_fraction=0.60,
        inflation_heat_loss_exponent=0.75,
        stretch_start_fraction=0.65,
    )
    stretched = effective_thermal_resistance(
        1.2,
        inflation_fraction=1.30,
        inflation_heat_loss_exponent=0.75,
        stretch_start_fraction=0.65,
    )
    assert stretched < relaxed


def test_first_flight_candle_components_feed_shared_state():
    request = LaunchRequest(
        gas_id="air",
        envelope_id="candle_kite",
        payload_ids=("candle_heater",),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )
    preparation = FlightService().prepare(request)
    state = preparation.sim_state

    assert state.gas_type == "air"
    assert state.heater_power_watts > 0.0
    assert state.envelope.thermal_resistance_m2_k_w is not None
    assert state.envelope.permeability == 0.0
    assert state.envelope.contained_gas is False


def test_ground_support_allows_real_heater_power_to_create_liftoff():
    pressure = atmosphere_pressure(0.0)
    temperature = atmosphere_temperature(0.0)
    volume = 0.20
    initial_gas_mass = gas_density("air", temperature, pressure) * volume

    state = SimulationState(
        gas_type="air",
        gas_mass_kg=initial_gas_mass,
        payload_mass_kg=0.005,
        ballast_mass_kg=0.0,
        heater_power_watts=80.0,
        wind_enabled=False,
        envelope=EnvelopeConfig(
            max_volume_m3=volume,
            burst_stretch_ratio=1.05,
            drag_coefficient=1.45,
            permeability=0.0,
            mass_kg=0.005,
            contained_gas=False,
            envelope_absorptivity=0.0,
            envelope_emissivity=0.0,
            thermal_resistance_m2_k_w=100.0,
        ),
    )

    telemetry = run_simulation(
        state,
        dt=0.1,
        total_time_s=90.0,
        max_steps=900,
        step_interval=1.0,
    )

    assert telemetry
    assert telemetry[-1]["gas_temperature_k"] > temperature
    assert any(point["altitude_m"] > 0.01 for point in telemetry)
    assert state.has_lifted_off is True


def test_hot_air_compatibility_id_has_same_composition_as_air():
    pressure = atmosphere_pressure(0.0)
    temperature = 350.0
    assert gas_density("hot_air", temperature, pressure) == gas_density(
        "air", temperature, pressure
    )
