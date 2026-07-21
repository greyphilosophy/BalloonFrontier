"""
Medal tier determination for BalloonFrontier.

Maps a flight's peak altitude to a medal tier:
  Bronze    ≥ 10,000m
  Silver    ≥ 20,000m
  Gold      ≥ 30,000m
  Platinum  ≥ 40,000m

Altitudes below 10 km return "None" medal.
"""

from enum import Enum, auto
from typing import Optional


class MedalTier(Enum):
    """Medal tiers mapped to peak altitude thresholds."""
    NONE = auto()
    BRONZE = auto()
    SILVER = auto()
    GOLD = auto()
    PLATINUM = auto()


# Thresholds in meters (ordered from highest tier down)
_MEDAL_THRESHOLDS = [
    (MedalTier.PLATINUM, 40_000),
    (MedalTier.GOLD, 30_000),
    (MedalTier.SILVER, 20_000),
    (MedalTier.BRONZE, 10_000),
]

# Emoji map for display on results screens
_MEDAL_EMOJI = {
    MedalTier.NONE:     "⚪",
    MedalTier.BRONZE:   "🟤",
    MedalTier.SILVER:   "🟡",
    MedalTier.GOLD:     "🥇",
    MedalTier.PLATINUM: "💎",
}


def get_medal_tier(peak_altitude_m: float) -> MedalTier:
    """Determine the medal tier from the flight's peak altitude.

    Args:
        peak_altitude_m: Peak altitude in meters above sea level.

    Returns:
        The MedalTier enum value for the given peak altitude.
        Returns MedalTier.NONE if the flight peaks below 10,000m.

    Examples:
        >>> get_medal_tier(15_000)
        <MedalTier.BRONZE>
        >>> get_medal_tier(40_000)
        <MedalTier.PLATINUM>
        >>> get_medal_tier(500)
        <MedalTier.NONE>
    """
    for tier, threshold in _MEDAL_THRESHOLDS:
        if peak_altitude_m >= threshold:
            return tier
    return MedalTier.NONE


def get_medal_emoji(peak_altitude_m: float) -> str:
    """Return the emoji representation of the medal tier for a given peak altitude.

    Args:
        peak_altitude_m: Peak altitude in meters.

    Returns:
        Emoji string for the medal tier (e.g. "🥇" for Gold).
    """
    tier = get_medal_tier(peak_altitude_m)
    return _MEDAL_EMOJI.get(tier, "⚪")


def medal_tier_to_string(peak_altitude_m: float) -> str:
    """Convenience wrapper that returns the medal tier as a display string.

    Args:
        peak_altitude_m: Peak altitude in meters.

    Returns:
        Display name of the medal tier (e.g. "Bronze", "Gold", "None").
    """
    return get_medal_tier(peak_altitude_m).name


# ── Quick CLI demo ────────────────────────────────────────

if __name__ == "__main__":
    for alt in [500, 9_999, 10_000, 20_000, 30_000, 40_000, 40_001]:
        tier = get_medal_tier(alt)
        emoji = get_medal_emoji(alt)
        print(f"  {alt:>7}m → {tier.name:<10s} {emoji}")
