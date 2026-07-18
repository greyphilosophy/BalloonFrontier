"""Tests for progression system (budget, unlocks, reputation)."""

import pytest
from balloon_frontier.progression import (
    EnvelopeUnlock, ENVELOPES,
    get_unlock_path, get_envelope, list_unlocked_envelopes,
    PlayerState, PlayerRegistry,
)


class TestEnvelopeProgression:
    def test_get_unlock_path(self):
        path = get_unlock_path()
        assert "latex" in path
        assert "mylar" in path

    def test_get_envelope_default(self):
        e = get_envelope("latex")
        assert e.id == "latex"

    def test_get_envelope_nonexistent(self):
        e = get_envelope("unknown")
        assert e.id == "latex"  # Default fallback

    def test_unlocked_envelopes_by_reputation(self):
        unlocked = list_unlocked_envelopes(0, 100)
        assert len(unlocked) >= 1

    def test_all_envelopes_require_increasing_reputation(self):
        reps = [e.min_reputation for e in ENVELOPES]
        assert reps == sorted(reps)

    def test_envelope_costs_increasing(self):
        costs = [e.cost for e in ENVELOPES]
        assert costs == sorted(costs)


class TestPlayerState:
    def test_new_player_state(self):
        p = PlayerState()
        assert p.reputation == 0
        assert p.budget == 100
        assert p.total_flights == 0

    def test_earn_from_mission_increases_flights(self):
        p = PlayerState()
        p.earn_from_mission("test", 80.0)
        assert p.total_flights == 1

    def test_successful_mission_gains_reputation(self):
        p = PlayerState()
        result = p.earn_from_mission("test", 80.0)
        assert p.reputation > 0
        assert result["reputation_gained"] > 0

    def test_successful_mission_earns_budget(self):
        p = PlayerState()
        result = p.earn_from_mission("test", 80.0)
        assert result["budget_earned"] > 0

    def test_failed_mission_earns_less(self):
        p = PlayerState()
        p.earn_from_mission("test", 30.0)
        p2 = PlayerState()
        p2.earn_from_mission("test", 90.0)
        assert p.budget < p2.budget

    def test_successful_mission_tracks_success(self):
        p = PlayerState()
        p.earn_from_mission("test", 80.0)
        assert p.successful_flights == 1

    def test_mission_tracking(self):
        p = PlayerState()
        p.earn_from_mission("mission_a", 80.0)
        p.earn_from_mission("mission_b", 75.0)
        assert "mission_a" in p.missions_completed
        assert "mission_b" in p.missions_completed

    def test_save_and_load(self, tmp_path):
        p = PlayerState()
        p.earn_from_mission("test", 80.0)
        save_path = str(tmp_path / "save.json")
        p.save(save_path)
        loaded = PlayerState.load(save_path)
        assert loaded.reputation == p.reputation
        assert loaded.budget == p.budget

    def test_load_new_player(self, tmp_path):
        save_path = str(tmp_path / "new_save.json")
        loaded = PlayerState.load(save_path)
        assert loaded.reputation == 0


class TestPlayerRegistry:
    def test_get_or_create(self):
        PlayerRegistry._players.clear()
        p = PlayerRegistry.get_or_create("player1")
        assert p.reputation == 0

    def test_leaderboard(self):
        PlayerRegistry._players.clear()
        p1 = PlayerRegistry.get_or_create("player1")
        p1.reputation = 5
        p2 = PlayerRegistry.get_or_create("player2")
        p2.reputation = 10
        lb = PlayerRegistry.leaderboard("reputation")
        assert lb[0].reputation == 10
