"""Tests for flight_score module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from balloon_frontier.flight_score import (
    calculate_flight_score, W_ALT, W_PAY, W_TIME,
)


class TestCalculateFlightScore:
    def test_basic_score(self):
        score = calculate_flight_score(
            altitude=15000, payloads=3, time_seconds=60.0
        )
        expected = (15000 * W_ALT) + (3 * W_PAY) + (60 * W_TIME)
        assert abs(score - expected) < 0.01

    def test_zero_values(self):
        score = calculate_flight_score(0, 0, 0)
        assert score == 0.0

    def test_custom_weights(self):
        score = calculate_flight_score(
            altitude=1000, payloads=2, time_seconds=30,
            w_alt=2.0, w_pay=250.0, w_time=50.0,
        )
        expected = (1000 * 2.0) + (2 * 250.0) + (30 * 50.0)
        assert abs(score - expected) < 0.01

    def test_negative_inputs(self):
        score = calculate_flight_score(-100, -1, -5.0)
        expected = (-100 * W_ALT) + (-1 * W_PAY) + (-5.0 * W_TIME)
        assert abs(score - expected) < 0.01

    def test_float_inputs(self):
        score = calculate_flight_score(100.5, 2.5, 30.5)
        expected = (100.5 * W_ALT) + (2.5 * W_PAY) + (30.5 * W_TIME)
        assert abs(score - expected) < 0.01

    def test_returns_float(self):
        score = calculate_flight_score(100, 1, 1)
        assert isinstance(score, float)

    def test_default_weights_match_constants(self):
        score = calculate_flight_score(10, 2, 5)
        expected = (10 * W_ALT) + (2 * W_PAY) + (5 * W_TIME)
        assert score == expected

    def test_high_altitude_dominates(self):
        score = calculate_flight_score(30000, 4, 100)
        alt_contribution = 30000 * W_ALT
        pay_contribution = 4 * W_PAY
        time_contribution = 100 * W_TIME
        assert score > alt_contribution
        assert score > pay_contribution
        assert score > time_contribution

