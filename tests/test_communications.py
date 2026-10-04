"""Physical boundaries and end-to-end scoring for powered relay coverage."""

from dataclasses import replace
from math import acos
from pathlib import Path

import pytest

from balloon_frontier.communications import (
    EARTH_RADIUS_M,
    RADIO_POWER_W,
    radio_coverage_radius_m,
    relay_service,
)
from balloon_frontier.launch_result import (
    LaunchRequest, MissionAssignment, TelemetryPoint, telemetry_list_to_points,
)
from balloon_frontier.mission_evaluator import MissionEvaluator
from balloon_frontier.missions import load_mission_json
from balloon_frontier.powered_simulation import run_powered_simulation
from balloon_frontier.simulation import EnvelopeConfig, SimulationState


def point(time_s, **changes):
    base = TelemetryPoint(
        time_s=time_s, altitude_m=17000.0, velocity_mps=0.0,
        gas_volume_m3=100.0, ambient_pressure_pa=9000.0,
        ambient_temperature_k=216.65, net_lift_N=0.0,
        buoyancy_N=100.0, weight_N=100.0, drag_N=0.0,
        gas_mass_kg=1.0, total_mass_kg=10.0,
        radio_active=True, radio_coverage_radius_m=20000.0,
    )
    return replace(base, **changes)


def sky_relay():
    return load_mission_json(str(
        Path(__file__).resolve().parents[1] / "data/missions/sky_relay.json"
    ))


def test_low_altitude_footprint_agrees_with_flat_ground_limit():
    # At a 45-degree elevation angle a 10 m mast reaches roughly 10 m away.
    assert radio_coverage_radius_m(10.0, min_elevation_deg=45.0) == pytest.approx(
        10.0, rel=1e-5
    )


def test_horizon_and_slant_range_both_bound_coverage():
    height = 17000.0
    horizon = EARTH_RADIUS_M * acos(EARTH_RADIUS_M / (EARTH_RADIUS_M + height))
    assert radio_coverage_radius_m(
        height, min_elevation_deg=0.0, max_slant_range_m=1_000_000.0,
    ) == pytest.approx(horizon)
    assert radio_coverage_radius_m(95000.0) < radio_coverage_radius_m(height)
    assert radio_coverage_radius_m(100000.0) == 0.0
    assert radio_coverage_radius_m(110000.0) == 0.0
    assert radio_coverage_radius_m(0.0) == 0.0


@pytest.mark.parametrize("kwargs", [
    {"height_agl_m": float("nan")},
    {"height_agl_m": 100.0, "max_slant_range_m": 0.0},
    {"height_agl_m": 100.0, "min_elevation_deg": 90.0},
])
def test_invalid_radio_geometry_is_rejected(kwargs):
    with pytest.raises(ValueError):
        radio_coverage_radius_m(**kwargs)


def test_service_uses_elapsed_time_and_requires_whole_target_coverage():
    trace = (
        point(0), point(10), point(70),
        point(80, x_m=10001),  # Far edge of 10 km community is outside footprint.
        point(90), point(120),
    )
    report = relay_service(trace, target_radius_m=10000)
    assert report.connected_s == 100.0
    assert report.longest_connection_s == 70.0
    assert report.interruptions == ("target outside radio footprint",)
    # A differently sampled constant flight has the same service duration.
    assert relay_service((point(0), point(7), point(120))).connected_s == 120.0
    assert relay_service((point(0), point(120))).connected_s == 120.0


@pytest.mark.parametrize("changes,reason", [
    ({"radio_active": False}, "radio unpowered"),
    ({"radio_coverage_radius_m": 0.0}, "target outside radio footprint"),
    ({"altitude_m": 15999.0}, "below service altitude"),
    ({"burst": True}, "platform no longer in service"),
    ({"landed": True}, "platform no longer in service"),
    ({"crashed": True}, "platform no longer in service"),
])
def test_service_never_bridges_an_outage(changes, reason):
    trace = (point(0), point(10), point(20, **changes), point(30), point(40))
    report = relay_service(trace, minimum_altitude_m=16000)
    assert report.connected_s == 20
    assert report.longest_connection_s == 10
    assert reason in report.interruptions


