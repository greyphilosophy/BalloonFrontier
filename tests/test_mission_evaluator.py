"""Balloon Frontier — MissionEvaluator tests

Focused unit tests for :class:`MissionEvaluator` that exercise every
objective type, config checks, and failure modes independently of the
flight simulation.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from balloon_frontier.launch_result import (
    LaunchRequest,
    MissionAssignment,
    MissionResult,
    TelemetryPoint,
    FillMode,
)
from balloon_frontier.mission_evaluator import MissionEvaluator
from balloon_frontier.missions import Mission, Objective


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_evaluator(
    missions: dict | None = None,
) -> MissionEvaluator:
    """Build a MissionEvaluator backed by an optional mission catalog."""
    if missions is not None:
        return MissionEvaluator(mission_catalog=missions)
    return MissionEvaluator()


def _make_telemetry(
    *,
    peak_altitude: float = 20000.0,
    duration_s: float = 3600.0,
    has_landed: bool = True,
    has_crashed: bool = False,
    burst: bool = False,
    start_x: float = 0.0,
    end_x: float = 0.0,
    n_points: int = 30,
) -> tuple[TelemetryPoint, ...]:
    """Generate a simple ascending-then-descending telemetry trace."""
    points: list[TelemetryPoint] = []
    for i in range(n_points):
        t = (i / (n_points - 1)) * duration_s if n_points > 1 else 0.0
        if i <= n_points // 2:
            alt = peak_altitude * (2 * i / (n_points - 1)) if n_points > 1 else peak_altitude
        else:
            alt = peak_altitude * (2 * (n_points - i - 1) / (n_points - 1)) if n_points > 1 else 0.0
        points.append(TelemetryPoint(
            time_s=t,
            altitude_m=max(alt, 0.0),
            velocity_mps=1.0 if i < n_points // 2 else -0.5,
            gas_volume_m3=5.0,
            ambient_pressure_pa=100000 - alt * 12,
            ambient_temperature_k=288 - alt * 0.0065,
            net_lift_N=10.0,
            buoyancy_N=15.0,
            weight_N=5.0,
            drag_N=2.0,
            gas_mass_kg=0.5,
            total_mass_kg=10.0,
            burst=burst and i == n_points - 1,
            landed=has_landed and i == n_points - 1,
            crashed=has_crashed and i == n_points - 1,
            x_m=start_x + (end_x - start_x) * (i / (n_points - 1)) if n_points > 1 else start_x,
            vx_mps=0.0,
        ))
    return tuple(points)


def _make_request(
    payload_ids: tuple[str, ...] = ("camera",),
    site: str = "field",
) -> LaunchRequest:
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=payload_ids,
        launch_site_id=site,
        fill_mode=FillMode.AUTO,
    )


# ═══════════════════════════════════════════════════════════════════════
# reach_altitude
# ═══════════════════════════════════════════════════════════════════════


class TestReachAltitude:
    def test_exceeds_minimum(self):
        mission = Mission(
            id="high_sky",
            title="High Sky",
            description="Reach high",
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 15000})],
        )
        tel = _make_telemetry(peak_altitude=20000.0)
        result = _make_evaluator({"high_sky": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("high_sky",))
        )
        assert len(result) == 1
        assert result[0].completed is True
        assert result[0].reward == 5000

    def test_below_minimum(self):
        mission = Mission(
            id="high_sky",
            title="High Sky",
            description="Reach high",
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 30000})],
        )
        tel = _make_telemetry(peak_altitude=20000.0)
        result = _make_evaluator({"high_sky": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("high_sky",))
        )
        assert len(result) == 1
        assert result[0].completed is False
        assert result[0].reward == 0

    def test_exact_minimum(self):
        mission = Mission(
            id="exact",
            title="Exact",
            description="Exactly here",
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 20000})],
        )
        tel = _make_telemetry(peak_altitude=20000.0)
        result = _make_evaluator({"exact": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("exact",))
        )
        assert result[0].completed is True

    def test_zero_minimum_always_passes(self):
        mission = Mission(
            id="easy",
            title="Easy",
            description="Anything goes",
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 0})],
        )
        tel = _make_telemetry(peak_altitude=0.0)
        result = _make_evaluator({"easy": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("easy",))
        )
        assert result[0].completed is True


# ═══════════════════════════════════════════════════════════════════════
# recover_data
# ═══════════════════════════════════════════════════════════════════════


class TestRecoverData:
    def test_safe_recovery(self):
        mission = Mission(
            id="recover",
            title="Recovery Mission",
            description="Bring it back",
            objectives=[Objective(type="recover_data", params={"required": True})],
        )
        tel = _make_telemetry(has_landed=True, has_crashed=False)
        result = _make_evaluator({"recover": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("recover",))
        )
        assert result[0].completed is True

    def test_crashed_fails(self):
        mission = Mission(
            id="recover",
            title="Recovery Mission",
            description="Bring it back",
            objectives=[Objective(type="recover_data", params={"required": True})],
        )
        tel = _make_telemetry(has_landed=True, has_crashed=True)
        result = _make_evaluator({"recover": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("recover",))
        )
        assert result[0].completed is False

    def test_burst_fails(self):
        mission = Mission(
            id="recover",
            title="Recovery Mission",
            description="Bring it back",
            objectives=[Objective(type="recover_data", params={"required": True})],
        )
        tel = _make_telemetry(burst=True, has_landed=False)
        result = _make_evaluator({"recover": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("recover",))
        )
        assert result[0].completed is False

    def test_no_landing_fails(self):
        mission = Mission(
            id="recover",
            title="Recovery Mission",
            description="Bring it back",
            objectives=[Objective(type="recover_data", params={"required": True})],
        )
        tel = _make_telemetry(has_landed=False)
        result = _make_evaluator({"recover": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("recover",))
        )
        assert result[0].completed is False


# ═══════════════════════════════════════════════════════════════════════
# capture_photo
# ═══════════════════════════════════════════════════════════════════════


class TestCapturePhoto:
    def test_camera_present_and_quality_met(self):
        mission = Mission(
            id="photo",
            title="Photo Mission",
            description="Take pics",
            objectives=[Objective(type="capture_photo", params={"minimum_quality": 0.5})],
        )
        # 20 000 m → quality = 20000/50000 = 0.4 → need higher alt
        tel = _make_telemetry(peak_altitude=25000.0)
        result = _make_evaluator({"photo": mission}).evaluate(
            _make_request(payload_ids=("camera",)), tel,
            MissionAssignment(mission_ids=("photo",)),
        )
        assert result[0].completed is True

    def test_no_camera_fails(self):
        mission = Mission(
            id="photo",
            title="Photo Mission",
            description="Take pics",
            objectives=[Objective(type="capture_photo", params={"minimum_quality": 0.5})],
        )
        tel = _make_telemetry(peak_altitude=60000.0)  # quality = 1.0, but no camera
        result = _make_evaluator({"photo": mission}).evaluate(
            _make_request(payload_ids=("battery",)), tel,
            MissionAssignment(mission_ids=("photo",)),
        )
        assert result[0].completed is False

    def test_quality_scaled_by_altitude(self):
        mission = Mission(
            id="photo",
            title="Photo Mission",
            description="Take pics",
            objectives=[Objective(type="capture_photo", params={"minimum_quality": 0.6})],
        )
        # 25 000 m → quality = 0.5, below 0.6 threshold → fail
        tel = _make_telemetry(peak_altitude=25000.0)
        result = _make_evaluator({"photo": mission}).evaluate(
            _make_request(payload_ids=("camera",)), tel,
            MissionAssignment(mission_ids=("photo",)),
        )
        assert result[0].completed is False

    def test_burst_halves_quality(self):
        mission = Mission(
            id="photo",
            title="Photo Mission",
            description="Take pics",
            objectives=[Objective(type="capture_photo", params={"minimum_quality": 0.5})],
        )
        # 50 000 m → quality = 1.0, burst halves → 0.5, threshold 0.5 → pass
        tel = _make_telemetry(peak_altitude=50000.0, burst=True)
        result = _make_evaluator({"photo": mission}).evaluate(
            _make_request(payload_ids=("camera",)), tel,
            MissionAssignment(mission_ids=("photo",)),
        )
        assert result[0].completed is True

    def test_burst_plus_low_altitude_fails(self):
        mission = Mission(
            id="photo",
            title="Photo Mission",
            description="Take pics",
            objectives=[Objective(type="capture_photo", params={"minimum_quality": 0.5})],
        )
        # 20 000 m → quality = 0.4, burst halves → 0.2, below 0.5 → fail
        tel = _make_telemetry(peak_altitude=20000.0, burst=True)
        result = _make_evaluator({"photo": mission}).evaluate(
            _make_request(payload_ids=("camera",)), tel,
            MissionAssignment(mission_ids=("photo",)),
        )
        assert result[0].completed is False


# ═══════════════════════════════════════════════════════════════════════
# float_duration
# ═══════════════════════════════════════════════════════════════════════


class TestFloatDuration:
    def test_target_hours_met(self):
        mission = Mission(
            id="floaty",
            title="Floaty Mission",
            description="Stay up long",
            objectives=[Objective(type="float_duration", params={"target_hours": 1.0})],
        )
        tel = _make_telemetry(duration_s=3600.0)  # exactly 1 hour
        result = _make_evaluator({"floaty": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("floaty",))
        )
        assert result[0].completed is True

    def test_short_flight_fails(self):
        mission = Mission(
            id="floaty",
            title="Floaty Mission",
            description="Stay up long",
            objectives=[Objective(type="float_duration", params={"target_hours": 2.0})],
        )
        tel = _make_telemetry(duration_s=3600.0)  # only 1 hour
        result = _make_evaluator({"floaty": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("floaty",))
        )
        assert result[0].completed is False

    def test_long_flight_passes(self):
        mission = Mission(
            id="floaty",
            title="Floaty Mission",
            description="Stay up long",
            objectives=[Objective(type="float_duration", params={"target_hours": 0.5})],
        )
        tel = _make_telemetry(duration_s=3600.0)  # 1 hour > 0.5 target
        result = _make_evaluator({"floaty": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("floaty",))
        )
        assert result[0].completed is True

    def test_zero_hours_always_passes(self):
        mission = Mission(
            id="instant",
            title="Instant",
            description="Any duration",
            objectives=[Objective(type="float_duration", params={"target_hours": 0})],
        )
        tel = _make_telemetry(duration_s=0.0)
        result = _make_evaluator({"instant": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("instant",))
        )
        assert result[0].completed is True


# ═══════════════════════════════════════════════════════════════════════
# station_keep
# ═══════════════════════════════════════════════════════════════════════


class TestStationKeep:
    def test_stays_in_range(self):
        target_alt = 10000.0
        tolerance = 500.0  # ± 500 m
        mission = Mission(
            id="station",
            title="Station Keep",
            description="Stay near altitude",
            objectives=[Objective(type="station_keep", params={"target_altitude_m": target_alt})],
        )
        # Generate telemetry where 100% of points are in range
        n_points = 20
        tel: list[TelemetryPoint] = []
        for i in range(n_points):
            alt = target_alt + (i % 3 - 1) * 100  # oscillates -100, 0, +100
            tel.append(TelemetryPoint(
                time_s=i * 100.0,
                altitude_m=alt,
                velocity_mps=0.0,
                gas_volume_m3=5.0,
                ambient_pressure_pa=100000,
                ambient_temperature_k=273,
                net_lift_N=0.0,
                buoyancy_N=10.0,
                weight_N=10.0,
                drag_N=0.0,
                gas_mass_kg=0.5,
                total_mass_kg=10.0,
            ))
        result = _make_evaluator({"station": mission}).evaluate(
            _make_request(), tuple(tel),
            MissionAssignment(mission_ids=("station",)),
        )
        assert result[0].completed is True

    def test_fails_with_few_points_in_range(self):
        target_alt = 10000.0
        mission = Mission(
            id="station",
            title="Station Keep",
            description="Stay near altitude",
            objectives=[Objective(type="station_keep", params={"target_altitude_m": target_alt})],
        )
        # Generate telemetry where only 30% of points are in range → fail
        n_points = 10
        tel: list[TelemetryPoint] = []
        for i in range(n_points):
            alt = target_alt if i < 3 else 15000.0  # only 3/10 in range (30%)
            tel.append(TelemetryPoint(
                time_s=i * 100.0,
                altitude_m=alt,
                velocity_mps=0.0,
                gas_volume_m3=5.0,
                ambient_pressure_pa=100000,
                ambient_temperature_k=273,
                net_lift_N=0.0,
                buoyancy_N=10.0,
                weight_N=10.0,
                drag_N=0.0,
                gas_mass_kg=0.5,
                total_mass_kg=10.0,
            ))
        result = _make_evaluator({"station": mission}).evaluate(
            _make_request(), tuple(tel),
            MissionAssignment(mission_ids=("station",)),
        )
        assert result[0].completed is False

    def test_exact_50_percent_passes(self):
        target_alt = 10000.0
        mission = Mission(
            id="station",
            title="Station Keep",
            description="Stay near altitude",
            objectives=[Objective(type="station_keep", params={"target_altitude_m": target_alt})],
        )
        # 5/10 points in range → exactly 50% → pass
        n_points = 10
        tel: list[TelemetryPoint] = []
        for i in range(n_points):
            alt = target_alt if i < 5 else 15000.0
            tel.append(TelemetryPoint(
                time_s=i * 100.0,
                altitude_m=alt,
                velocity_mps=0.0,
                gas_volume_m3=5.0,
                ambient_pressure_pa=100000,
                ambient_temperature_k=273,
                net_lift_N=0.0,
                buoyancy_N=10.0,
                weight_N=10.0,
                drag_N=0.0,
                gas_mass_kg=0.5,
                total_mass_kg=10.0,
            ))
        result = _make_evaluator({"station": mission}).evaluate(
            _make_request(), tuple(tel),
            MissionAssignment(mission_ids=("station",)),
        )
        assert result[0].completed is True


# ═══════════════════════════════════════════════════════════════════════
# fly_distance
# ═══════════════════════════════════════════════════════════════════════


class TestFlyDistance:
    def test_distance_met(self):
        mission = Mission(
            id="fly",
            title="Fly Far",
            description="Travel far",
            objectives=[Objective(type="fly_distance", params={"minimum_m": 5000})],
        )
        tel = _make_telemetry(start_x=0.0, end_x=6000.0)
        result = _make_evaluator({"fly": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("fly",))
        )
        assert result[0].completed is True

    def test_distance_not_met(self):
        mission = Mission(
            id="fly",
            title="Fly Far",
            description="Travel far",
            objectives=[Objective(type="fly_distance", params={"minimum_m": 5000})],
        )
        tel = _make_telemetry(start_x=0.0, end_x=3000.0)
        result = _make_evaluator({"fly": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("fly",))
        )
        assert result[0].completed is False

    def test_zero_minimum_always_passes(self):
        mission = Mission(
            id="fly",
            title="Fly Far",
            description="Travel far",
            objectives=[Objective(type="fly_distance", params={"minimum_m": 0})],
        )
        tel = _make_telemetry(start_x=0.0, end_x=0.0)
        result = _make_evaluator({"fly": mission}).evaluate(
            _make_request(), tel, MissionAssignment(mission_ids=("fly",))
        )
        assert result[0].completed is True


# ═══════════════════════════════════════════════════════════════════════
# Config checks
# ═══════════════════════════════════════════════════════════════════════


class TestConfigChecks:
    def test_missing_required_payload(self):
        mission = Mission(
            id="camera_required",
            title="Camera Mission",
            description="Needs camera",
            required_payloads=["camera"],
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 0})],
        )
        # No camera payload
        tel = _make_telemetry()
        result = _make_evaluator({"camera_required": mission}).evaluate(
            _make_request(payload_ids=("battery",)), tel,
            MissionAssignment(mission_ids=("camera_required",)),
        )
        assert result[0].completed is False
        assert "missing required payloads" in result[0].explanation

    def test_wrong_launch_site(self):
        mission = Mission(
            id="mountain_only",
            title="Mountain Mission",
            description="Only from mountain",
            launch_site="mountain",
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 0})],
        )
        tel = _make_telemetry()
        result = _make_evaluator({"mountain_only": mission}).evaluate(
            _make_request(site="field"), tel,
            MissionAssignment(mission_ids=("mountain_only",)),
        )
        assert result[0].completed is False
        assert "launch site" in result[0].explanation and "mountain" in result[0].explanation

    def test_correct_site(self):
        mission = Mission(
            id="mountain_only",
            title="Mountain Mission",
            description="Only from mountain",
            launch_site="mountain",
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 0})],
        )
        tel = _make_telemetry()
        result = _make_evaluator({"mountain_only": mission}).evaluate(
            _make_request(site="mountain"), tel,
            MissionAssignment(mission_ids=("mountain_only",)),
        )
        assert result[0].completed is True


# ═══════════════════════════════════════════════════════════════════════
# Unknown missions / objectives
# ═══════════════════════════════════════════════════════════════════════


class TestUnknown:
    def test_unknown_mission_id_fails_closed(self):
        tel = _make_telemetry()
        result = _make_evaluator({"known": Mission("known", "Known", "Known")}).evaluate(
            _make_request(), tel,
            MissionAssignment(mission_ids=("unknown_mission",)),
        )
        assert len(result) == 1
        assert result[0].completed is False
        assert result[0].reward == 0
        assert "not found" in result[0].explanation

    def test_unknown_objective_type_fails_closed(self, caplog):
        mission = Mission(
            id="weird",
            title="Weird Mission",
            description="Has unknown objective",
            objectives=[Objective(type="do_thing", params={"value": 42})],
        )
        tel = _make_telemetry()
        with caplog.at_level(logging.ERROR):
            result = _make_evaluator({"weird": mission}).evaluate(
                _make_request(), tel,
                MissionAssignment(mission_ids=("weird",)),
            )
        assert result[0].completed is False
        assert result[0].reward == 0

    def test_custom_catalog(self):
        custom_missions = {
            "custom_01": Mission(
                id="custom_01",
                title="Custom Mission",
                description="Custom objective",
                objectives=[Objective(type="reach_altitude", params={"minimum_m": 10000})],
            ),
        }
        tel = _make_telemetry(peak_altitude=15000.0)
        result = _make_evaluator(missions=custom_missions).evaluate(
            _make_request(), tel,
            MissionAssignment(mission_ids=("custom_01",)),
        )
        assert result[0].completed is True


# ═══════════════════════════════════════════════════════════════════════
# Empty / edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyEdgeCases:
    def test_no_mission_ids(self):
        tel = _make_telemetry()
        result = _make_evaluator().evaluate(
            _make_request(), tel,
            MissionAssignment(mission_ids=()),
        )
        assert result == ()

    def test_mission_with_no_objectives(self):
        mission = Mission(
            id="blank",
            title="Blank",
            description="No objectives",
        )
        tel = _make_telemetry()
        result = _make_evaluator({"blank": mission}).evaluate(
            _make_request(), tel,
            MissionAssignment(mission_ids=("blank",)),
        )
        assert result[0].completed is True

    def test_single_telemetry_point(self):
        tel = (_make_telemetry(n_points=1),)[0]
        mission = Mission(
            id="quick",
            title="Quick",
            description="Short flight",
            objectives=[
                Objective(type="reach_altitude", params={"minimum_m": 0}),
                Objective(type="recover_data", params={"required": True}),
            ],
        )
        result = _make_evaluator({"quick": mission}).evaluate(
            _make_request(), tel,
            MissionAssignment(mission_ids=("quick",)),
        )
        assert result[0].completed is True


# ═══════════════════════════════════════════════════════════════════════
# Multiple missions — mixed results
# ═══════════════════════════════════════════════════════════════════════


class TestMultipleMissions:
    def test_mixed_results(self):
        missions = {
            "easy": Mission(
                id="easy",
                title="Easy",
                description="Always passes",
                objectives=[Objective(type="reach_altitude", params={"minimum_m": 0})],
            ),
            "hard": Mission(
                id="hard",
                title="Hard",
                description="Always fails",
                objectives=[Objective(type="reach_altitude", params={"minimum_m": 1000000})],
            ),
        }
        tel = _make_telemetry(peak_altitude=20000.0)
        result = _make_evaluator(missions).evaluate(
            _make_request(), tel,
            MissionAssignment(mission_ids=("easy", "hard")),
        )
        assert len(result) == 2
        assert result[0].completed is True
        assert result[0].reward == 5000
        assert result[1].completed is False
        assert result[1].reward == 0

    def test_order_preserved(self):
        missions = {
            "a": Mission(id="a", title="A", description="", objectives=[]),
            "b": Mission(id="b", title="B", description="", objectives=[]),
            "c": Mission(id="c", title="C", description="", objectives=[]),
        }
        tel = _make_telemetry()
        result = _make_evaluator(missions).evaluate(
            _make_request(), tel,
            MissionAssignment(mission_ids=("c", "a", "b")),
        )
        assert tuple(mr.mission_id for mr in result) == ("c", "a", "b")