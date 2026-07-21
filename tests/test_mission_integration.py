import sys

sys.path.insert(0, "/home/greyphilosophy/projects/BalloonFrontier")

from discord_bot import make_result_embed, run_simulation


def test_make_result_embed_includes_assigned_missions_when_present():
    telemetry = [
        {"time": 0.0, "alt": 0.0, "vel": 0.0},
        {"time": 1.0, "alt": 10.0, "vel": 2.0},
    ]
    summary = {
        "peak_altitude": 10.0,
        "burst": False,
        "time_of_flight": 1.0,
        "payload_count": 1,
        "score": 0.0,
        "medal": "Bronze",
        "medal_emoji": "🥉",
        "assigned_missions": ["m1", "m2"],
        "mission_seed": 123,
        "mission_count": 2,
    }

    result = make_result_embed(
        gas_name="Helium",
        gas_mass=1.0,
        env_name="Latex",
        payload_name="None",
        site_name="Open Field",
        telemetry=telemetry,
        summary=summary,
    )

    assert "Missions: m1, m2" in result


def test_run_simulation_propagates_mission_assignment_into_summary():
    mission_assignment = {
        "missions": ["mx"],
        "seed": 42,
        "mission_count": 1,
    }

    tel, summary = run_simulation(
        "helium",
        2.0,
        288.15,
        1.0,
        0.47,
        10.0,
        3.0,
        mission_assignment=mission_assignment,
    )

    assert summary["assigned_missions"] == ["mx"]
    assert summary["mission_seed"] == 42
    assert summary["mission_count"] == 1
