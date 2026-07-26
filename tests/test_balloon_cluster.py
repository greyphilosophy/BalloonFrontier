from types import SimpleNamespace

import pytest

from balloon_frontier.balloon_cluster import (
    BalloonClusterFlightService,
    ClusteredLaunchRequest,
)
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.tutorial import evaluate_tutorial_outcome


def _request(**overrides):
    values = {
        "gas_id": "helium",
        "envelope_id": "mylar",
        "payload_ids": ("quadcopter",),
        "launch_site_id": "field",
        "fill_mode": FillMode.AUTO,
    }
    values.update(overrides)
    return ClusteredLaunchRequest(**values)


def _outcome():
    return FlightOutcome(result=SimpleNamespace(peak_altitude_m=0.0, duration_s=0.0))


def test_cluster_scales_automatic_gas_envelope_capacity_and_mass():
    single = _request(balloon_count=1)
    cluster = _request(balloon_count=4)

    single_state = single.to_simulation_state()
    cluster_state = cluster.to_simulation_state()

    assert cluster.gas_mass_kg == pytest.approx(single.gas_mass_kg * 4)
    assert cluster_state.envelope.max_volume_m3 == pytest.approx(
        single_state.envelope.max_volume_m3 * 4
    )
    assert cluster_state.envelope.mass_kg == pytest.approx(
        single_state.envelope.mass_kg * 4
    )


def test_manual_fill_is_an_explicit_total_for_the_cluster():
    request = _request(
        balloon_count=5,
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=0.25,
    )
    assert request.gas_mass_kg == pytest.approx(0.25)


@pytest.mark.parametrize("count", [0, 101, 1.5, True])
def test_invalid_balloon_counts_are_rejected(count):
    with pytest.raises(ValueError, match="balloon_count"):
        _request(balloon_count=count)


def test_service_wrapper_preserves_request_and_adds_quantity():
    captured = SimpleNamespace(request=None)

    class Service:
        def run(self, request):
            captured.request = request
            return "ok"

    wrapper = BalloonClusterFlightService(Service(), balloon_count=7)
    ordinary = LaunchRequest(
        gas_id="helium",
        envelope_id="mylar",
        payload_ids=("quadcopter",),
        launch_site_id="field",
        fill_mode=FillMode.AUTO,
    )

    assert wrapper.run(ordinary) == "ok"
    assert isinstance(captured.request, ClusteredLaunchRequest)
    assert captured.request.balloon_count == 7
    assert captured.request.payload_ids == ordinary.payload_ids


def test_modest_party_balloon_clusters_can_complete_tutorial():
    result = evaluate_tutorial_outcome(_request(balloon_count=3), _outcome())
    assert result.mission_results[0].completed


def test_excessive_party_balloon_cluster_leaves_range():
    result = evaluate_tutorial_outcome(_request(balloon_count=4), _outcome())
    mission = result.mission_results[0]
    assert not mission.completed
    assert mission.explanation == "The aircraft left communications range and was lost."
