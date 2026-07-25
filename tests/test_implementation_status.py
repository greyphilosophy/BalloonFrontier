"""Tests for payload implementation status + shared validation."""

from __future__ import annotations

import re

import pytest

from balloon_frontier.catalog import CATALOG, ImplementationStatus
from balloon_frontier.launch_result import FillMode, LaunchRequest


STUBBED_PAYLOAD_IDS: tuple[str, ...] = (
    "barometer",
    "gps_receiver",
    "parafoil",
    "propeller_pod",
    "solar_panel",
    "thermometer",
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


@pytest.mark.parametrize("payload_id", STUBBED_PAYLOAD_IDS)
def test_dormant_payload_is_stubbed(payload_id: str) -> None:
    payload = CATALOG.payload(payload_id)

    assert payload.implementation_status is ImplementationStatus.STUBBED
    assert payload.unavailable_reason


@pytest.mark.parametrize("payload_id", STUBBED_PAYLOAD_IDS)
def test_dormant_payload_is_rejected_from_launch_request(payload_id: str) -> None:
    payload = CATALOG.payload(payload_id)

    with pytest.raises(
        ValueError,
        match=re.escape(f"{payload.name} is not available"),
    ):
        LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=(payload_id,),
            launch_site_id="field",
            fill_mode=FillMode.AUTO,
        )
