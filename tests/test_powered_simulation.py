"""Integration coverage for the finite-energy simulation shell."""

from balloon_frontier.powered_simulation import run_powered_simulation
from balloon_frontier.simulation import EnvelopeConfig, SimulationState


def _state(
    *,
    altitude_m: float = 10.0,
    gas_mass_kg: float = 0.02,
    payload_mass_kg: float = 1.0,
    has_pressure_valve: bool = False,
) -> SimulationState:
    return SimulationState(
        altitude_m=altitude_m,
        gas_type="helium",
        gas_mass_kg=gas_mass_kg,
        payload_mass_kg=payload_mass_kg,
        ballast_mass_kg=0.0,
        has_pressure_valve=has_pressure_valve,
        wind_enabled=False,
        envelope=EnvelopeConfig(
            max_volume_m3=10.0,
            burst_stretch_ratio=2.5,
            drag_coefficient=0.47,
            permeability=0.0,
            mass_kg=0.1,
            contained_gas=True,
            envelope_absorptivity=0.0,
            envelope_emissivity=0.0,
        ),
    )


def test_quadcopter_uses_battery_to_add_vertical_lift():
    state = _state()
    start_altitude = state.altitude_m

    result = run_powered_simulation(
        state,
        payload_ids=("quadcopter", "battery"),
        dt=0.1,
        total_time_s=2.0,
    )

    assert result.telemetry
    assert max(tick["vertical_control_force_N"] for tick in result.telemetry) > 0.0
    assert max(tick["altitude_m"] for tick in result.telemetry) > start_altitude
    assert result.battery_remaining_wh < result.battery_capacity_wh
    assert any("Battery:" in note for note in result.flight_notes)


def test_quadcopter_without_battery_has_no_powered_control():
    state = _state()

    result = run_powered_simulation(
        state,
        payload_ids=("quadcopter",),
        dt=0.1,
        total_time_s=1.0,
    )

    assert all(tick["vertical_control_force_N"] == 0.0 for tick in result.telemetry)
    assert all(tick["electrical_power_w"] == 0.0 for tick in result.telemetry)
    assert any("no Battery Pack" in note for note in result.flight_notes)


def test_over_buoyant_return_reports_missing_descent_authority():
    state = _state(gas_mass_kg=0.6, payload_mass_kg=0.1)
    state.time_s = 40.0

    result = run_powered_simulation(
        state,
        payload_ids=("quadcopter", "battery"),
        dt=0.1,
        total_time_s=1.0,
    )

    assert any(tick["returning"] for tick in result.telemetry)
    assert any(
        "remained positively buoyant" in note
        for note in result.flight_notes
    )


def test_pressure_valve_is_an_active_lift_reduction_method_on_return():
    state = _state(
        gas_mass_kg=0.6,
        payload_mass_kg=0.1,
        has_pressure_valve=True,
    )
    state.time_s = 40.0
    starting_gas_mass = state.gas_mass_kg

    result = run_powered_simulation(
        state,
        payload_ids=("quadcopter", "battery", "valve"),
        dt=0.1,
        total_time_s=2.0,
    )

    assert result.telemetry
    assert result.telemetry[-1]["gas_mass_kg"] < starting_gas_mass
    assert not any(
        "remained positively buoyant" in note
        for note in result.flight_notes
    )


def test_battery_depletion_turns_off_powered_systems(monkeypatch):
    monkeypatch.setattr("balloon_frontier.power.BATTERY_PACK_CAPACITY_WH", 0.001)
    state = _state()

    result = run_powered_simulation(
        state,
        payload_ids=("quadcopter", "battery"),
        dt=0.1,
        total_time_s=2.0,
    )

    assert result.battery_remaining_wh == 0.0
    assert any("Battery depleted" in note for note in result.flight_notes)
    assert result.telemetry[-1]["vertical_control_force_N"] == 0.0


def test_unpowered_loadouts_delegate_without_power_notes():
    state = _state()

    result = run_powered_simulation(
        state,
        payload_ids=("parachute",),
        dt=0.1,
        total_time_s=0.2,
    )

    assert result.telemetry
    assert result.flight_notes == ()
    assert "battery_remaining_wh" not in result.telemetry[0]
