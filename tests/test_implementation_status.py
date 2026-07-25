"""Tests for payload implementation status + shared validation."""

from __future__ import annotations

import pytest

from balloon_frontier.catalog import CATALOG, ImplementationStatus
from balloon_frontier.launch_result import FillMode, LaunchRequest


def test_extraneous_payloads_are_marked_stubbed() -> None:
    assert CATALOG.payload("solar_panel").implementation_status == ImplementationStatus.STUBBED
    assert CATALOG.payload("propeller_pod").implementation_status == ImplementationStatus.STUBBED


def test_stubbed_payload_is_rejected_from_launch_request() -> None:
    with pytest.raises(ValueError, match=r"Payload 'solar_panel'.*stubbed"):
        LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=("solar_panel",),
            launch_site_id="field",
            fill_mode=FillMode.AUTO,
        )


def test_implemented_payload_is_allowed() -> None:
    req = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
    )
    ids = [p.id for p in req.payloads]
    assert ids == ["camera"]
