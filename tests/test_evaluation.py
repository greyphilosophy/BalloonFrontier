"""Tests for mission evaluation system."""

import pytest
from balloon_frontier.evaluation import (
    Objective, MissionResult, evaluate_objective,
    evaluate_flight, format_mission_result,
)


class TestObjective:
    def test_create_objective(self):
        obj = Objective("reach_altitude", 20000, 15000)
        assert obj.type == "reach_altitude"
        assert obj.weight == 1.0

    def test_objective_with_weight(self):
        obj = Objective("capture_photo", 1.0, 0.8, 2.0, "Take photos")
        assert obj.weight == 2.0
        assert obj.description == "Take photos"


class TestEvaluateObjective:
    def test_reach_altitude_exceeds(self):
        obj = Objective("reach_altitude", 20000, 25000)
        assert evaluate_objective(obj) == 100.0

    def test_reach_altitude_barely_misses(self):
        obj = Objective("reach_altitude", 20000, 15000)
        score = evaluate_objective(obj)
        assert 50 < score < 100

    def test_capture_photo_perfect(self):
        obj = Objective("capture_photo", 1.0, 1.0)
        assert evaluate_objective(obj) == 100.0

    def test_float_duration_score(self):
        obj = Objective("float_duration", 6.0, 4.5)
        assert evaluate_objective(obj) < 100.0


class TestEvaluateFlight:
    def _make_telemetry(self, num_steps: int, peak_at: int = 5):
        """Create simple telemetry with a peak at a given step."""
        tel = []
        for i in range(num_steps):
            alt = min(i * 100, peak_at * 100)
            if i > peak_at:
                alt = peak_at * 100 - (i - peak_at) * 50
            tel.append({
                "altitude_m": max(alt, 0),
                "velocity_mps": 1.0 if i <= peak_at else -0.5,
                "time_s": i * 0.1,
                "burst": i == num_steps - 1 and alt < 50,
            })
        return tel

    def test_simple_altitude_objective(self):
        tel = self._make_telemetry(20, peak_at=10)
        mission = {
            "id": "test",
            "objectives": [{"type": "reach_altitude", "target_value": 800, "weight": 1.0}],
        }
        result = evaluate_flight(tel, mission)
        assert result.score > 50
        assert result.is_success

    def test_no_camera_reduces_photo_score(self):
        tel = self._make_telemetry(20, peak_at=10)
        mission = {
            "id": "test",
            "objectives": [{"type": "capture_photo", "target_value": 1.0, "weight": 1.0}],
        }
        result = evaluate_flight(tel, mission, payloads=["radio"])
        for obj in result.objectives:
            if obj.type == "capture_photo":
                assert obj.actual_value == 0.0

    def test_safe_landing_has_higher_recovery(self):
        """No burst → higher recovery than burst."""
        tel_safe = self._make_telemetry(20, peak_at=10)
        tel_safe[-1]["burst"] = False
        tel_burst = self._make_telemetry(20, peak_at=10)
        tel_burst[-1]["burst"] = True
        mission = {
            "id": "test",
            "objectives": [{"type": "recover_data"}],
        }
        r_safe = evaluate_flight(tel_safe, mission)
        r_burst = evaluate_flight(tel_burst, mission)
        safe_rec = [o for o in r_safe.objectives if o.type == "recover_data"][0]
        burst_rec = [o for o in r_burst.objectives if o.type == "recover_data"][0]
        assert safe_rec.actual_value > burst_rec.actual_value


class TestFormatMissionResult:
    def test_format_includes_score(self):
        result = MissionResult(
            mission_id="test", score=75.0,
            objectives=[], is_success=True)
        text = format_mission_result(result)
        assert "75.0" in text
        assert "test" in text
