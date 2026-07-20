"""Tests for medal_tier module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from balloon_frontier.medal_tier import (
    MedalTier, get_medal_tier, get_medal_emoji, medal_tier_to_string,
)


class TestGetMedalTier:
    def test_none_below_10k(self):
        assert get_medal_tier(0) == MedalTier.NONE
        assert get_medal_tier(9999) == MedalTier.NONE

    def test_bronze_at_10k(self):
        assert get_medal_tier(10_000) == MedalTier.BRONZE

    def test_bronze_above_10k(self):
        assert get_medal_tier(15_000) == MedalTier.BRONZE

    def test_silver_at_20k(self):
        assert get_medal_tier(20_000) == MedalTier.SILVER

    def test_gold_at_30k(self):
        assert get_medal_tier(30_000) == MedalTier.GOLD

    def test_platinum_at_40k(self):
        assert get_medal_tier(40_000) == MedalTier.PLATINUM

    def test_platinum_above_40k(self):
        assert get_medal_tier(50_000) == MedalTier.PLATINUM

    def test_negative_altitude(self):
        assert get_medal_tier(-500) == MedalTier.NONE

    def test_edge_just_below_threshold(self):
        assert get_medal_tier(9_999) == MedalTier.BRONZE or get_medal_tier(9_999) == MedalTier.NONE
        # 9999 < 10000, so it's NONE
        assert get_medal_tier(9_999) == MedalTier.NONE

    def test_edge_just_below_silver(self):
        assert get_medal_tier(19_999) == MedalTier.BRONZE

    def test_edge_just_below_gold(self):
        assert get_medal_tier(29_999) == MedalTier.SILVER

    def test_edge_just_below_platinum(self):
        assert get_medal_tier(39_999) == MedalTier.GOLD


class TestGetMedalEmoji:
    def test_bronze_emoji(self):
        emoji = get_medal_emoji(15_000)
        assert emoji == "🟤"

    def test_silver_emoji(self):
        emoji = get_medal_emoji(25_000)
        assert emoji == "🟡"

    def test_gold_emoji(self):
        emoji = get_medal_emoji(35_000)
        assert emoji == "🥇"

    def test_platinum_emoji(self):
        emoji = get_medal_emoji(45_000)
        assert emoji == "💎"

    def test_none_emoji(self):
        emoji = get_medal_emoji(500)
        assert emoji == "⚪"

    def test_returns_string(self):
        emoji = get_medal_emoji(30_000)
        assert isinstance(emoji, str)


class TestMedalTierToString:
    def test_none_string(self):
        assert medal_tier_to_string(500) == "NONE"

    def test_bronze_string(self):
        assert medal_tier_to_string(15_000) == "BRONZE"

    def test_silver_string(self):
        assert medal_tier_to_string(25_000) == "SILVER"

    def test_gold_string(self):
        assert medal_tier_to_string(35_000) == "GOLD"

    def test_platinum_string(self):
        assert medal_tier_to_string(45_000) == "PLATINUM"

    def test_returns_string(self):
        assert isinstance(medal_tier_to_string(10_000), str)


class TestMedalTierEnum:
    def test_enum_has_five_members(self):
        assert len(MedalTier) == 5

    def test_enum_members_exist(self):
        assert MedalTier.NONE is not None
        assert MedalTier.BRONZE is not None
        assert MedalTier.SILVER is not None
        assert MedalTier.GOLD is not None
        assert MedalTier.PLATINUM is not None
