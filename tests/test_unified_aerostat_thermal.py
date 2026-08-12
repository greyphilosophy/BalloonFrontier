"""Regression tests for the unified gas/thermal aerostat model."""

import pytest

from balloon_frontier.aerostat import (
    HeatSourceProfile,
    configured_simulation_state,
    envelope_thermal_profile,
    heat_source_power_watts,
)
from balloon_frontier.flight_service import FlightService, _state_with_weather_impacts
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.physics import (
    G,
    atmosphere_density,
    atmosphere_pressure,
    atmosphere_temperature,
    gas_density,
    gas_volume,
)
from balloon_frontier.simulation import (
    EnvelopeConfig,
    SimulationState,
    run_simulation,
    simulation_step,
)
from balloon_frontier.thermal import (
    calculate_balloon_heat_flows,
    effective_thermal_resistance,
)


def _candle_request(payload_ids=("candle_heater",)):
    return LaunchRequest(
        gas_id="air",
        envelope_id="candle_kite",
        payload_ids=payload_ids,
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )


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


def test_profile_uses_shared_resistance_equation():
    profile = envelope_thermal_profile("latex")
    assert profile.effective_resistance(1.2) == pytest.approx(
        effective_thermal_resistance(
            profile.thermal_resistance_m2_k_w,
            1.2,
            profile.inflation_heat_loss_exponent,
            profile.stretch_start_fraction,
        )
    )


def test_unknown_envelope_uses_stable_default_profile():
    first = envelope_thermal_profile("not-a-real-envelope")
    second = envelope_thermal_profile("still-not-real")
    assert first == second
    assert first.thermal_resistance_m2_k_w == 1.0
    assert first.risk_tags == ()


def test_heat_source_efficiency_is_clamped_to_physical_bounds():
    assert HeatSourceProfile(-10.0, 0.5).coupled_power_watts == 0.0
    assert HeatSourceProfile(100.0, -2.0).coupled_power_watts == 0.0
    assert HeatSourceProfile(100.0, 2.0).coupled_power_watts == 100.0


def test_multiple_heat_sources_compose_and_non_heaters_are_ignored():
    expected = (80.0 * 0.72) + (80.0 * 0.88)
    assert heat_source_power_watts(
        ("camera", "candle_heater", "electric_heater")
    ) == pytest.approx(expected)


def test_configured_state_is_a_pure_copy():
    request = _candle_request()
    original = request.to_simulation_state()
    original_permeability = original.envelope.permeability

    configured = configured_simulation_state(request, original)

    assert configured is not original
    assert configured.envelope is not original.envelope
    assert original.heater_power_watts == 0.0
    assert original.envelope.thermal_resistance_m2_k_w is None
    assert original.envelope.permeability == original_permeability
    assert configured.heater_power_watts == pytest.approx(80.0 * 0.72)
    assert configured.envelope.thermal_resistance_m2_k_w == 0.85
    assert configured.envelope.permeability == 0.0


def test_weather_transform_is_a_pure_copy():
    original = _candle_request().to_simulation_state()
    impacts = {
        "burst_risk": 1.2,
        "thermal_efficiency": 0.8,
        "pressure_modifier": 0.9,
        "ascent_rate": 1.1,
        "drift_factor": 1.3,
    }

    adjusted = _state_with_weather_impacts(original, impacts)

    assert adjusted is not original
    assert adjusted.envelope is not original.envelope
    assert original.weather_ascent_multiplier == 1.0
    assert original.envelope.weather_pressure_modifier == 1.0
    assert adjusted.weather_ascent_multiplier == 1.1
    assert adjusted.weather_drift_multiplier == 1.3
    assert adjusted.envelope.weather_burst_risk_modifier == 1.2
    assert adjusted.envelope.weather_solar_modifier == 0.8
    assert adjusted.envelope.weather_pressure_modifier == 0.9


def test_solar_uses_projected_area_while_losses_use_envelope_surface():
    flows = calculate_balloon_heat_flows(
        altitude_m=0.0,
        gas_temp_K=320.0,
        gas_mass_kg=0.1,
        gas_type="air",
        envelope_absorptivity=0.5,
        envelope_emissivity=0.8,
        envelope_area_m2=4.0,
        envelope_mass_kg=0.01,
        heater_power_watts=0.0,
        equipment_heat_watts=0.0,
        thermal_resistance_m2_k_w=1.0,
        solar_projected_area_m2=1.0,
    )
    legacy_area_flows = calculate_balloon_heat_flows(
        altitude_m=0.0,
        gas_temp_K=320.0,
        gas_mass_kg=0.1,
        gas_type="air",
        envelope_absorptivity=0.5,
        envelope_emissivity=0.8,
        envelope_area_m2=4.0,
        envelope_mass_kg=0.01,
        heater_power_watts=0.0,
        equipment_heat_watts=0.0,
        thermal_resistance_m2_k_w=1.0,
    )

    assert flows["Q_solar"] * 4.0 == pytest.approx(legacy_area_flows["Q_solar"])
    assert flows["Q_radiation"] == pytest.approx(legacy_area_flows["Q_radiation"])
    assert flows["Q_convection"] == pytest.approx(legacy_area_flows["Q_convection"])
    assert flows["Q_envelope"] == pytest.approx(legacy_area_flows["Q_envelope"])


def test_archimedean_buoyancy_does_not_charge_gas_weight_twice():
    state = SimulationState(
        gas_type="helium",
        gas_mass_kg=0.05,
        payload_mass_kg=0.10,
        ballast_mass_kg=0.0,
        wind_enabled=False,
        envelope=EnvelopeConfig(
            max_volume_m3=10.0,
            mass_kg=0.05,
            contained_gas=True,
            permeability=0.0,
            envelope_absorptivity=0.0,
            envelope_emissivity=0.0,
        ),
    )
    initial_volume = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        state.gas_temperature_k,
        atmosphere_pressure(0.0),
    )
    tick = simulation_step(state, dt=0.01)

    expected_buoyancy = atmosphere_density(0.0) * G * initial_volume
    assert tick["buoyancy_N"] == pytest.approx(expected_buoyancy, rel=1e-3)
    assert tick["weight_N"] == pytest.approx(state.total_mass() * G, rel=1e-3)


def test_first_flight_candle_components_feed_shared_state():
    preparation = FlightService().prepare(_candle_request())
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
