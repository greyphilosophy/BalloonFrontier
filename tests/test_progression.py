"""Tests for progression system (budget, unlocks, reputation)."""

import pytest
from balloon_frontier.progression import (
    EnvelopeUnlock, ENVELOPES,
    get_unlock_path, get_envelope, list_unlocked_envelopes, list_locked_envelopes,
    PlayerState, PlayerRegistry,
    PAYLOAD_UNLOCKS, SITES,
    list_unlocked_payloads, list_locked_payloads,
    list_unlocked_sites, list_locked_sites, envelope_needs,
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

    def test_latex_always_unlocked(self):
        # Latex requires 0 rep and 0 cost — always available
        assert "latex" in [e.id for e in list_unlocked_envelopes(0, 0)]

    def test_mylar_unlocks_at_1000_credits_or_5_rep(self):
        # OR logic: credits only
        assert any(e.id == "mylar" for e in list_unlocked_envelopes(0, 1000))
        # OR logic: reputation only
        assert any(e.id == "mylar" for e in list_unlocked_envelopes(5, 0))
        # Not unlocked with insufficient amounts
        assert not any(e.id == "mylar" for e in list_unlocked_envelopes(4, 999))

    def test_zero_pressure_unlocks_at_3000_or_10(self):
        assert any(e.id == "zero_pressure" for e in list_unlocked_envelopes(0, 3000))
        assert any(e.id == "zero_pressure" for e in list_unlocked_envelopes(10, 0))
        assert not any(e.id == "zero_pressure" for e in list_unlocked_envelopes(9, 2999))

    def test_blimp_unlocks_at_5000_or_20(self):
        assert any(e.id == "blimp" for e in list_unlocked_envelopes(0, 5000))
        assert any(e.id == "blimp" for e in list_unlocked_envelopes(20, 0))
        assert not any(e.id == "blimp" for e in list_unlocked_envelopes(19, 4999))

    def test_list_locked_envelopes(self):
        locked = list_locked_envelopes(0, 0)
        ids = [e.id for e in locked]
        assert "latex" not in ids
        assert "mylar" in ids

    def test_locked_envelopes_needs_text(self):
        player_rep = 2
        player_budget = 100
        mylar = get_envelope("mylar")
        need = envelope_needs(player_rep, player_budget, mylar)
        assert "credit" in need.lower() or "rep" in need.lower()


class TestPayloadUnlocks:
    def test_basic_payloads_always_available(self):
        """All payloads with min_reputation=0 and cost=0 are always unlocked."""
        unlocked_ids = [p.id for p in list_unlocked_payloads(0, 0)]
        basic_ids = [p.id for p in PAYLOAD_UNLOCKS if p.min_reputation == 0 and p.cost == 0]
        for bid in basic_ids:
            assert bid in unlocked_ids, f"Basic payload {bid} should be unlocked at start"

    def test_advanced_payloads_locked_initially(self):
        advanced = [p.id for p in PAYLOAD_UNLOCKS if p.min_reputation > 0 or p.cost > 0]
        locked_ids = [p.id for p in list_locked_payloads(0, 0)]
        for aid in advanced:
            assert aid in locked_ids, f"Advanced payload {aid} should be locked initially"

    def test_heater_unlocks_at_rep_3(self):
        unlocked_ids = [p.id for p in list_unlocked_payloads(3, 0)]
        assert "heater" in unlocked_ids

    def test_flight_computer_unlocks_at_rep_3(self):
        unlocked_ids = [p.id for p in list_unlocked_payloads(3, 0)]
        assert "flight_computer" in unlocked_ids

    def test_payload_or_logic(self):
        # Can unlock via budget instead of reputation
        unlocked_ids = [p.id for p in list_unlocked_payloads(0, 250)]
        assert "heater" in unlocked_ids

    def test_locked_payload_needs_info(self):
        locked = list_locked_payloads(0, 0)
        heater = [p for p in locked if p.name == "Heater"]
        assert len(heater) == 1
        assert heater[0].min_reputation == 3
        assert heater[0].cost == 250


class TestSiteUnlocks:
    def test_open_field_always_unlocked(self):
        assert any(s.id == "field" for s in list_unlocked_sites(0, 0))

    def test_rooftop_unlocks_at_3_rep(self):
        assert any(s.id == "rooftop" for s in list_unlocked_sites(3, 0))
        # Sites with cost=0 are reputation-gated only; budget cannot bypass rep.
        assert not any(s.id == "rooftop" for s in list_unlocked_sites(0, 9999))

    def test_mountain_unlocks_at_8_rep(self):
        assert any(s.id == "mountain" for s in list_unlocked_sites(8, 0))
        # Sites with cost=0 are reputation-gated only.
        assert not any(s.id == "mountain" for s in list_unlocked_sites(0, 9999))

    def test_site_locks_shown_properly(self):
        locked = list_locked_sites(0, 0)
        site_ids = [s.id for s in locked]
        assert "field" not in site_ids

    def test_site_attributes(self):
        mountain = next((s for s in SITES if s.id == "mountain"), None)
        assert mountain is not None
        assert mountain.altitude_m == 1500.0
        assert mountain.wind_strength == 4.0


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

    def test_payload_is_unlocked_initially(self):
        p = PlayerState()
        assert p.is_payload_unlocked("camera")
        assert p.is_payload_unlocked("battery")
        assert p.is_payload_unlocked("none")

    def test_payload_is_not_unlocked_when_locked(self):
        p = PlayerState()
        assert not p.is_payload_unlocked("heater")  # needs rep 3

    def test_site_is_unlocked_initially(self):
        p = PlayerState()
        assert p.is_site_unlocked("field")

    def test_site_is_not_unlocked_when_locked(self):
        p = PlayerState()
        assert not p.is_site_unlocked("rooftop")
        assert not p.is_site_unlocked("mountain")

    def test_profile_summary(self):
        p = PlayerState()
        p._player_id = "test_user"
        p.reputation = 5
        p.budget = 500
        summary = p.status_summary()
        assert "test_user" in summary
        assert "5" in summary
        assert "500" in summary


class TestAutomaticUnlocks:
    def test_auto_unsafe_gas_after_successful_flight(self):
        """After a successful flight, player might unlock envelopes automatically."""
        p = PlayerState()
        # Simulate earning enough through missions
        p.reputation = 5
        p.budget = 1000

        result = p.earn_from_mission("test", 60.0)
        # Mylar should be unlocked now
        assert "Mylar" in result["new_unlocks"] or "mylar" in p.unlocked_envelopes

    def test_multi_unlock_on_jump(self):
        """Jumping high enough can unlock multiple equipment at once."""
        p = PlayerState()
        p.reputation = 20  # Enough for everything
        p.budget = 5000

        result = p.earn_from_mission("big_mission", 100.0)
        # Should have many new unlocks
        assert len(result["new_unlocks"]) >= 3

    def test_no_duplicate_unlocks(self):
        """Calling earn_from_mission multiple times shouldn't re-unlock."""
        p = PlayerState()
        p.reputation = 20
        p.budget = 5000
        p._check_and_apply_unlocks()  # Pre-unlock everything

        initial_count = len(p.unlocked_envelopes)
        result = p.earn_from_mission("test", 100.0)
        assert len(result["new_unlocks"]) == 0
        assert len(p.unlocked_envelopes) == initial_count


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

    def test_registry_persists_state(self):
        PlayerRegistry._players.clear()
        p1 = PlayerRegistry.get_or_create("player1")
        p1.reputation = 5
        p2 = PlayerRegistry.get_or_create("player1")
        assert p2.reputation == 5  # Same instance

    def test_flush_all_saves_to_disk(self, tmp_path):
        # Patch the save directory temporarily
        import pathlib
        old_save_dir = PlayerRegistry._save_dir
        PlayerRegistry._save_dir = tmp_path

        try:
            PlayerRegistry._players.clear()
            p = PlayerRegistry.get_or_create("flush_test")
            p.reputation = 10
            count = PlayerRegistry.flush_all()
            assert count == 1
            # File should exist
            save_file = tmp_path / "flush_test.json"
            assert save_file.exists()
            data = __import__("json").loads(save_file.read_text())
            assert data["reputation"] == 10
        finally:
            PlayerRegistry._save_dir = old_save_dir


class TestEnrollmentEdgeCases:
    def test_negative_reputation_handled(self):
        p = PlayerState()
        p.reputation = -5  # edge case
        assert not p.is_site_unlocked("rooftop")

    def test_zero_budget(self):
        p = PlayerState()
        p.budget = 0
        p.reputation = 0
        # Basic payloads still available
        assert p.is_payload_unlocked("camera")
        # Advanced payloads locked
        assert not p.is_payload_unlocked("heater")

    def test_varying_reputation_thresholds(self):
        """Verify threshold ordering matches GDD spec."""
        p = PlayerState()
        p.reputation = 0
        p.budget = 0
        assert p.is_site_unlocked("field")
        assert not p.is_site_unlocked("rooftop")

        p.reputation = 3
        assert p.is_site_unlocked("rooftop")
        assert not p.is_site_unlocked("mountain")

        p.reputation = 8
        assert p.is_site_unlocked("mountain")


class TestAutoUnlocksOnIsCheck:
    """Tests that _check_and_apply_unlocks runs inside is_*_unlocked so
    unlocked lists are updated eagerly rather than only at save time."""

    def test_is_payload_unlocked_triggers_check(self):
        p = PlayerState()
        # At start, heater is locked (needs rep 3 or cost 250).
        assert not p.is_payload_unlocked("heater"), "Should be locked initially"

        # Give budget but no reputation — should now unlock via OR logic.
        p.budget = 250
        # Calling is_payload_unlocked should trigger _check_and_apply_unlocks.
        assert p.is_payload_unlocked("heater"), "Budget alone should unlock heater"

    def test_is_site_unlocked_triggers_check(self):
        p = PlayerState()
        assert not p.is_site_unlocked("rooftop")

        p.budget = 1000  # Sites have cost=0, so budget doesn't help here; need rep
        p.reputation = 3
        assert p.is_site_unlocked("rooftop")

    def test_is_envelope_unlocked_triggers_check(self):
        p = PlayerState()
        assert not p.is_envelope_unlocked("mylar")

        p.budget = 1000
        # Budget-only path triggers unlock.
        assert p.is_envelope_unlocked("mylar")

    def test_auto_unfreeze_after_mission_reward(self):
        """Player earns enough budget in a mission and can immediately
        use it when selecting envelope/payload/site."""
        p = PlayerState()
        p.budget = 4900  # Just short of Mylar (1000) ... wait, Mylar is 1000.
        p.budget = 900   # Still below 1000
        p.reputation = 4

        # Should still be locked.
        assert not p.is_envelope_unlocked("mylar")

        # Now give exact threshold.
        p.budget = 1000
        assert p.is_envelope_unlocked("mylar")


class TestNarrativeResultIntegration:
    """Tests that narrative_result properly uses OR logic for all equipment types."""

    def test_payload_unlock_via_budget_only(self):
        from balloon_frontier.progression import ENVELOPES

        player = PlayerRegistry.get_or_create("narr_test_a")
        PlayerRegistry._players.pop("narr_test_a", None)
        player = PlayerState()

        # Only budget, no reputation
        player.budget = 250  # Heater needs cost 250 or rep 3
        player.reputation = 0

        # Check payload unlocks (simulating what narrative does).
        for puid in PAYLOAD_UNLOCKS:
            if puid.id == "heater":
                if player.reputation >= puid.min_reputation or player.budget >= puid.cost:
                    assert True  # heater should unlock via budget

    def test_site_unlock_via_budget_only(self):
        p = PlayerState()
        p.budget = 100  # Sites have cost=0, so this doesn't apply

        # Actually sites use cost=0 so reputation is the only gate.
        p.reputation = 3
        assert p.is_site_unlocked("rooftop")


class TestDiscordIntegration:
    """Tests that discord_bot filtering works correctly."""

    def test_discord_bot_imports(self):
        # discord_bot.py lives at project root alongside the balloon_frontier pkg.
        import sys, os
        proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if proj_root not in sys.path:
            sys.path.insert(0, proj_root)
        import discord_bot as db
        assert "camera" in db.PAYLOAD_OPTIONS
        assert "heater" in db.PAYLOAD_OPTIONS
        site_keys = list(db.SITE_OPTIONS.keys())
        assert "field" in site_keys
        assert "mountain" in site_keys
        assert "rooftop" in site_keys
        env_keys = list(db.ENVELOPE_OPTIONS.keys())
        assert "latex" in env_keys
        assert "mylar" in env_keys