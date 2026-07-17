"""Tests for the mission system (GDD §14.2, §17)."""

import json
import os
import tempfile
import pytest
from balloon_frontier.missions import (
    Objective, Mission, register_mission, get_mission, list_missions,
    load_mission_json, load_mission_directory, MISSIONS,
)


class TestMissionModel:
    """Test the Mission data model."""

    def test_create_mission(self):
        m = Mission(
            id="test_01",
            title="Test Mission",
            description="A test mission",
            launch_site="field",
            budget=5000,
        )
        assert m.id == "test_01"
        assert m.budget == 5000

    def test_mission_serialization(self):
        m = Mission(
            id="test_01",
            title="Test",
            description="Desc",
            objectives=[Objective(type="reach_altitude", params={"minimum_m": 30000})],
        )
        d = m.to_dict()
        assert d["id"] == "test_01"
        assert len(d["objectives"]) == 1
        assert d["objectives"][0]["type"] == "reach_altitude"

    def test_objective_params(self):
        obj = Objective(type="capture_photo", params={"target_id": "horizon"})
        assert obj.type == "capture_photo"
        assert obj.params["target_id"] == "horizon"

    def test_mission_with_defaults(self):
        m = Mission(id="minimal", title="Minimal", description="Short")
        assert m.budget == 5000
        assert m.launch_site == "field"
        assert len(m.objectives) == 0
        assert m.difficulty == 1


class TestMissionRegistration:
    """Test mission registry operations."""

    def setup_method(self):
        MISSIONS.clear()

    def test_register_and_get(self):
        m = Mission(id="reg_test", title="Registration Test", description="Reg desc")
        register_mission(m)
        assert get_mission("reg_test").id == "reg_test"

    def test_get_unknown_raises(self):
        MISSIONS.clear()
        with pytest.raises(KeyError):
            get_mission("nonexistent")

    def test_list_missions(self):
        MISSIONS.clear()
        m1 = Mission(id="m1", title="M1", description="D1")
        m2 = Mission(id="m2", title="M2", description="D2")
        register_mission(m1)
        register_mission(m2)
        assert len(list_missions()) == 2

    def test_override_registration(self):
        m1 = Mission(id="override", title="First", description="D1")
        m2 = Mission(id="override", title="Second", description="D2")
        register_mission(m1)
        register_mission(m2)
        assert get_mission("override").title == "Second"


class TestMissionJSONLoading:
    """Test loading missions from JSON files."""

    def test_load_valid_json(self, tmp_path):
        data = {
            "id": "json_test",
            "title": "JSON Mission",
            "description": "Loaded from JSON",
            "budget": 3000,
            "objectives": [
                {"type": "reach_altitude", "params": {"minimum_m": 20000}},
                {"type": "capture_photo", "params": {"target_id": "sun", "minimum_quality": 0.5}},
            ],
        }
        fpath = tmp_path / "mission.json"
        with open(fpath, 'w') as f:
            json.dump(data, f)

        m = load_mission_json(str(fpath))
        assert m.id == "json_test"
        assert m.budget == 3000
        assert len(m.objectives) == 2

    def test_load_from_directory(self, tmp_path):
        for i in range(3):
            data = {"id": f"dir_{i}", "title": f"Mission {i}", "description": "D"}
            fpath = tmp_path / f"mission_{i}.json"
            with open(fpath, 'w') as f:
                json.dump(data, f)

        MISSIONS.clear()
        load_mission_directory(str(tmp_path))
        assert len(list_missions()) == 3

    def test_ignores_non_json_files(self, tmp_path):
        data = {"id": "keep", "title": "Keep", "description": "D"}
        json_path = tmp_path / "keep.json"
        with open(json_path, 'w') as f:
            json.dump(data, f)
        text_path = tmp_path / "readme.txt"
        text_path.write_text("hello")

        MISSIONS.clear()
        load_mission_directory(str(tmp_path))
        assert len(list_missions()) == 1

    def test_handles_missing_fields(self, tmp_path):
        # Minimal valid JSON
        data = {"id": "minimal", "title": "Min", "description": "D"}
        fpath = tmp_path / "minimal.json"
        with open(fpath, 'w') as f:
            json.dump(data, f)

        m = load_mission_json(str(fpath))
        assert m.id == "minimal"
        assert m.budget == 5000
        assert m.required_payloads == []


class TestMissionFromDataDir:
    """Test loading the actual mission data files."""

    def test_sounding_01_loads(self):
        MISSIONS.clear()
        load_mission_directory("/home/greyphilosophy/projects/BalloonFrontier/data/missions/")
        assert "sounding_01" in MISSIONS
        m = MISSIONS["sounding_01"]
        assert m.id == "sounding_01"
        assert len(m.objectives) == 3
        assert "camera" in m.required_payloads

    def test_mission_evaluate_reach_altitude(self):
        obj = Objective(type="reach_altitude", params={"minimum_m": 30000})
        assert obj.type == "reach_altitude"
        assert obj.params["minimum_m"] == 30000

    def test_mission_evaluate_capture_photo(self):
        obj = Objective(type="capture_photo", params={"target_id": "horizon", "minimum_quality": 0.7})
        assert obj.params["target_id"] == "horizon"
        assert obj.params["minimum_quality"] == 0.7
