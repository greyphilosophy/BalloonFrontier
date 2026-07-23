"""Tests for medal_tier module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from balloon_frontier.medal_tier import (
    MedalTier, get_medal_tier, get_medal_emoji, medal_tier_to_string,
)


class TestGetMedalTier:
    def test_none_below_2k(self):
        assert get_medal_tier(0) == MedalTier.NONE
        assert get_medal_tier(1_999) == MedalTier.NONE

    def test_bronze_at_2k(self):
        assert get_medal_tier(2_000) == MedalTier.BRONZE

    def test_bronze_above_2k(self):
        assert get_medal_tier(3_000) == MedalTier.BRONZE

    def test_silver_at_4k(self):
        assert get_medal_tier(4_000) == MedalTier.SILVER

    def test_gold_at_6k(self):
        assert get_medal_tier(6_000) == MedalTier.GOLD

    def test_platinum_at_8k(self):
        assert get_medal_tier(8_000) == MedalTier.PLATINUM

    def test_platinum_above_8k(self):
        assert get_medal_tier(10_000) == MedalTier.PLATINUM

    def test_negative_altitude(self):
        assert get_medal_tier(-500) == MedalTier.NONE

    def test_edge_just_below_threshold(self):
        # 1999 < 2000, so it's NONE
        assert get_medal_tier(1_999) == MedalTier.NONE

    def test_edge_just_below_silver(self):
        assert get_medal_tier(3_999) == MedalTier.BRONZE

    def test_edge_just_below_gold(self):
        assert get_medal_tier(5_999) == MedalTier.SILVER

    def test_edge_just_below_platinum(self):
        assert get_medal_tier(7_999) == MedalTier.GOLD


class TestGetMedalEmoji:
    def test_bronze_emoji(self):
        emoji = get_medal_emoji(3_000)
        assert emoji == "🟤"

    def test_silver_emoji(self):
        emoji = get_medal_emoji(5_000)
        assert emoji == "🟡"

    def test_gold_emoji(self):
        emoji = get_medal_emoji(7_000)
        assert emoji == "🥇"

    def test_platinum_emoji(self):
        emoji = get_medal_emoji(9_000)
        assert emoji == "💎"

    def test_none_emoji(self):
        emoji = get_medal_emoji(500)
        assert emoji == "⚪"

    def test_returns_string(self):
        emoji = get_medal_emoji(6_000)
        assert isinstance(emoji, str)


class TestMedalTierToString:
    def test_none_string(self):
        assert medal_tier_to_string(500) == "NONE"

    def test_bronze_string(self):
        assert medal_tier_to_string(3_000) == "BRONZE"

    def test_silver_string(self):
        assert medal_tier_to_string(5_000) == "SILVER"

    def test_gold_string(self):
        assert medal_tier_to_string(7_000) == "GOLD"

    def test_platinum_string(self):
        assert medal_tier_to_string(9_000) == "PLATINUM"

    def test_returns_string(self):
        assert isinstance(medal_tier_to_string(2_000), str)


class TestMedalTierEnum:
    def test_enum_has_five_members(self):
        assert len(MedalTier) == 5

    def test_enum_members_exist(self):
        assert MedalTier.NONE is not None
        assert MedalTier.BRONZE is not None
        assert MedalTier.SILVER is not None
        assert MedalTier.GOLD is not None
        assert MedalTier.PLATINUM is not None
