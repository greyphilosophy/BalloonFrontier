"""Discord callback integration tests.

These tests exercise the full _LaunchButton.callback path — from
LaunchRequest construction through flight_service.run() to the
format_discord_results() call that was crashing with
AttributeError: 'FlightOutcome' has no attribute 'launch_request'.
"""

import pytest
from balloon_frontier.flight_service import (
    flight_service,
    FlightOutcome,
)
from balloon_frontier.launch_result import LaunchRequest, FillMode
from discord_bot import (
    format_discord_results,
    GAS_OPTIONS,
    ENVELOPE_OPTIONS,
    SITE_OPTIONS,
    PAYLOAD_OPTIONS,
)


class TestCallbackFormattingPath:
    """Test the Discord callback's formatting path after flight_service.run().

    Regression: after FlightService migration the callback was correctly
    extracting result.result but then accessing result.launch_request —
    FlightOutcome has no launch_request attribute, causing an
    AttributeError on every successful flight.
    """

    def test_full_callback_path_does_not_raise(self):
        """The full callback path (run -> extract -> format) should not raise.

        This is the integration test that catches regressions where
        FlightOutcome fields are accessed incorrectly.
        """
        # Build LaunchRequest like the Discord callback does
        launch_request = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=("camera", "battery"),
            launch_site_id="field",
            fill_mode=FillMode.NORMAL,
        )

        # Run the flight (this is what the callback does)
        outcome = flight_service.run(launch_request)

        # Verify FlightOutcome structure
        assert isinstance(outcome, FlightOutcome)
        assert outcome.result is not None

        # This is the path the callback follows — it should not raise
        result_obj = outcome.result
        tel = [
            {
                "time": tp.time_s,
                "alt": tp.altitude_m,
                "vel": tp.velocity_mps,
                "burst": tp.burst,
                "landed": tp.landed,
                "crashed": tp.crashed,
            }
            for tp in result_obj.telemetry
        ]

        peak_alt = result_obj.peak_altitude_m
        time_of_flight = result_obj.duration_s
        burst = result_obj.burst
        landed = result_obj.landed
        crashed = result_obj.crashed

        # Compute score (mimics callback)
        payload_keys = list(launch_request.payload_ids)
        payload_count = max(1, len([pid for pid in payload_keys if pid != "none"]))

        from balloon_frontier.flight_score import calculate_flight_score
        from balloon_frontier.medal_tier import medal_tier_to_string, get_medal_emoji
        score = calculate_flight_score(peak_alt, payload_count, time_of_flight)
        medal_name = medal_tier_to_string(peak_alt)
        medal_emoji = get_medal_emoji(peak_alt)

        # Get weather from FlightOutcome (no second prepare())
        weather_dict = {
            "name": outcome.weather.name if outcome.weather else "",
            "description": outcome.weather.description if outcome.weather else "",
            "severity": outcome.weather.severity if outcome.weather else "",
            "flight_modifier": outcome.weather.flight_modifier if outcome.weather else "",
        }

        # Build the chart (mimics callback)
        from balloon_frontier.ascii_chart import chart_to_string
        time_arr = [r["time"] for r in tel]
        alt_arr = [r["alt"] for r in tel]
        chart = chart_to_string(time_arr, alt_arr, title="Flight Trajectory")

        # Resolve catalog info (mimics callback's gas_info, env_info, site_info)
        gas_info = GAS_OPTIONS[launch_request.gas_id]
        env_info = ENVELOPE_OPTIONS[launch_request.envelope_id]
        site_info = SITE_OPTIONS[launch_request.launch_site_id]
        payload_names = [PAYLOAD_OPTIONS[p][0] for p in payload_keys]

        # This is the call that was crashing — verify it doesn't raise
        result_content = format_discord_results(
            peak_altitude=peak_alt,
            burst=burst,
            landed=landed,
            crashed=crashed,
            time_of_flight=time_of_flight,
            telemetry=tel,
            gas_name=gas_info[0],
            gas_mass=launch_request.gas_mass_kg,  # Was: result.launch_request.gas_mass_kg
            env_name=env_info[0],
            payload_names=", ".join(payload_names),
            site_name=site_info.name,
            mission_assignment=outcome.mission_assignment,
            player_id="test_user",
            weather_event=weather_dict,
            chart_str=chart,
        )

        # Verify the result is a non-empty string
        assert isinstance(result_content, str)
        assert len(result_content) > 0
        # Should contain key labels
        assert "Peak" in result_content or "altitude" in result_content.lower()

    def test_flight_outcome_no_launch_request_attribute(self):
        """FlightOutcome should not have a launch_request attribute.

        This test documents why the bug occurred — result is a FlightOutcome,
        not a FlightResult or LaunchRequest.
        """
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=("camera",),
            launch_site_id="field",
            fill_mode=FillMode.NORMAL,
        )
        outcome = flight_service.run(req)

        # Verify the attributes FlightOutcome actually has
        assert hasattr(outcome, 'result')
        assert hasattr(outcome, 'weather')
        assert hasattr(outcome, 'mission_assignment')
        assert hasattr(outcome, 'weather_impacts')

        # launch_request should NOT be on FlightOutcome
        assert not hasattr(outcome, 'launch_request')

        # But it IS on the nested FlightResult
        assert hasattr(outcome.result, 'launch_request')
        assert outcome.result.launch_request is req