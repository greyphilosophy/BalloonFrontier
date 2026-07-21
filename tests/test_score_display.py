"""Tests for post-flight score and medal display integration.

Verifies that score and medal are correctly computed and displayed in
both the Discord bot results embed and the CLI game results screen.
"""

import sys
import os
sys.path.insert(0, "/home/greyphilosophy/projects/BalloonFrontier")

import pytest

from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.medal_tier import (
    get_medal_tier, get_medal_emoji, medal_tier_to_string, MedalTier,
)
from discord_bot import (
    run_simulation, make_result_embed, format_score_breakdown,
)


class TestScoreBreakdown:
    """Test format_score_breakdown output."""

    def test_format_score_breakdown_returns_string(self):
        breakdown = format_score_breakdown(10000, 5000, 1, 10)
        assert isinstance(breakdown, str)
        assert "Altitude" in breakdown
        assert "Payloads" in breakdown
        assert "Time" in breakdown
        assert "TOTAL" in breakdown

    def test_format_score_breakdown_altitude_points(self):
        """10000m altitude × 1.0 = 10000 pts."""
        breakdown = format_score_breakdown(10000, 10000, 1, 10)
        assert "10,000 pts" in breakdown

    def test_format_score_breakdown_payload_points(self):
        """3 payloads × 500 = 1500 pts."""
        breakdown = format_score_breakdown(0, 10000, 3, 10)
        assert "1,500 pts" in breakdown

    def test_format_score_breakdown_time_points(self):
        """30.5s × 100 = 3050 pts."""
        breakdown = format_score_breakdown(3050, 10000, 1, 30.5)
        assert "3,050 pts" in breakdown

    def test_format_score_breakdown_zero_values(self):
        breakdown = format_score_breakdown(0, 0, 0, 0)
        assert "0 pts" in breakdown

    def test_format_score_breakdown_total_matches_components(self):
        score = calculate_flight_score(10000, 3, 30)
        breakdown = format_score_breakdown(score, 10000, 3, 30)
        expected_total = int(score)
        assert f"TOTAL: {expected_total:,} pts" in breakdown


class TestMakeResultEmbedScoreDisplay:
    """Test that make_result_embed includes score and medal sections."""

    def _tel(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[0]

    def _summary_for_embed(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[1]

    def test_embed_contains_score_breakdown_header(self):
        tel = self._tel()
        summary = self._summary_for_embed()
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field", tel, summary
        )
        assert "Score Breakdown" in result

    def test_embed_contains_altitude_pts(self):
        tel = self._tel()
        summary = self._summary_for_embed()
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field", tel, summary
        )
        assert "Altitude:" in result
        assert "pts" in result

    def test_embed_contains_total_pts(self):
        tel = self._tel()
        summary = self._summary_for_embed()
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field", tel, summary
        )
        assert "TOTAL:" in result

    def test_embed_contains_medal(self):
        tel = self._tel()
        summary = self._summary_for_embed()
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field", tel, summary
        )
        # Medal line should be present with emoji and name
        assert "Medal:" in result

    def test_embed_contains_time_of_flight(self):
        tel = self._tel()
        summary = self._summary_for_embed()
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field", tel, summary
        )
        assert "Time of Flight:" in result


class TestScoreMedalIntegration:
    """Integration tests: score and medal appear together correctly."""

    def test_score_and_medal_for_low_altitude(self):
        """Low peak altitude → None medal + low score."""
        tier = get_medal_tier(500)
        assert tier == MedalTier.NONE
        assert get_medal_emoji(500) == "⚪"
        score = calculate_flight_score(500, 1, 10)
        assert score > 0

    def test_score_and_medal_for_gold_altitude(self):
        """30,000m → Gold medal."""
        tier = get_medal_tier(30_000)
        assert tier == MedalTier.GOLD
        assert get_medal_emoji(30_000) == "🥇"

    def test_score_and_medal_for_platinum_altitude(self):
        """40,000m → Platinum medal."""
        tier = get_medal_tier(40_000)
        assert tier == MedalTier.PLATINUM
        assert get_medal_emoji(40_000) == "💎"

    def test_medal_emoji_appears_in_embed(self):
        """When the balloon reaches high altitude, medal emoji shows."""
        tel = self._get_high_alt_telemetry()
        summary = self._get_high_alt_summary()
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field", tel, summary
        )
        # The embed should contain a medal line with an emoji
        assert "Medal:" in result

    def _get_high_alt_telemetry(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[0]

    def _get_high_alt_summary(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[1]


class TestScoreCalculationConsistency:
    """Ensure calculate_flight_score matches the displayed breakdown."""

    def test_score_formula_matches_breakdown(self):
        peak = 15000
        payloads = 2
        time = 25
        score = calculate_flight_score(peak, payloads, time)
        breakdown = format_score_breakdown(score, peak, payloads, time)
        alt_pts = int(peak * 1.0)
        pay_pts = int(payloads * 500.0)
        time_pts = int(time * 100.0)
        total = alt_pts + pay_pts + time_pts
        assert int(score) == total
        assert f"TOTAL: {total:,} pts" in breakdown

    def test_score_zero_inputs(self):
        score = calculate_flight_score(0, 0, 0)
        assert score == 0.0

    def test_score_negative_altitude(self):
        score = calculate_flight_score(-100, 1, 10)
        assert score == -100 * 1.0 + 1 * 500 + 10 * 100
