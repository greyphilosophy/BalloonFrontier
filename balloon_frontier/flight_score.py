"""
Flight score calculation for the BalloonFrontier Discord bot.

Score = (Altitude * W_ALT) + (Payloads * W_PAY) + (Time * W_TIME)

This module provides a reusable function to compute a flight score
using configurable weight constants.
"""

# Configurable weight constants
W_ALT = 1.0
W_PAY = 500.0
W_TIME = 100.0


def calculate_flight_score(
    altitude: float,
    payloads: int,
    time_seconds: float,
    w_alt: float = W_ALT,
    w_pay: float = W_PAY,
    w_time: float = W_TIME,
) -> float:
    """
    Compute the flight score using a weighted formula.

    Score = (Altitude * W_ALT) + (Payloads * W_PAY) + (Time * W_TIME)

    Args:
        altitude: Altitude in units (e.g., feet). Defaults to 1.0 weight.
        payloads: Number of payloads collected. Defaults to 500.0 weight.
        time_seconds: Total time in seconds. Defaults to 100.0 weight.
        w_alt: Custom altitude weight override.
        w_pay: Custom payload weight override.
        w_time: Custom time weight override.

    Returns:
        The numeric flight score.
    """
    score = (altitude * w_alt) + (payloads * w_pay) + (time_seconds * w_time)
    return score
