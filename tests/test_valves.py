"""Tests for valve variants system."""

import pytest
from balloon_frontier.valves import (
    Valve, VALVES, get_valve, list_valves, valve_tradeoff_description,
)


class TestValveModel:
    def test_valve_creation(self):
        v = Valve("test", "Test Valve", 0.5, 2.5, 400, "A test valve")
        assert v.mass_kg == 0.5
        assert v.burst_stretch_ratio == 2.5

    def test_get_standard_valve(self):
        v = get_valve("standard")
        assert v.mass_kg == 0.5
        assert v.burst_stretch_ratio == 2.5

    def test_get_light_valve(self):
        v = get_valve("light")
        assert v.mass_kg == 0.3
        assert v.burst_stretch_ratio == 2.0

    def test_get_heavy_valve(self):
        v = get_valve("heavy")
        assert v.mass_kg == 1.0
        assert v.burst_stretch_ratio == 3.0

    def test_default_returns_standard(self):
        v = get_valve("nonexistent")
        assert v.id == "standard"

    def test_list_valves(self):
        valves = list_valves()
        assert len(valves) == 3

    def test_valve_tradeoff_description(self):
        desc = valve_tradeoff_description("light")
        assert "0.3kg" in desc
        assert "2.0x" in desc

    def test_light_valve_is_lighter(self):
        light = get_valve("light")
        heavy = get_valve("heavy")
        assert light.mass_kg < heavy.mass_kg

    def test_heavy_valve_has_more_stretch(self):
        light = get_valve("light")
        heavy = get_valve("heavy")
        assert heavy.burst_stretch_ratio > light.burst_stretch_ratio
