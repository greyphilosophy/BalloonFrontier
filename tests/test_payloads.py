"""Tests for the payload system."""

import pytest
from balloon_frontier.payloads import (
    Payload, Payloads, PAYLOAD_DEFINITIONS,
)


class TestPayloadModel:
    def test_create_payload(self):
        p = Payload("test", "Test Payload", 1.5, 300, "A test", tag="sensor")
        assert p.id == "test"
        assert p.mass_kg == 1.5
        assert p.tag == "sensor"

    def test_payloads_registry(self):
        assert len(Payloads.list_all()) > 0
        for p in Payloads.list_all():
            assert p.id
            assert p.name
            assert p.mass_kg > 0

    def test_get_payload(self):
        p = Payloads.get("camera")
        assert p.id == "camera"
        assert p.tag == "sensor"

    def test_get_payload_valve(self):
        p = Payloads.get("pressure_valve")
        assert p.tag == "vent"
        assert p.mass_kg == 0.5

    def test_unknown_payload_raises(self):
        with pytest.raises(KeyError):
            Payloads.get("nonexistent")

    def test_list_all_returns_payloads(self):
        all_p = Payloads.list_all()
        assert len(all_p) > 5

    def test_tags_exist(self):
        tags = {p.tag for p in Payloads.list_all()}
        for expected in ["sensor", "vent", "ballast", "recovery"]:
            assert expected in tags

    def test_valve_is_defined(self):
        valve = Payloads.get("pressure_valve")
        assert valve.mass_kg > 0
        assert valve.mass_kg < 2.0
        assert valve.tag == "vent"

    def test_payload_mass_sum(self):
        """Sum of selected payloads gives total payload mass."""
        payloads = [Payloads.get("camera"), Payloads.get("radio"), Payloads.get("battery")]
        total = sum(p.mass_kg for p in payloads)
        assert total > 0