def test_offset_target_and_invalid_telemetry_do_not_manufacture_service():
    trace = (point(0, x_m=-30000), point(60, x_m=-30000))
    assert relay_service(trace, target_x_m=-30000, target_radius_m=10000).connected_s == 60
    assert relay_service(trace, target_radius_m=10000).connected_s == 0
    assert relay_service(()).connected_s == 0
    assert relay_service((point(60),)).connected_s == 0
    for trace in (
        (point(0), point(60), point(20), point(60)),
        (point(0), point(0), point(60)),
        (point(0), point(60, x_m=float("nan"))),
    ):
        assert relay_service(trace).connected_s == 0
    with pytest.raises(ValueError):
        relay_service((), target_radius_m=-1.0)


def relay_state():
    # Start aloft to isolate electrical behavior from the ascent design.
    return SimulationState(
        altitude_m=17000.0, gas_mass_kg=1.0, payload_mass_kg=5.0,
        ballast_mass_kg=0.0, wind_enabled=False,
        envelope=EnvelopeConfig(
            max_volume_m3=1000, mass_kg=0.5, permeability=0.0,
            envelope_absorptivity=0.0, envelope_emissivity=0.0,
        ),
    )


def test_live_radio_draws_energy_and_survives_typed_telemetry_conversion():
    state = relay_state()
    state.terrain_base_altitude_offset_m = 1500.0
    result = run_powered_simulation(
        state, payload_ids=("radio", "battery"), total_time_s=1.0,
    )
    points = telemetry_list_to_points(list(result.telemetry))
    assert points[-1].electrical_power_w == RADIO_POWER_W
    assert points[-1].battery_capacity_wh == 500.0
    assert points[-1].battery_remaining_wh == pytest.approx(500.0 - RADIO_POWER_W / 3600)
    assert all(p.radio_active for p in points)
    assert points[-1].radio_coverage_radius_m == pytest.approx(
        radio_coverage_radius_m(points[-1].altitude_m - 1500.0)
    )


def test_no_battery_or_depleted_battery_cannot_supply_coverage(monkeypatch):
    unpowered = run_powered_simulation(
        relay_state(), payload_ids=("radio",), total_time_s=1.0,
    )
    assert all(not tick["radio_active"] for tick in unpowered.telemetry)
    assert any("no Battery Pack" in note for note in unpowered.flight_notes)

    monkeypatch.setattr("balloon_frontier.power.BATTERY_PACK_CAPACITY_WH", 0.001)
    depleted = run_powered_simulation(
        relay_state(), payload_ids=("radio", "battery"), total_time_s=1.0,
    )
    assert depleted.telemetry[0]["radio_active"]
    assert not depleted.telemetry[1]["radio_active"]
    assert depleted.telemetry[-1]["radio_coverage_radius_m"] == 0.0
    assert depleted.battery_remaining_wh == 0.0


def test_sky_relay_evaluates_connected_minutes_and_explains_failures():
    mission = sky_relay()
    evaluator = MissionEvaluator({mission.id: mission})
    request = LaunchRequest("helium", "zero_pressure", ("radio", "battery"))
    assignment = MissionAssignment((mission.id,))
    success = evaluator.evaluate(request, (point(0), point(1800)), assignment)[0]
    assert success.completed and success.reward == mission.budget
    assert "30.0 / 30.0 min" in success.explanation
    failed = evaluator.evaluate(request, (
        point(0), point(1799), point(1800, radio_active=False), point(7200, radio_active=False),
    ), assignment)[0]
    assert not failed.completed and failed.reward == 0
    assert "radio unpowered" in failed.explanation
    # Old telemetry has no evidence of a working radio, even on a long flight.
    legacy = (point(0, radio_active=False), point(7200, radio_active=False))
    assert not evaluator.evaluate(request, legacy, assignment)[0].completed


def test_real_powered_flight_drives_coverage_objective():
    mission = sky_relay()
    mission.objectives[0].params["minimum_duration_s"] = 0.5
    result = run_powered_simulation(
        relay_state(), payload_ids=("radio", "battery"), total_time_s=1.0,
    )
    request = LaunchRequest("helium", "zero_pressure", ("radio", "battery"))
    scored = MissionEvaluator({mission.id: mission}).evaluate(
        request, tuple(telemetry_list_to_points(list(result.telemetry))),
        MissionAssignment((mission.id,)),
    )
    assert scored[0].completed


def test_scenario_pool_can_assign_sky_relay_without_changing_story():
    from balloon_frontier.session_controller import plan_session

    plan = plan_session("scenario", {
        "gas": "helium", "envelope": "zero_pressure", "fill_mode": "auto",
        "payloads": ("radio", "battery"), "site": "field",
    })
    assert "sky_relay" in plan.missions
